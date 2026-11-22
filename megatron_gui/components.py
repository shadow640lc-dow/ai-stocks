"""Reusable MEGATRON widgets: cards, stat tiles, choices, console, toggles."""

from __future__ import annotations

import html

from PySide6.QtCore import QEasingCurve, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import config, theme


# ----------------------------------------------------------------------
# Building blocks
# ----------------------------------------------------------------------

def section(text: str, color: str = theme.MUTED) -> QLabel:
    label = QLabel(text.upper())
    label.setFont(theme.font(9, QFont.Weight.DemiBold, mono=True, spacing=1.6))
    label.setStyleSheet(f"color: {color};")
    return label


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFixedHeight(1)
    return line


def field(label_text: str, widget: QWidget, hint: str | None = None) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(5)
    layout.addWidget(section(label_text, theme.DIM))
    layout.addWidget(widget)
    if hint:
        note = QLabel(hint)
        note.setObjectName("Hint")
        note.setWordWrap(True)
        note.setMinimumWidth(0)
        note.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(note)
    return box


def primary_button(text: str, color: str, *, height: int = 40) -> QPushButton:
    button = QPushButton(text)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setMinimumHeight(height)
    base = QColor(color)
    hover = base.lighter(112).name()
    pressed = base.darker(112).name()
    button.setStyleSheet(
        f"""
        QPushButton {{
            background: {color};
            color: {theme.INK};
            border: 1px solid {color};
            border-radius: 9px;
            padding: 9px 16px;
            font-weight: 700;
            font-size: 12px;
        }}
        QPushButton:hover {{ background: {hover}; border-color: {hover}; }}
        QPushButton:pressed {{ background: {pressed}; }}
        QPushButton:disabled {{
            background: #14171E;
            border-color: #1B2029;
            color: {theme.DIM};
        }}
        """
    )
    return button


def ghost_button(text: str, color: str | None = None, *, height: int = 36) -> QPushButton:
    accent = color or theme.TEXT
    button = QPushButton(text)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setMinimumHeight(height)
    button.setFont(theme.font(10, QFont.Weight.Bold, mono=True, spacing=1.1))
    button.setStyleSheet(
        f"""
        QPushButton {{
            background: transparent;
            color: {accent};
            border: 1px solid {theme.rgba(accent, 0.35)};
            border-radius: 9px;
            padding: 8px 14px;
        }}
        QPushButton:hover {{ background: {theme.rgba(accent, 0.10)}; }}
        QPushButton:disabled {{ color: {theme.DIM}; border-color: #1B2029; }}
        """
    )
    return button


