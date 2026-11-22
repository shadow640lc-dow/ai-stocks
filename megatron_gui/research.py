"""Structured research console.

The engine keeps printing its terminal report; this widget parses those real
lines into per-analyst cards (state, signal, confidence, details, timestamp).
Nothing is inferred or invented: whatever cannot be parsed stays readable in
the ENGINE OUTPUT pane.
"""

from __future__ import annotations

import ast
import json
import re
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .catalog import Analyst
from .components import Card, Pill, section

STATE_COLORS = {
    "pending": theme.DIM,
    "running": theme.BLUE,
    "done": theme.GREEN,
    "failed": theme.RED,
    "cancelled": theme.YELLOW,
    "skipped": theme.DIM,
}
SIGNAL_COLORS = {"BULLISH": theme.GREEN, "BEARISH": theme.RED, "NEUTRAL": theme.YELLOW}

PROGRESS_RE = re.compile(r"^([✓✗⋯])\s+(.+?)\s+\[([A-Za-z0-9.\-]{1,10})\]\s*(.*)$")
SIGNAL_RE = re.compile(r"Signal:\s+.*?(BULLISH|BEARISH|NEUTRAL)", re.IGNORECASE)
CONF_RE = re.compile(r"Confidence:\s+([\d.]+)%")
DETAIL_RE = re.compile(r"📈\s+(.+?)\s*$")
KV_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 /&()._%\-']{2,34})\s{2,}(.+)$")
KV_LABEL_RE = re.compile(r"^([A-Z][A-Za-z /&'()\-]{2,30}):\s+(.+)$")
SECTION_RE = re.compile(r"^[A-Z][A-Z0-9 /&'()\-]{3,38}$")
EXC_RE = re.compile(r"^[\w.]*(?:Error|Exception|Interrupt)\b")
PERCENT_RE = re.compile(r"([+-]?\d+(?:\.\d+)?)\s*%")
FINANCE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 /&().%_\-]{1,30}):\s*(.+)$")


