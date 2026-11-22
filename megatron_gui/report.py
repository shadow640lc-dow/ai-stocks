"""Structured report stream for scanner and executor engines.

MEGACALLS and MEGACRYPTO print finance reports and decision tables to the
terminal. This widget turns those real lines into readable sections, metric
rows and neon percentage bars, while keeping the raw engine output one click
away. It never invents values; unparsed lines remain readable notes.
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
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
from .components import Card, Pill, section
from .research import MetricRow

BOX_RE = re.compile(r"^[\s│║┌└├╔╚╭╰╮╯─═]+|[\s│║┐┘┤╗╝╮╯─═]+$")
BOX_ANY_RE = re.compile(r"[│║┌└├╔╚╭╰╮╯─═╠╣┐┘┤╗╝]")
BLOCK_RE = re.compile(r"[█░▓▒]+")
SYMBOL_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]")
SEPARATOR_RE = re.compile(r"^[\s\-_=─═]{4,}$")
SECTION_RE = re.compile(r"^[A-Z][A-Z0-9 /&'()\-—.]{3,64}$")
PAIR_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 /&()._%#\-]{1,34})\s*:\s*(.+)$")
COLUMN_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 /&()._%#\-]{2,32})\s{2,}(.+)$")
RANK_RE = re.compile(r"^#(\d+)\s+(.+)$")
PROGRESS_RE = re.compile(r"^\[\s*\d+\s*/\s*\d+\s*\]\s*([A-Z][A-Z0-9.\-]{0,9})\s+(.+)$")
HUNTER_RE = re.compile(
    r"^#(\d+)\s+([A-Z][A-Z0-9.\-]{0,9})\s+Hunter\s+([\d.]+)\s*(.*)$",
    re.IGNORECASE,
)
OPTION_CHAIN_RE = re.compile(r"^(?:[└├]\s*[─\-]?\s*)?([✓✗])\s*(\d+)\s+candidates?\s*(?:\|\s*best\s*([\d.]+))?$")


def _clean(line: str) -> str:
    text = str(line).replace("\r", "").replace("\t", "    ")
    text = SYMBOL_RE.sub("", text)
    text = BLOCK_RE.sub(" ", text)
    text = BOX_ANY_RE.sub(" ", text)
    text = BOX_RE.sub("", text)
    text = re.sub(r"\s{2,}", "  ", text)
    return text.strip()


def _split_segments(text: str) -> list[tuple[str, str]]:
    """Turn ``Premium 4.89% | Annualized 54.11%`` into labelled rows."""
    if " | " not in text:
        return []
    rows: list[tuple[str, str]] = []
    for raw in text.split(" | "):
        part = raw.strip()
        if not part:
            return []
        if "→" in part:
            rows.append(("Price path", part))
            continue
        match = re.match(r"^([A-Za-z][A-Za-z /]{1,24})\s+(.+)$", part)
        if not match:
            return []
        label = match.group(1).strip()
        value = match.group(2).strip()
        if "=" in label:
            label, _, extra = label.partition("=")
            value = f"{extra} {value}".strip()
        rows.append((label, value))
    return rows if len(rows) > 1 else []


class ReportRunCard(QFrame):
    """One structured engine run."""

    def __init__(self, title: str, subtitle: str, accent: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.accent = accent
        self.state = "running"
        self._last_heading = ""
        self.setObjectName("ReportRun")
        self.setStyleSheet(
            f"QFrame#ReportRun {{ background: {theme.PANEL}; border: 1px solid {theme.LINE}; "
            f"border-radius: 12px; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 16)
        root.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(10)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {accent}; font-size: 12px;")
        self.title = QLabel(title)
        self.title.setFont(theme.font(14, QFont.Weight.Bold, mono=True, spacing=1.0))
        self.title.setStyleSheet(f"color: {accent};")
        self.title.setMinimumWidth(0)
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("Hint")
        self.subtitle.setWordWrap(True)
        self.subtitle.setMinimumWidth(0)
        self.subtitle.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.state_pill = Pill("RUNNING", theme.BLUE)
        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(2)
        info.addWidget(self.title)
        info.addWidget(self.subtitle)
        head.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
        head.addLayout(info, 1)
        head.addWidget(self.state_pill, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setSpacing(5)
        root.addLayout(self.body)

        self._empty = QLabel("Waiting for the engine's first report line…")
        self._empty.setObjectName("Hint")
        self._empty.setWordWrap(True)
        self.body.addWidget(self._empty)

    def add_heading(self, text: str) -> None:
        heading_text = text.strip().rstrip(":").upper()
        if not heading_text or heading_text == self._last_heading:
            return
        self._last_heading = heading_text
        self._empty.hide()
        spacer = QWidget()
        spacer.setFixedHeight(5)
        self.body.addWidget(spacer)
        heading = QLabel(heading_text)
        heading.setFont(theme.font(9, QFont.Weight.Bold, mono=True, spacing=1.6))
        heading.setStyleSheet(f"color: {theme.MUTED};")
        self.body.addWidget(heading)

    def add_metric(self, label: str, value: str) -> None:
        self._empty.hide()
        self.body.addWidget(MetricRow(label, value))

    def add_note(self, text: str, color: str | None = None) -> None:
        text = text.strip()
        if not text:
            return
        self._empty.hide()
        note = QLabel(text)
        note.setWordWrap(True)
        note.setFont(theme.font(11))
        upper = text.upper()
        tone = color or theme.TEXT
        if "ERROR" in upper or "TRACEBACK" in upper or upper.startswith("✖"):
            tone = theme.RED
        elif "WARNING" in upper or upper.startswith(("⚠", "🛑")):
            tone = theme.YELLOW
        elif "NO TRADE" in upper or "DISABLED" in upper or "RESEARCH-ONLY" in upper:
            tone = theme.GREEN
        elif text.startswith("•"):
            tone = theme.rgba(theme.TEXT, 0.82)
        note.setStyleSheet(f"color: {tone};")
        note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.addWidget(note)

    def add_divider(self) -> None:
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {theme.LINE};")
        self.body.addWidget(line)

    def finish(self, code: int, stopped: bool) -> None:
        self.state = "stopped" if stopped else "done" if code == 0 else "failed"
        if stopped:
            self.state_pill.set_state("STOPPED", theme.YELLOW)
        elif code == 0:
            self.state_pill.set_state("COMPLETE", theme.GREEN)
        else:
            self.state_pill.set_state(f"EXIT {code}", theme.RED)
        self._empty.hide()


class ReportStream(Card):
    """Scrollable structured report with raw-output fallback and stdin."""

    submitted = Signal(str)

    def __init__(self, title: str = "REPORT", accent: str = theme.PURPLE, parent: QWidget | None = None):
        super().__init__(pad=16, spacing=10, parent=parent)
        self._accent = accent
        self._card: ReportRunCard | None = None

        head = QHBoxLayout()
        head.setSpacing(8)
        heading = section(title, theme.MUTED)
        heading.setMinimumWidth(0)
        heading.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        head.addWidget(heading, 1)
        self.status = Pill("IDLE", theme.DIM)
        self.raw_btn = QPushButton("RAW")
        self.raw_btn.setObjectName("Chip")
        self.raw_btn.setCheckable(True)
        self.raw_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.raw_btn.setToolTip("Show the untouched engine output")
        clear_btn = QPushButton("CLEAR")
        clear_btn.setObjectName("Chip")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        head.addWidget(self.status)
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
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(10)

        self._empty = QLabel("Run the engine. Its report appears here as structured finance rows and charts.")
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
        send = QPushButton("SEND")
        send.setObjectName("Chip")
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.clicked.connect(self._send)
        input_row.addWidget(self._input, 1)
        input_row.addWidget(send)
        self.body.addLayout(input_row)

        self.raw_btn.toggled.connect(self.raw.setVisible)
        clear_btn.clicked.connect(self.clear)

    # -- lifecycle -----------------------------------------------------

    def begin(self, title: str, argv: list[str], *, subtitle: str = "") -> ReportRunCard:
        self._empty.hide()
        note = subtitle or "structured live report"
        card = ReportRunCard(title, note, self._accent)
        card.setMaximumWidth(max(240, self._scroll.viewport().width()))
        self._card = card
        self._column.insertWidget(self._column.count() - 1, card)
        self.status.set_state("RUNNING", self._accent)
        self._input.setEnabled(True)
        self.raw.clear()
        self.raw.appendPlainText("$ " + " ".join(argv))
        QTimer.singleShot(0, self._scroll_to_bottom)
        return card

    def set_status(self, text: str, color: str) -> None:
        self.status.set_state(text, color)

    def finish(self, code: int, *, stopped: bool = False) -> None:
        if self._card is not None:
            self._card.finish(code, stopped)
        if stopped or code == 130:
            self.status.set_state("STOPPED", theme.YELLOW)
        elif code == 0:
            self.status.set_state("COMPLETE", theme.GREEN)
        else:
            self.status.set_state(f"EXIT {code}", theme.RED)
        self._input.setEnabled(False)

    def clear(self) -> None:
        if self._card is not None:
            self._column.removeWidget(self._card)
            self._card.deleteLater()
        self._card = None
        self.raw.clear()
        self.raw.hide()
        self.raw_btn.setChecked(False)
        self._empty.show()
        self.status.set_state("IDLE", theme.DIM)
        self._input.clear()
        self._input.setEnabled(False)

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
        text = str(line).rstrip()
        self.raw.appendPlainText(text)
        cleaned = _clean(text)
        if not cleaned or SEPARATOR_RE.match(cleaned):
            return
        if self._card is None:
            self.begin("ENGINE REPORT", [], subtitle="output received")
        self._consume(cleaned)

    def write(self, text: str, _kind: str | None = None) -> None:
        self.feed(text)

    def _consume(self, text: str) -> None:
        assert self._card is not None

        if "Traceback (most recent call last):" in text:
            self._card.add_heading("ENGINE ERROR")
            self._card.add_note(text, theme.RED)
            return

        if text.upper().startswith("CONTRACT DETAIL"):
            self._card.add_heading(text)
            return

        if ":" not in text and SECTION_RE.match(text) and not _looks_like_value(text):
            self._card.add_heading(text)
            return

        hunter = HUNTER_RE.match(text)
        if hunter:
            rank, ticker, score, signal = hunter.groups()
            detail = f"{score}/100"
            if signal.strip():
                detail += f" · {signal.strip()}"
            self._card.add_metric(f"#{rank} {ticker.upper()}", detail)
            return

        progress = PROGRESS_RE.match(text)
        if progress:
            ticker, detail = progress.groups()
            self._card.add_metric(ticker.upper(), detail.strip())
            return

        chain = OPTION_CHAIN_RE.match(text)
        if chain:
            mark, count, best = chain.groups()
            detail = f"{count} candidate(s)"
            if best:
                detail += f" · best {best}/100"
            self._card.add_metric("Option chain", f"{detail}  {mark}")
            return

        segments = _split_segments(text)
        if segments:
            for label, value in segments:
                self._card.add_metric(label, value)
            return

        rank = RANK_RE.match(text)
        if rank:
            self._card.add_metric(f"Rank {rank.group(1)}", rank.group(2).strip())
            return

        pair = PAIR_RE.match(text) or COLUMN_RE.match(text)
        if pair:
            label = pair.group(1).strip()
            value = pair.group(2).strip()
            if value:
                self._card.add_metric(label, value)
                return

        if text.startswith(("•", "⚠", "🛑")):
            self._card.add_note(text)
            return

        self._card.add_note(text)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        width = max(240, self._scroll.viewport().width())
        for card in self._canvas.findChildren(ReportRunCard):
            card.setMaximumWidth(width)

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())


def _looks_like_value(text: str) -> bool:
    """Keep uppercase data rows from being mistaken for headings."""
    if any(char.isdigit() for char in text):
        return True
    return text.upper().startswith(("BUY", "SELL", "LIVE", "OFF", "ON", "SET", "MISSING", "TRUE", "FALSE"))