class Card(QFrame):
    def __init__(self, accent: str | None = None, *, pad: int = 18, spacing: int = 12, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(pad, pad, pad, pad)
        self.body.setSpacing(spacing)
        if accent:
            self.setStyleSheet(f"QFrame#Card {{ border-top: 2px solid {accent}; }}")


class Pill(QLabel):
    def __init__(self, text: str = "", color: str = theme.DIM, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_state(text, color)

    def set_state(self, text: str, color: str) -> None:
        self.setText(text)
        self.setFont(theme.font(9, QFont.Weight.Bold, mono=True, spacing=1.2))
        self.setStyleSheet(
            f"""
            QLabel {{
                color: {color};
                background: {theme.rgba(color, 0.12)};
                border: 1px solid {theme.rgba(color, 0.34)};
                border-radius: 9px;
                padding: 3px 9px;
            }}
            """
        )
        # The state text changes after construction (IDLE -> COMPLETE).
        # Keep the pill wide enough instead of clipping the first glyph.
        self.setMinimumWidth(self.fontMetrics().horizontalAdvance(text) + 24)
        self.updateGeometry()


class Stat(Card):
    """Big number tile used on the dashboard and crypto panels."""

    def __init__(self, label: str, value: str = "—", hint: str = "", accent: str = theme.BLUE, parent: QWidget | None = None):
        super().__init__(accent=accent, pad=16, spacing=6, parent=parent)
        self.body.addWidget(section(label, theme.MUTED))
        self.value = QLabel(value)
        self.value.setFont(theme.font(23, QFont.Weight.Bold, mono=True))
        self.value.setStyleSheet(f"color: {accent};")
        self.body.addWidget(self.value)
        self.hint = QLabel(hint)
        self.hint.setObjectName("Hint")
        self.hint.setWordWrap(True)
        self.body.addWidget(self.hint)

    def set(self, value: str, *, color: str | None = None, hint: str | None = None) -> None:
        self.value.setText(value)
        if color:
            self.value.setStyleSheet(f"color: {color};")
        if hint is not None:
            self.hint.setText(hint)


class KeyRow(QWidget):
    """Status line: coloured dot, label, right-aligned value."""

    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(9)
        self.dot = QLabel("●")
        self.name = QLabel(label)
        self.name.setObjectName("Muted")
        self.value = QLabel("—")
        self.value.setFont(theme.font(10, QFont.Weight.DemiBold, mono=True))
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.dot)
        layout.addWidget(self.name)
        layout.addStretch(1)
        layout.addWidget(self.value)

    def set(self, ok: bool, detail: str, *, color: str | None = None) -> None:
        tone = color or (theme.GREEN if ok else theme.RED)
        self.dot.setStyleSheet(f"color: {tone}; font-size: 12px;")
        self.value.setText(detail)
        self.value.setStyleSheet(f"color: {tone};")


class Toggle(QWidget):
    """Animated pill switch."""

    toggled = Signal(bool)

    def __init__(self, on: bool = False, accent: str = theme.GREEN, parent: QWidget | None = None):
        super().__init__(parent)
        self._on = on
        self._progress = 1.0 if on else 0.0
        self._accent = accent
        self.setFixedSize(48, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._step)

    def is_on(self) -> bool:
        return self._on

    def set_on(self, on: bool, *, emit: bool = False) -> None:
        if on == self._on:
            return
        self._on = on
        self._anim.stop()
        self._anim.setStartValue(float(self._progress))
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()
        if emit:
            self.toggled.emit(on)

    def _step(self, value) -> None:
        self._progress = float(value)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_on(not self._on, emit=True)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        p = self._progress

        off = QColor(theme.LINE)
        on = QColor(self._accent)
        track = QColor(
            int(off.red() + (on.red() - off.red()) * p),
            int(off.green() + (on.green() - off.green()) * p),
            int(off.blue() + (on.blue() - off.blue()) * p),
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        diameter = rect.height() - 6
        x = rect.left() + 3 + p * (rect.width() - diameter - 6)
        painter.setBrush(QColor("#F4F7FF"))
        painter.drawEllipse(int(x), rect.top() + 3, diameter, diameter)


class ChoiceRow(QFrame):
    clicked = Signal(str)

    def __init__(self, value: str, title: str, subtitle: str = "", accent: str = theme.ORANGE, tag: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.value = value
        self.accent = accent
        self._selected = False
        self.setObjectName("ChoiceRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(13, 10, 13, 10)
        layout.setSpacing(11)

        self.dot = QLabel("○")
        self.dot.setFont(theme.font(12, mono=True))
        self.dot.setFixedWidth(14)
        layout.addWidget(self.dot)

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(2)
        self.title = QLabel(title)
        self.title.setFont(theme.font(13, QFont.Weight.DemiBold))
        self.title.setMinimumWidth(0)
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        text_box.addWidget(self.title)
        if subtitle:
            self.subtitle = QLabel(subtitle)
            self.subtitle.setObjectName("Hint")
            self.subtitle.setWordWrap(True)
            self.subtitle.setMinimumWidth(0)
            self.subtitle.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            text_box.addWidget(self.subtitle)
        layout.addLayout(text_box, 1)

        if tag:
            badge = QLabel(tag)
            badge.setFont(theme.font(8, QFont.Weight.Bold, mono=True, spacing=1.1))
            badge.setStyleSheet(f"color: {accent};")
            layout.addWidget(badge)

        self._restyle()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._restyle()

    def _restyle(self) -> None:
        if self._selected:
            frame = (
                f"QFrame#ChoiceRow {{ background: {theme.rgba(self.accent, 0.10)}; "
                f"border: 1px solid {theme.rgba(self.accent, 0.55)}; border-radius: 10px; }}"
            )
            self.dot.setStyleSheet(f"color: {self.accent};")
            self.dot.setText("●")
        else:
            frame = (
                f"QFrame#ChoiceRow {{ background: {theme.BG}; border: 1px solid {theme.LINE}; border-radius: 10px; }}"
                f"QFrame#ChoiceRow:hover {{ background: {theme.HOVER}; border-color: #2C3444; }}"
            )
            self.dot.setStyleSheet(f"color: {theme.DIM};")
            self.dot.setText("○")
        self.setStyleSheet(frame + " QLabel { background: transparent; border: none; }")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.value)


class ChoiceGroup(QWidget):
    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str, str, str]], accent: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._rows: list[ChoiceRow] = []
        self._value = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        for value, title, subtitle, tag in options:
            row = ChoiceRow(value, title, subtitle, accent, tag)
            row.clicked.connect(self.select)
            layout.addWidget(row)
            self._rows.append(row)
        if options:
            self.select(options[0][0], announce=False)

    def value(self) -> str:
        return self._value

    def select(self, value: str, *, announce: bool = True) -> None:
        changed = value != self._value
        self._value = value
        for row in self._rows:
            row.set_selected(row.value == value)
        if announce and changed:
            self.changed.emit(value)

    def set_value(self, value: str) -> None:
        self.select(value, announce=False)


class SegmentBar(QFrame):
    """Exclusive segmented control."""

    changed = Signal(str)

    def __init__(self, items: list[tuple[str, str]], accent: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Segment")
        self.setStyleSheet(
            f"QFrame#Segment {{ background: {theme.PANEL}; border: 1px solid {theme.LINE}; border-radius: 10px; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}

        for value, label in items:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFont(theme.font(9, QFont.Weight.Bold, mono=True, spacing=1.2))
            button.setStyleSheet(
                f"""
                QPushButton {{
                    background: transparent;
                    color: {theme.MUTED};
                    border: 1px solid transparent;
                    border-radius: 7px;
                    padding: 7px 14px;
                }}
                QPushButton:hover {{ color: {theme.TEXT}; background: {theme.HOVER}; }}
                QPushButton:checked {{
                    color: {accent};
                    background: {theme.rgba(accent, 0.12)};
                    border-color: {theme.rgba(accent, 0.35)};
                }}
                """
            )
            button.clicked.connect(lambda _checked=False, v=value: self._pick(v))
            self._group.addButton(button)
            layout.addWidget(button)
            self._buttons[value] = button

        if items:
            self._buttons[items[0][0]].setChecked(True)
            self._value = items[0][0]

    def _pick(self, value: str) -> None:
        if value == self._value:
            return
        self._value = value
        self.changed.emit(value)

    def value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        button = self._buttons.get(value)
        if button:
            button.setChecked(True)
            self._value = value


class TickerField(QWidget):
    def __init__(self, accent: str, chips: tuple[str, ...] = ("NVDA", "AMD", "PLTR", "MSFT", "SPY"), parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("NVDA AMD PLTR")
        self.edit.setFont(theme.font(14, QFont.Weight.DemiBold, mono=True, spacing=1.0))
        self.edit.setMinimumHeight(42)
        layout.addWidget(self.edit)

        chip_row = QGridLayout()
        chip_row.setContentsMargins(0, 0, 0, 0)
        chip_row.setHorizontalSpacing(6)
        chip_row.setVerticalSpacing(6)
        for index, symbol in enumerate(chips):
            chip = QPushButton(symbol)
            chip.setObjectName("Chip")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _=False, s=symbol: self._append(s))
            chip_row.addWidget(chip, index // 3, index % 3)
        chip_row.setColumnStretch(3, 1)
        layout.addLayout(chip_row)

        self._accent = accent

    def _append(self, symbol: str) -> None:
        symbols = config.parse_tickers(self.edit.text())
        if symbol not in symbols:
            symbols.append(symbol)
        self.edit.setText(" ".join(symbols))

    def tickers(self) -> list[str]:
        return config.parse_tickers(self.edit.text())

    def text(self) -> str:
        return self.edit.text()


class Console(Card):
    """Streaming engine output with a stdin line for y/N prompts."""

    submitted = Signal(str)

    _COLORS = {
        "out": "#C7D0E1",
        "dim": theme.DIM,
        "cmd": theme.BLUE,
        "ok": theme.GREEN,
        "err": theme.RED,
        "warn": theme.YELLOW,
        "accent": theme.ORANGE,
    }

    def __init__(self, title: str = "CONSOLE", accent: str = theme.BLUE, parent: QWidget | None = None):
        super().__init__(pad=16, spacing=10, parent=parent)
        self._accent = accent

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(section(title, theme.MUTED))
        head.addStretch(1)
        self.status = Pill("IDLE", theme.DIM)
        head.addWidget(self.status)
        clear = QPushButton("CLEAR")
        clear.setObjectName("Chip")
        clear.setCursor(Qt.CursorShape.PointingHandCursor)
        clear.clicked.connect(self.clear)
        head.addWidget(clear)
        self.body.addLayout(head)

        self.output = QPlainTextEdit()
        self.output.setObjectName("Console")
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(6000)
        self.output.setFont(theme.font(12, mono=True))
        self.output.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.body.addWidget(self.output, 1)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.input = QLineEdit()
        self.input.setObjectName("ConsoleInput")
        self.input.setPlaceholderText("Answer an engine prompt (y / n / YES) and press Enter")
        self.input.returnPressed.connect(self._send)
        send = QPushButton("SEND")
        send.setObjectName("Chip")
        send.setCursor(Qt.CursorShape.PointingHandCursor)
        send.clicked.connect(self._send)
        input_row.addWidget(self.input, 1)
        input_row.addWidget(send)
        self.body.addLayout(input_row)

    def _send(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.write(f"» {text}", "cmd")
        self.submitted.emit(text)

    def set_status(self, text: str, color: str) -> None:
        self.status.set_state(text, color)

    def clear(self) -> None:
        self.output.clear()

    def begin(self, title: str, argv: list[str]) -> None:
        self.write("")
        self.write(f"── {title} " + "─" * max(4, 66 - len(title)), "dim")
        self.write("$ " + " ".join(argv), "cmd")

    def write(self, text: str, kind: str | None = None) -> None:
        text = str(text)
        color = self._classify(text, kind)
        escaped = html.escape(text).replace("\t", "    ")
        if escaped.startswith(" "):
            trimmed = escaped.lstrip(" ")
            escaped = "&nbsp;" * (len(escaped) - len(trimmed)) + trimmed
        self.output.appendHtml(f'<span style="color:{color}; white-space:pre;">{escaped or "&nbsp;"}</span>')
        bar = self.output.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _classify(self, text: str, kind: str | None) -> str:
        if kind and kind in self._COLORS:
            return self._COLORS[kind]
        stripped = text.strip()
        if not stripped:
            return self._COLORS["dim"]
        if stripped.startswith(("✖", "ERROR", "Traceback", "Exception")):
            return self._COLORS["err"]
        if stripped.startswith(("⚠", "WARNING", "REFUSED")):
            return self._COLORS["warn"]
        if stripped.startswith(("✓", "OK", "ORDER", "COMPLETE")):
            return self._COLORS["ok"]
        if stripped.startswith(("╔", "╚", "╠", "║", "─", "═", "┌", "└", "├")):
            return self._COLORS["dim"]
        if stripped.startswith(("$", "»")):
            return self._COLORS["cmd"]
        return self._COLORS["out"]