def _chip(text: str, *, checkable: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("Chip")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setCheckable(checkable)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return button


class MiniBar(QWidget):
    """A high-contrast meter with a dark track, ticks and a neon fill."""

    def __init__(
        self,
        value: float = 0.0,
        color: str = theme.GREEN,
        parent: QWidget | None = None,
        *,
        width: int = 112,
        height: int = 10,
    ):
        super().__init__(parent)
        self._value = max(0.0, min(100.0, value))
        self._color = color
        self.setFixedSize(width, height)

    def set_value(self, value: float, color: str | None = None) -> None:
        self._value = max(0.0, min(100.0, value))
        if color:
            self._color = color
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = self.height() / 2
        track = self.rect().adjusted(0, 0, -1, -1)

        painter.setPen(QPen(QColor(theme.LINE), 1))
        painter.setBrush(QColor("#010805"))
        painter.drawRoundedRect(track, radius, radius)

        painter.setPen(QPen(QColor(theme.rgba(theme.GREEN, 0.14)), 1))
        for tick in (25, 50, 75):
            x = int(track.width() * tick / 100)
            painter.drawLine(x, track.top() + 2, x, track.bottom() - 2)

        fill_width = int(track.width() * self._value / 100)
        if fill_width:
            fill = track.adjusted(0, 0, fill_width - track.width(), 0)
            base = QColor(self._color)
            gradient = QLinearGradient(fill.left(), 0, fill.right(), 0)
            gradient.setColorAt(0.0, base.darker(190))
            gradient.setColorAt(0.72, base)
            gradient.setColorAt(1.0, base.lighter(138))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            painter.drawRoundedRect(fill, radius, radius)
            cap = min(fill.width(), max(3, int(radius * 1.4)))
            painter.setBrush(QColor("#F0FFF5"))
            painter.drawRoundedRect(fill.right() - cap + 1, fill.top() + 2, cap, fill.height() - 4, 2, 2)


def _percent_value(text: str) -> float | None:
    match = PERCENT_RE.search(str(text))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _display_value(label: str, value: object) -> str:
    """Render ratio-style growth and margin fields as readable percentages."""
    text = str(value)
    if "%" in text:
        return text
    lowered = str(label).lower()
    if "trend" in lowered or not any(word in lowered for word in ("growth", "margin")):
        return text
    try:
        ratio = float(text)
    except (TypeError, ValueError):
        return text
    if -5.0 <= ratio <= 5.0:
        return f"{ratio * 100:.2f}%"
    return text


def _bar_value(text: str) -> float | None:
    """Return a 0-100 fill for percentages and x/100 score rows."""
    percent = _percent_value(text)
    if percent is not None:
        return abs(percent)
    score = re.search(r"([+-]?\d+(?:\.\d+)?)\s*/\s*100\b", str(text))
    if score:
        try:
            return max(0.0, min(100.0, float(score.group(1))))
        except ValueError:
            return None
    return None


def _wrap_text(text: str) -> str:
    """Add invisible break opportunities to otherwise unbreakable data.

    QLabel only wraps at whitespace by default, so a long DCF number or a
    pasted identifier can still overflow a narrow report pane. Zero-width
    spaces let the label wrap inside long tokens without changing the visible
    figures or prose.
    """
    text = str(text)
    if not text or "\u200b" in text:
        return text

    def chunk(match: re.Match[str]) -> str:
        token = match.group(0)
        return "\u200b".join(token[index:index + 12] for index in range(0, len(token), 12))

    text = re.sub(r"\S{20,}", chunk, text)
    return re.sub(r"([,/|:;=])", lambda match: match.group(1) + "\u200b", text)


def _finance_pairs(text: str) -> list[tuple[str, str]]:
    """Turn 'ROE: 1%, Net Margin: 2%' into separate report rows."""
    if ", " not in text or ":" not in text:
        return []
    pairs: list[tuple[str, str]] = []
    for part in text.split(", "):
        match = FINANCE_RE.match(part.strip())
        if not match:
            return []
        pairs.append((match.group(1), match.group(2)))
    return pairs if len(pairs) > 1 else []


def _mapping_lines(payload: object, depth: int = 0) -> list[str]:
    """Readable fallback for any structured payload, never raw JSON."""
    prefix = "  " * depth
    if isinstance(payload, dict):
        lines: list[str] = []
        for key, value in payload.items():
            label = str(key).replace("_", " ").title()
            if isinstance(value, dict):
                lines.append(f"{prefix}{label.upper()}")
                lines.extend(_mapping_lines(value, depth + 1))
            elif isinstance(value, (list, tuple)):
                text = " · ".join(str(item) for item in value)
                lines.append(f"{prefix}{label:<26} {text or 'n/a'}")
            else:
                lines.append(f"{prefix}{label:<26} {value if value is not None else 'n/a'}")
        return lines
    if isinstance(payload, (list, tuple)):
        lines = []
        for item in payload:
            lines.extend(_mapping_lines(item, depth) if isinstance(item, (dict, list, tuple)) else [f"{prefix}{item}"])
        return lines
    return [f"{prefix}{payload}"]


class MetricRow(QWidget):
    """A report line: label, human value, and a bar for percentages or scores."""

    def __init__(self, label: str, value: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._bar_color: str | None = None
        self._bar: MiniBar | None = None
        text = _display_value(label, value)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.key = QLabel(str(label))
        self._key_width = 112
        self.key.setFixedWidth(self._key_width)
        self.key.setWordWrap(True)
        self.key.setFont(theme.font(9, QFont.Weight.DemiBold, mono=True))
        self.key.setStyleSheet(f"color: {theme.MUTED};")
        self.key.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.key, 0, Qt.AlignmentFlag.AlignTop)

        fill = _bar_value(text)
        if fill is not None:
            self._bar_color = self._tone_for(text)
            self._bar = MiniBar(fill, self._bar_color, width=84, height=9)
            layout.addWidget(self._bar, 0, Qt.AlignmentFlag.AlignTop)

        self.value = QLabel(_wrap_text(text))
        self.value.setWordWrap(True)
        self.value.setMinimumWidth(0)
        self.value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.MinimumExpanding)
        self.value.setFont(theme.font(11))
        self.value.setTextFormat(Qt.TextFormat.PlainText)
        self._paint_value(text, self._bar_color)
        self.value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.value.setToolTip(text if _wrap_text(text) != text else "")
        layout.addWidget(self.value, 1, Qt.AlignmentFlag.AlignTop)

    def resizeEvent(self, event) -> None:  # noqa: N802
        """Use a wider label column when the report pane has room."""
        target = max(96, min(138, int(self.width() * 0.28)))
        if target != self._key_width:
            self._key_width = target
            self.key.setFixedWidth(target)
        super().resizeEvent(event)

    @staticmethod
    def _tone_for(text: str, fallback: str | None = None) -> str:
        upper = text.strip().upper()
        if "BEARISH" in upper or upper.startswith(("-", "▼")):
            return theme.RED
        if "BULLISH" in upper or upper.startswith(("+", "▲")):
            return theme.GREEN
        return fallback or theme.BLUE

    def _paint_value(self, text: str, color: str | None = None) -> None:
        tone = color or theme.MUTED
        upper = text.strip().upper()
        if upper in SIGNAL_COLORS:
            tone = SIGNAL_COLORS[upper]
        self.value.setStyleSheet(f"color: {tone if tone != theme.MUTED else theme.TEXT};")

    def set_value(self, text: str, *, color: str | None = None) -> None:
        text = _display_value(self.key.text(), text)
        self.value.setText(_wrap_text(text))
        self.value.setToolTip(text if _wrap_text(text) != text else "")
        fill = _bar_value(text)
        if self._bar is not None and fill is not None:
            tone = color or self._tone_for(text)
            self._bar.set_value(fill, tone)
            self._paint_value(text, tone)
        else:
            self._paint_value(text, color)


class ElidedLabel(QLabel):
    """A single-line label that never forces the card wider."""

    def __init__(self, text: str = "", color: str = theme.DIM, parent: QWidget | None = None):
        super().__init__(parent)
        self._text = text
        self._color = color
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def set_text(self, text: str, color: str | None = None) -> None:
        self._text = text
        if color:
            self._color = color
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setFont(self.font())
        painter.setPen(QColor(self._color))
        metrics = QFontMetrics(self.font())
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(self._text, Qt.TextElideMode.ElideRight, self.width()),
        )


class _Clickable(QWidget):
    clicked = Signal()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class AnalystCard(QFrame):
    """One analyst row: identity, state, signal, confidence and expandable detail."""

    def __init__(self, name: str, role: str = "", accent: str = theme.ORANGE, parent: QWidget | None = None):
        super().__init__(parent)
        self.state = "pending"
        self.terminal_failure = False
        self._failure_note = ""
        self.name = name
        self.setObjectName("AnalystCard")
        self.setStyleSheet(
            f"QFrame#AnalystCard {{ background: {theme.RAISED}; border: 1px solid {theme.LINE}; border-radius: 10px; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._head = _Clickable()
        self._head.setCursor(Qt.CursorShape.PointingHandCursor)
        head = QVBoxLayout(self._head)
        head.setContentsMargins(10, 9, 10, 8)
        head.setSpacing(3)

        top = QHBoxLayout()
        top.setSpacing(5)
        self.dot = QLabel("●")
        self.dot.setFixedWidth(12)
        self.dot.setStyleSheet(f"color: {theme.DIM}; font-size: 11px;")
        title = QLabel(name)
        title.setFont(theme.font(12, QFont.Weight.DemiBold))
        self.role = ElidedLabel(role, theme.DIM)
        self.role.setFont(theme.font(10))
        self.activity = ElidedLabel("PENDING", theme.DIM)
        self.activity.setFont(theme.font(9, QFont.Weight.DemiBold, mono=True, spacing=0.8))
        self.activity.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.signal = Pill("—", theme.DIM)
        self.stamp = QLabel("")
        self.stamp.setFont(theme.font(9, mono=True))
        self.stamp.setStyleSheet(f"color: {theme.DIM};")
        self.chevron = QLabel("▸")
        self.chevron.setStyleSheet(f"color: {theme.DIM};")

        top.addWidget(self.dot)
        top.addWidget(title)
        top.addWidget(self.role, 1)
        top.addWidget(self.activity)
        top.addWidget(self.signal)
        top.addWidget(self.stamp)
        top.addWidget(self.chevron)
        head.addLayout(top)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self.confidence = QLabel("")
        self.confidence.setFont(theme.font(9, mono=True))
        self.confidence.setStyleSheet(f"color: {theme.DIM};")
        self.bar = MiniBar(0, theme.DIM)
        bottom.addWidget(self.bar)
        bottom.addWidget(self.confidence)
        bottom.addStretch(1)
        head.addLayout(bottom)

        root.addWidget(self._head)

        self.body = QWidget()
        self.body.hide()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(12, 0, 12, 12)
        self.body_layout.setSpacing(6)
        root.addWidget(self.body)

        self._head.clicked.connect(self.toggle)
        self._role_text = role
        self._set_expanded(False)

    # -- state ---------------------------------------------------------

    def set_state(self, state: str, note: str = "", *, stamp: bool = True) -> None:
        was = self.state
        self.state = state
        color = STATE_COLORS.get(state, theme.DIM)
        self.dot.setStyleSheet(f"color: {color}; font-size: 11px;")
        self.activity.set_text(state.upper(), color)
        self.role.set_text(note or self._role_text, theme.BLUE if state == "running" and note else theme.DIM)
        if stamp and state in {"done", "failed", "cancelled"} and not self.stamp.text():
            self.stamp.setText(datetime.now().strftime("%H:%M:%S"))
        if state == "running" and was != "running":
            self.chevron.setStyleSheet(f"color: {color};")

    def set_result(self, signal: str, confidence: float, body: list[str]) -> None:
        signal = (signal or "").upper()
        color = SIGNAL_COLORS.get(signal, theme.DIM)
        self.signal.set_state(signal or "—", color)
        self.confidence.setText(f"{confidence:.1f}%")
        self.bar.set_value(confidence, color)
        self._render(body)
        if self.terminal_failure:
            self.set_state("failed", self._failure_note or "engine reported a failure")
        else:
            self.set_state("done", "")
        if body:
            self._set_expanded(True)

    def set_error(self, summary: str, detail: list[str]) -> None:
        self.terminal_failure = True
        self._failure_note = summary
        self.signal.set_state("FAILED", theme.RED)
        self.confidence.setText("")
        self.bar.set_value(0, theme.RED)
        body = [summary] + [line for line in detail if line.strip()]
        self._render(body)
        self.set_state("failed", summary)
        self._set_expanded(True)

    # -- rendering -----------------------------------------------------

    def _render(self, lines: list[str]) -> None:
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        expanded: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(("{", "[")):
                payload = None
                try:
                    payload = json.loads(stripped)
                except ValueError:
                    try:
                        payload = ast.literal_eval(stripped)
                    except (ValueError, SyntaxError):
                        payload = None
                if isinstance(payload, (dict, list)):
                    expanded.extend(_mapping_lines(payload))
                    continue
            expanded.append(line)

        for line in expanded:
            text = line.rstrip()
            stripped = text.strip()
            if not stripped:
                spacer = QWidget()
                spacer.setFixedHeight(3)
                self.body_layout.addWidget(spacer)
                continue
            if SECTION_RE.match(stripped):
                heading = QLabel(stripped.upper())
                heading.setFont(theme.font(9, QFont.Weight.DemiBold, mono=True, spacing=1.4))
                heading.setStyleSheet(f"color: {theme.MUTED};")
                self.body_layout.addWidget(heading)
                continue
            match = KV_RE.match(stripped) or KV_LABEL_RE.match(stripped)
            if match:
                label = match.group(1).strip()
                value = match.group(2).strip()
                pairs = _finance_pairs(value)
                if pairs:
                    for sub_label, sub_value in pairs:
                        self.body_layout.addWidget(MetricRow(sub_label, sub_value))
                else:
                    self.body_layout.addWidget(MetricRow(label, value))
            else:
                label = QLabel(_wrap_text(stripped))
                label.setWordWrap(True)
                label.setMinimumWidth(0)
                label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.MinimumExpanding)
                label.setFont(theme.font(11))
                label.setStyleSheet(f"color: {theme.rgba(theme.TEXT, 0.86)};")
                label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                label.setToolTip(stripped if _wrap_text(stripped) != stripped else "")
                self.body_layout.addWidget(label)

    def toggle(self) -> None:
        self._set_expanded(not self.body.isVisible())

    def _set_expanded(self, expanded: bool) -> None:
        self.body.setVisible(expanded and self.body_layout.count() > 0)
        self.chevron.setText("▾" if expanded and self.body_layout.count() else "▸")

    def expand(self, expanded: bool) -> None:
        self._set_expanded(expanded)


class DecisionCard(QFrame):
    def __init__(self, accent: str = theme.ORANGE, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DecisionCard")
        self.setStyleSheet(
            f"QFrame#DecisionCard {{ background: {theme.rgba(accent, 0.07)}; border: 1px solid {theme.rgba(accent, 0.4)}; border-radius: 10px; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 11, 14, 12)
        root.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(section("FUND DECISION", accent))
        top.addStretch(1)
        self.action = Pill("—", theme.DIM)
        top.addWidget(self.action)
        root.addLayout(top)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.qty = QLabel("")
        self.qty.setFont(theme.font(10, mono=True))
        self.qty.setWordWrap(True)
        self.qty.setMinimumWidth(0)
        self.qty.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.conf = QLabel("")
        self.conf.setFont(theme.font(10, mono=True))
        self.conf.setWordWrap(True)
        self.conf.setMinimumWidth(0)
        self.conf_bar = MiniBar(0, theme.GREEN, width=96, height=9)
        self.qty.setStyleSheet(f"color: {theme.MUTED};")
        self.conf.setStyleSheet(f"color: {theme.MUTED};")
        row.addWidget(self.qty, 1)
        row.addWidget(self.conf)
        row.addWidget(self.conf_bar, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(0)
        root.addLayout(row)

        self.rationale = QLabel("")
        self.rationale.setWordWrap(True)
        self.rationale.setMinimumWidth(0)
        self.rationale.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.MinimumExpanding)
        self.rationale.setFont(theme.font(11))
        self.rationale.setStyleSheet(f"color: {theme.rgba(theme.TEXT, 0.86)};")
        self.rationale.hide()
        root.addWidget(self.rationale)

    def set_fields(self, action: str, quantity: str, confidence: str, rationale: list[str]) -> None:
        action = (action or "").upper()
        color = theme.GREEN if action in {"BUY", "COVER"} else theme.RED if action in {"SELL", "SHORT"} else theme.YELLOW
        self.action.set_state(action or "—", color)
        qty_text = f"QTY {quantity}" if quantity else ""
        conf_text = f"CONF {confidence}" if confidence else ""
        self.qty.setText(_wrap_text(qty_text))
        self.conf.setText(_wrap_text(conf_text))
        self.qty.setToolTip(quantity)
        fill = _percent_value(confidence) or 0.0
        self.conf_bar.set_value(abs(fill), color)
        text = " ".join(rationale).strip()
        self.rationale.setText(_wrap_text(text))
        self.rationale.setToolTip(text if _wrap_text(text) != text else "")
        self.rationale.setVisible(bool(text))


class RunSection(QFrame):
    """All analyst cards for one ticker run."""

    def __init__(self, ticker: str, mode: str, index: int, total: int, names: list[str], roster: dict[str, Analyst], accent: str = theme.ORANGE, parent: QWidget | None = None):
        super().__init__(parent)
        self.ticker = ticker
        self.accent = accent
        self.roster = roster
        self.cards: dict[str, AnalystCard] = {}
        self._final = False
        self.decision: DecisionCard | None = None

        self.setObjectName("RunSection")
        self.setStyleSheet(
            f"QFrame#RunSection {{ background: {theme.PANEL}; border: 1px solid {theme.LINE}; border-radius: 12px; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 13, 14, 14)
        root.setSpacing(9)

        head = QHBoxLayout()
        head.setSpacing(10)
        symbol = QLabel(ticker)
        symbol.setFont(theme.font(16, QFont.Weight.Bold, mono=True))
        symbol.setStyleSheet(f"color: {accent};")
        mode_label = QLabel(mode)
        mode_label.setObjectName("Hint")
        mode_label.setWordWrap(True)
        mode_label.setMinimumWidth(0)
        mode_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.progress = QLabel("")
        self.progress.setFont(theme.font(9, QFont.Weight.DemiBold, mono=True, spacing=0.8))
        self.progress.setStyleSheet(f"color: {theme.MUTED};")
        self.state = Pill("QUEUED", theme.DIM)
        head.addWidget(symbol)
        head.addWidget(mode_label)
        head.addStretch(1)
        head.addWidget(self.progress)
        head.addWidget(self.state)
        root.addLayout(head)

        self.cards_layout = QVBoxLayout()
        self.cards_layout.setSpacing(6)
        root.addLayout(self.cards_layout)

        for name in names:
            self.card_for(name)
        self.refresh()

    def card_for(self, name: str) -> AnalystCard:
        key = name.upper()
        if key in self.cards:
            return self.cards[key]
        analyst = self.roster.get(key)
        card = AnalystCard(analyst.name if analyst else name, analyst.role if analyst else "", self.accent)
        self.cards[key] = card
        self.cards_layout.addWidget(card)
        self.refresh()
        return card

    def match(self, name: str) -> AnalystCard | None:
        """Find an existing selected-analyst card; never invent a new one."""
        key = re.sub(r"\s+", " ", str(name)).strip().upper()
        if key in self.cards:
            return self.cards[key]
        for card_key, card in self.cards.items():
            if card_key in key or key in card_key:
                return card
        return None

    def ensure_decision(self) -> DecisionCard:
        if self.decision is None:
            self.decision = DecisionCard(self.accent)
            self.cards_layout.addWidget(self.decision)
        return self.decision

    def refresh(self) -> None:
        total = len(self.cards)
        done = sum(1 for card in self.cards.values() if card.state == "done")
        failed = sum(1 for card in self.cards.values() if card.state == "failed")
        running = any(card.state == "running" for card in self.cards.values())
        self.progress.setText(f"{done}/{total} COMPLETE" + (f" · {failed} FAILED" if failed else ""))
        if self._final:
            return
        if failed:
            self.state.set_state("ERROR", theme.RED)
        elif count := sum(1 for card in self.cards.values() if card.state in {"done", "skipped", "cancelled"}):
            if count == total:
                self.state.set_state("COMPLETE", theme.GREEN)
            elif running:
                self.state.set_state("RUNNING", theme.BLUE)
        elif running:
            self.state.set_state("RUNNING", theme.BLUE)
        else:
            self.state.set_state("QUEUED", theme.DIM)

    def finalize(self, code: int, stopped: bool) -> None:
        self._final = True
        for card in self.cards.values():
            if card.state in {"pending", "running"}:
                if stopped or code == 130:
                    card.set_state("cancelled", "run stopped")
                elif code != 0:
                    card.set_state("failed", "engine exited before a result")
                else:
                    card.set_state("skipped", "no result returned")
        done = sum(1 for card in self.cards.values() if card.state == "done")
        if stopped or code == 130:
            self.state.set_state("STOPPED", theme.YELLOW)
        elif code != 0:
            self.state.set_state("FAILED", theme.RED)
        else:
            self.state.set_state("COMPLETE", theme.GREEN)
        failed = sum(1 for card in self.cards.values() if card.state == "failed")
        self.progress.setText(
            f"{done}/{len(self.cards)} COMPLETE" + (f" · {failed} FAILED" if failed else "")
        )


class ResearchStream(Card):
    """Structured replacement for the plain research console."""

    submitted = Signal(str)
    decision_ready = Signal(str, str, str, object)

    def __init__(self, title: str = "RESEARCH", accent: str = theme.ORANGE, parent: QWidget | None = None):
        super().__init__(pad=16, spacing=10, parent=parent)
        self._accent = accent
        self._roster: dict[str, Analyst] = {}
        self._section: RunSection | None = None
        self._runs: list[RunSection] = []
        self._parser: str | None = None
        self._detail: dict | None = None
        self._error: list[str] = []
        self._decision_data: dict = {}
        self._alerted: set[tuple[str, str, str]] = set()

        head = QHBoxLayout()
        head.setSpacing(8)
        heading = section(title, theme.MUTED)
        heading.setMinimumWidth(0)
        heading.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        head.addWidget(heading, 1)
        self.status = Pill("IDLE", theme.DIM)
        head.addWidget(self.status)
        self.expand_btn = _chip("EXPAND")
        self.raw_btn = _chip("RAW", checkable=True)
        self.raw_btn.setToolTip("Show the untouched engine output")
        clear_btn = _chip("CLEAR")
        head.addWidget(self.expand_btn)
        head.addWidget(self.raw_btn)
        head.addWidget(clear_btn)
        self.body.addLayout(head)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._scroll.viewport().setAutoFillBackground(False)

        self._canvas = QWidget()
        self._canvas.setStyleSheet("background: transparent;")
        self._canvas.setMinimumSize(0, 0)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._column = QVBoxLayout(self._canvas)
        self._column.setContentsMargins(0, 0, 4, 0)
        self._column.setSpacing(10)

        self._empty = QLabel("Pick a mode and run. Analyst results appear here as the engine reports them.")
        self._empty.setObjectName("Hint")
        self._empty.setWordWrap(True)
        self._column.addWidget(self._empty)
        self._column.addStretch(1)
        self._scroll.setWidget(self._canvas)
        self.body.addWidget(self._scroll, 1)

        self.raw = QPlainTextEdit()
        self.raw.setObjectName("Console")
        self.raw.setReadOnly(True)
        self.raw.setMaximumBlockCount(8000)
        self.raw.setFont(theme.font(10, mono=True))
        self.raw.setFixedHeight(150)
        self.raw.hide()
        self.body.addWidget(self.raw)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self._input = QLineEdit()
        self._input.setObjectName("ConsoleInput")
        self._input.setPlaceholderText("Engine prompt (y / n / YES)")
        self._input.setEnabled(False)
        self._input.returnPressed.connect(self._send)
        send = _chip("SEND")
        send.clicked.connect(self._send)
        input_row.addWidget(self._input, 1)
        input_row.addWidget(send)
        self.body.addLayout(input_row)

        self.expand_btn.clicked.connect(self._expand_all)
        self.raw_btn.toggled.connect(self.raw.setVisible)
        clear_btn.clicked.connect(self.clear)

    # -- roster --------------------------------------------------------

    def set_roster(self, roster: dict[str, Analyst]) -> None:
        self._roster = roster

    # -- lifecycle -----------------------------------------------------

    def begin_run(self, ticker: str, mode: str, names: list[str], index: int, total: int) -> RunSection:
        self._empty.hide()
        section = RunSection(ticker, mode, index, total, names, self._roster, self._accent)
        self._runs.append(section)
        self._sections_append(section)
        self._section = section
        self.status.set_state(f"RUN {index}/{total}", self._accent)
        self._input.setEnabled(True)
        self._parser = None
        self._detail = None
        self._decision_data = {}
        self._alerted.clear()
        QTimer.singleShot(0, self._scroll_to_bottom)
        return section

    def _sections_append(self, section: RunSection) -> None:
        self._column.insertWidget(self._column.count() - 1, section)

    def show_command(self, command: str) -> None:
        self.raw.appendPlainText("$ " + str(command))

    def progress_event(self, payload: dict) -> None:
        """Apply a structured agent-progress event emitted by the engine."""
        if self._section is None or not isinstance(payload, dict):
            return
        agent = str(payload.get("agent") or "")
        ticker = str(payload.get("ticker") or "")
        status = str(payload.get("status") or "").strip()
        if not agent:
            return
        if ticker and ticker.upper() != self._section.ticker.upper():
            return

        name = agent.replace("_agent", "").replace("_", " ").title()
        if name.lower().startswith(("risk management", "portfolio manager", "portfolio management")):
            return
        card = self._section.match(name)
        if card is None:
            return

        lowered = status.lower()
        if lowered == "done":
            if card.state != "done" and not card.terminal_failure:
                card.set_state("done", "engine reported done")
        elif lowered.startswith("failed"):
            card.terminal_failure = True
            card._failure_note = status[:120] or "engine failure"
            card.set_state("failed", card._failure_note)
        elif lowered.startswith("error"):
            card.set_state("running", status[:90] or "retrying")
        else:
            card.set_state("running", status[:90] or "working")
        self.set_status("RUNNING", theme.BLUE)
        self._section.refresh()

    def end_run(self, code: int, *, stopped: bool = False) -> None:
        self._flush_detail()
        self._flush_decision()
        if self._section is not None:
            self._section.finalize(code, stopped)
        if stopped or code == 130:
            self.status.set_state("STOPPED", theme.YELLOW)
        elif code == 0:
            self.status.set_state("DONE", theme.GREEN)
        else:
            self.status.set_state(f"FAILED {code}", theme.RED)
        self._input.setEnabled(False)
        self._parser = None

    def set_status(self, text: str, color: str) -> None:
        self.status.set_state(text, color)

    def clear(self) -> None:
        for run in self._runs:
            self._column.removeWidget(run)
            run.deleteLater()
        self._runs.clear()
        self._section = None
        self._parser = None
        self._detail = None
        self._error = []
        self._alerted.clear()
        self.raw.clear()
        self.raw.hide()
        self.raw_btn.setChecked(False)
        self._empty.show()
        self.status.set_state("IDLE", theme.DIM)
        self._input.clear()
        self._input.setEnabled(False)

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _expand_all(self) -> None:
        if self._section is None:
            return
        expand = any(not card.body.isVisible() for card in self._section.cards.values())
        for card in self._section.cards.values():
            card.expand(expand)
        self.expand_btn.setText("COLLAPSE" if expand else "EXPAND")

    # -- input ---------------------------------------------------------

    def _send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self.raw.appendPlainText(f"» {text}")
        self.submitted.emit(text)

    # -- parsing -------------------------------------------------------

    def feed(self, line: str) -> None:
        text = str(line)
        self.raw.appendPlainText(text)
        self._consume(text.rstrip())

    def write(self, text: str, _kind: str | None = None) -> None:
        self.feed(text)

    def _pretty(self, raw: str) -> str:
        cleaned = re.sub(r"[║╔╗╚╝═─┌┐└┘│]+", " ", str(raw))
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        analyst = self._roster.get(cleaned.upper())
        return analyst.name if analyst else cleaned.title()

    def _consume(self, line: str) -> None:
        stripped = line.strip()
        if not stripped:
            return

        if self._parser == "error":
            self._error.append(stripped)
            if EXC_RE.match(stripped):
                self._show_error()
            return
        if stripped.startswith("Traceback (most recent call last):"):
            self._parser = "error"
            self._error = [stripped]
            return

        progress = PROGRESS_RE.match(stripped)
        if progress:
            self._on_progress(*progress.groups())
            return

        if "📈" in stripped:
            match = DETAIL_RE.search(stripped)
            if match:
                self._flush_detail()
                self._begin_detail(self._pretty(match.group(1)))
                return

        if self._parser == "detail" and self._detail is not None:
            signal = SIGNAL_RE.search(stripped)
            if signal:
                self._detail["signal"] = signal.group(1).upper()
                return
            confidence = CONF_RE.search(stripped)
            if confidence:
                try:
                    self._detail["confidence"] = float(confidence.group(1))
                except ValueError:
                    pass
                return
            if "┌─ DETAILS" in stripped:
                self._parser = "body"
                return

        if self._parser == "body" and self._detail is not None:
            if not self._body_ends(stripped):
                self._detail["body"].append(stripped)
                return
            self._flush_detail()

        if "🎯 FUND DECISION" in stripped:
            self._flush_detail()
            if self._section is not None:
                self._section.ensure_decision()
            self._parser = "decision"
            self._decision_data = {"action": "", "quantity": "", "confidence": "", "rationale": []}
            return

        if self._parser == "decision":
            if stripped.startswith("╔") or "📊 PORTFOLIO SUMMARY" in stripped or "🧠 AI HEDGE FUND" in stripped:
                self._flush_decision()
                return
            self._on_decision_line(stripped)
            return

    @staticmethod
    def _body_ends(line: str) -> bool:
        return (
            line.startswith(("╔", "╚", "║"))
            or line.startswith("┌─")
            or "🎯" in line
            or "📊" in line
            or "🧠" in line
        )

    def _on_progress(self, symbol: str, name: str, ticker: str, status: str) -> None:
        if self._section is None or self._section.ticker.upper() != ticker.upper():
            return
        card = self._section.match(self._pretty(name))
        if card is None:
            return
        label = status.strip()
        if symbol == "✓" or label.lower() == "done":
            card.set_state("done", "")
        elif symbol == "✗" or label.lower() == "error":
            card.set_state("failed", label or "error")
        else:
            card.set_state("running", label or "working")
        self._section.refresh()

    def _begin_detail(self, name: str) -> None:
        self._detail = {"name": name, "signal": "", "confidence": 0.0, "body": []}
        self._parser = "detail"

    def _flush_detail(self) -> None:
        detail, self._detail = self._detail, None
        if self._parser in {"detail", "body"}:
            self._parser = None
        if not detail or self._section is None:
            return
        card = self._section.match(detail["name"])
        if card is None:
            return
        card.set_result(detail.get("signal", ""), float(detail.get("confidence") or 0.0), detail.get("body") or [])
        self._section.refresh()

    def _on_decision_line(self, line: str) -> None:
        # Strip both sides: terminal report boxes put a trailing ║ on every
        # wrapped line, which previously leaked into the rationale.
        text = line.strip().strip("║╔╗╚╝═─┌┐└┘│ \t")
        if not text or all(char in "╔╚║═─┌└├ 「」" for char in text):
            return
        if self._section is not None and text.upper() == self._section.ticker.upper():
            return
        if text.startswith("ACTION"):
            self._decision_data["action"] = text.split(None, 1)[1] if len(text.split(None, 1)) > 1 else ""
        elif text.startswith("QUANTITY"):
            parts = text.split(None, 1)
            self._decision_data["quantity"] = parts[1].strip() if len(parts) > 1 else ""
        elif text.startswith("CONFIDENCE"):
            parts = text.split(None, 1)
            self._decision_data["confidence"] = parts[1].strip() if len(parts) > 1 else ""
        elif text.startswith("DECISION RATIONALE") or text.startswith("┌─"):
            return
        elif not text.startswith(("QUANTITY", "CONFIDENCE")):
            self._decision_data["rationale"].append(text)

    def _flush_decision(self) -> None:
        if self._parser == "decision":
            self._parser = None
        data, self._decision_data = self._decision_data, {}
        if not data or self._section is None or self._section.decision is None:
            return
        action = data.get("action", "")
        confidence = data.get("confidence", "")
        rationale = data.get("rationale") or []
        self._section.decision.set_fields(
            action,
            data.get("quantity", ""),
            confidence,
            rationale,
        )
        key = (self._section.ticker, str(action).upper(), str(confidence))
        if action and key not in self._alerted:
            self._alerted.add(key)
            self.decision_ready.emit(self._section.ticker, action, confidence, rationale)

    def _show_error(self) -> None:
        buffer = self._error
        self._error = []
        self._parser = None
        if self._section is None:
            return
        summary = next((line for line in reversed(buffer) if EXC_RE.match(line)), "Engine error")
        card = self._section.card_for("Engine error")
        card.set_error(summary, buffer[-24:])
        self._section.refresh()
