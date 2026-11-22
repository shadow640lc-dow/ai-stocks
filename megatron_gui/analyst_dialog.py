"""Native analyst roster: arrow keys, Space, A, Enter and Escape.

Mirrors the keyboard contract of the CLI's questionary checkbox, without a
terminal: focus stays on the roster canvas for the dialog's whole lifetime.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .catalog import Analyst
from .components import Pill, ghost_button, primary_button, section

HEAD_H = 38
ITEM_H = 68
GAP = 4

# A balanced, fast roster for routine research. Every analyst can still be
# toggled individually or all at once.
FOCUS_KEYS = (
    "warren_buffett",
    "ben_graham",
    "cathie_wood",
    "technical_analyst",
    "fundamentals_analyst",
)


class RosterCanvas(QWidget):
    """Painted checklist. One widget keeps key handling unambiguous."""

    changed = Signal()
    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, analysts: list[Analyst], groups: list[tuple[str, list[Analyst]]], selected: set[str], accent: str = theme.ORANGE, parent: QWidget | None = None):
        super().__init__(parent)
        self._analysts = analysts
        self._accent = accent
        self.selected: set[str] = {key for key in selected if any(a.key == key for a in analysts)}
        self._scroll: QScrollArea | None = None
        self._hover = -1

        self.rows: list[tuple[str, object]] = []
        for title, members in groups:
            if members:
                self.rows.append(("head", title.upper()))
                self.rows.extend(("item", analyst) for analyst in members)

        self.focus_index = next((i for i, row in enumerate(self.rows) if row[0] == "item"), -1)
        self._rects: list[tuple[int, int, tuple[str, object]]] = []

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._relayout()

    # -- layout --------------------------------------------------------

    def attach_scroll(self, area: QScrollArea) -> None:
        self._scroll = area

    def _relayout(self) -> None:
        self._rects = []
        y = 4
        width = max(self.width(), 360)
        for row in self.rows:
            height = HEAD_H if row[0] == "head" else ITEM_H
            self._rects.append((y, height, row))
            y += height + GAP
        self.setMinimumHeight(y + 8)
        self._width = width

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(560, max(360, self.minimumHeight()))

    def _items(self) -> list[int]:
        return [i for i, row in enumerate(self.rows) if row[0] == "item"]

    def _row_at(self, pos: QPoint) -> int:
        for index, (y, height, _row) in enumerate(self._rects):
            if y <= pos.y() <= y + height:
                return index
        return -1

    def _ensure_visible(self, index: int) -> None:
        if self._scroll is None or not (0 <= index < len(self._rects)):
            return
        y, height, _row = self._rects[index]
        self._scroll.ensureVisible(0, y, 0, height + 8)

    # -- keys ----------------------------------------------------------

    def handle_key(self, event) -> bool:
        key = event.key()
        items = self._items()
        if not items:
            return False

        if self.focus_index not in items:
            self.focus_index = items[0]

        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Home, Qt.Key.Key_End, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            position = items.index(self.focus_index)
            if key == Qt.Key.Key_Up:
                position = max(0, position - 1)
            elif key == Qt.Key.Key_Down:
                position = min(len(items) - 1, position + 1)
            elif key == Qt.Key.Key_Home:
                position = 0
            elif key == Qt.Key.Key_End:
                position = len(items) - 1
            elif key == Qt.Key.Key_PageUp:
                position = max(0, position - 5)
            else:
                position = min(len(items) - 1, position + 5)
            self.focus_index = items[position]
            self._ensure_visible(self.focus_index)
            self.update()
            return True

        if key == Qt.Key.Key_Space:
            self._toggle(self.focus_index)
            return True

        if key == Qt.Key.Key_A:
            self._toggle_all()
            return True

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.selected:
                self.confirmed.emit()
            else:
                self.changed.emit()  # lets the dialog surface the "pick one" hint
            return True

        if key == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return True

        return False

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if not self.handle_key(event):
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        index = self._row_at(event.position().toPoint())
        if index < 0 or self.rows[index][0] != "item":
            return
        self.focus_index = index
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._toggle(index)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        index = self._row_at(event.position().toPoint())
        if index != self._hover:
            self._hover = index
            self.update()
        if 0 <= index < len(self.rows) and self.rows[index][0] == "item":
            analyst: Analyst = self.rows[index][1]  # type: ignore[assignment]
            self.setToolTip(f"{analyst.name}\n{analyst.style}")
        else:
            self.setToolTip("")

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    # -- selection -----------------------------------------------------

    def _toggle(self, index: int) -> None:
        if not (0 <= index < len(self.rows)) or self.rows[index][0] != "item":
            return
        analyst: Analyst = self.rows[index][1]  # type: ignore[assignment]
        if analyst.key in self.selected:
            self.selected.discard(analyst.key)
        else:
            self.selected.add(analyst.key)
        self.update()
        self.changed.emit()

    def _toggle_all(self) -> None:
        if len(self.selected) == len(self._analysts):
            self.selected.clear()
        else:
            self.selected = {a.key for a in self._analysts}
        self.update()
        self.changed.emit()

    def select_all(self) -> None:
        self.selected = {a.key for a in self._analysts}
        self.update()
        self.changed.emit()

    def clear_all(self) -> None:
        self.selected.clear()
        self.update()
        self.changed.emit()

    def select_keys(self, keys: tuple[str, ...] | list[str]) -> None:
        allowed = {analyst.key for analyst in self._analysts}
        self.selected = {key for key in keys if key in allowed}
        self.update()
        self.changed.emit()

    def selected_keys(self) -> list[str]:
        return [a.key for a in self._analysts if a.key in self.selected]

    # -- paint ---------------------------------------------------------

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(theme.BG))

        width = self.width()
        for index, (y, height, row) in enumerate(self._rects):
            if row[0] == "head":
                self._paint_head(painter, y, height, str(row[1]))
            else:
                self._paint_item(painter, index, y, height, row[1], width)  # type: ignore[arg-type]

    def _paint_head(self, painter: QPainter, y: int, height: int, title: str) -> None:
        painter.setFont(theme.font(9, QFont.Weight.DemiBold, mono=True, spacing=1.4))
        painter.setPen(QColor(theme.DIM))
        painter.drawText(QRect(14, y + 10, self.width() - 28, height - 12), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
        painter.setPen(QPen(QColor(theme.LINE), 1))
        painter.drawLine(14, y + height - 2, self.width() - 14, y + height - 2)

    def _paint_item(self, painter: QPainter, index: int, y: int, height: int, analyst: Analyst, width: int) -> None:
        focused = index == self.focus_index and self.hasFocus()
        hovered = index == self._hover
        checked = analyst.key in self.selected

        rect = QRect(6, y, width - 12, height)
        if focused or hovered:
            painter.setPen(QPen(QColor(theme.rgba(self._accent, 0.55) if focused else theme.rgba(theme.TEXT, 0.12)), 1))
            painter.setBrush(QColor(theme.rgba(self._accent, 0.10) if focused else theme.HOVER))
            painter.drawRoundedRect(rect, 10, 10)
            if focused:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(self._accent))
                painter.drawRoundedRect(QRect(rect.left() + 1, rect.top() + 10, 3, height - 20), 1.5, 1.5)

        box = QRect(20, y + (height - 18) // 2, 18, 18)
        if checked:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self._accent))
            painter.drawRoundedRect(box, 5, 5)
            painter.setPen(QColor(theme.INK))
            painter.setFont(theme.font(11, QFont.Weight.Bold, mono=True))
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, "✓")
        else:
            painter.setPen(QPen(QColor(theme.rgba(theme.TEXT, 0.38)), 1.4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(box, 5, 5)

        text_left = 50
        text_width = width - text_left - 16

        painter.setFont(theme.font(13, QFont.Weight.DemiBold))
        painter.setPen(QColor(theme.TEXT if checked else theme.MUTED))
        painter.drawText(QRect(text_left, y + 12, text_width, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, analyst.name)

        detail = analyst.role or analyst.style
        metrics = QFontMetrics(theme.font(11))
        painter.setFont(theme.font(11))
        painter.setPen(QColor(theme.DIM))
        painter.drawText(
            QRect(text_left, y + 34, text_width, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(detail, Qt.TextElideMode.ElideRight, text_width),
        )


class AnalystDialog(QDialog):
    """Modal roster with the CLI's keyboard contract."""

    def __init__(self, catalog, selected: list[str], accent: str = theme.ORANGE, parent: QWidget | None = None):
        super().__init__(parent)
        self._catalog = catalog
        self._accent = accent
        self.setWindowTitle("Select AI analysts")
        self.setModal(True)
        self.setMinimumSize(720, 660)
        self.setStyleSheet(
            f"QDialog {{ background: {theme.BG}; border: 1px solid {theme.LINE}; }}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(section("RESEARCH STAFF", theme.ORANGE))
        head.addStretch(1)
        self.count = Pill("0 SELECTED", theme.ORANGE)
        head.addWidget(self.count)
        root.addLayout(head)

        title = QLabel("Select AI analysts")
        title.setFont(theme.font(21, QFont.Weight.Bold))
        root.addWidget(title)

        hint = QLabel("Space toggles · A selects or clears all · Enter confirms · Esc cancels")
        hint.setObjectName("Hint")
        root.addWidget(hint)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            f"QScrollArea {{ background: {theme.BG}; border: 1px solid {theme.LINE}; border-radius: 12px; }}"
        )
        self.canvas = RosterCanvas(catalog.analysts, catalog.groups(), set(selected), accent)
        self.canvas.attach_scroll(self.scroll)
        self.scroll.setWidget(self.canvas)
        root.addWidget(self.scroll, 1)

        self.hint = QLabel(f"{len(catalog.analysts)} analysts available · research only, never execution")
        self.hint.setObjectName("Hint")
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.focus_btn = ghost_button("FOCUS 5", theme.GREEN)
        self.focus_btn.setToolTip("Buffett · Graham · Wood · Technical · Fundamentals")
        self.clear_btn = ghost_button("DESELECT ALL", theme.MUTED)
        self.all_btn = ghost_button("SELECT ALL", theme.ORANGE)
        self.cancel_btn = ghost_button("CANCEL", theme.MUTED)
        self.confirm_btn = primary_button("CONFIRM", theme.ORANGE, height=38)
        for button in (self.focus_btn, self.clear_btn, self.all_btn, self.cancel_btn, self.confirm_btn):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        footer.addWidget(self.focus_btn)
        footer.addWidget(self.clear_btn)
        footer.addWidget(self.all_btn)
        footer.addStretch(1)
        footer.addWidget(self.cancel_btn)
        footer.addWidget(self.confirm_btn)
        root.addLayout(footer)

        self.canvas.changed.connect(self._sync)
        self.canvas.confirmed.connect(self._confirm)
        self.canvas.cancelled.connect(self.reject)
        self.focus_btn.clicked.connect(lambda: self.canvas.select_keys(FOCUS_KEYS))
        self.clear_btn.clicked.connect(self.canvas.clear_all)
        self.all_btn.clicked.connect(self.canvas.select_all)
        self.cancel_btn.clicked.connect(self.reject)
        self.confirm_btn.clicked.connect(self._confirm)

        self.setFocusProxy(self.canvas)
        self._sync()
        QTimer.singleShot(0, self.canvas.setFocus)

    # -- state ---------------------------------------------------------

    def _sync(self) -> None:
        count = len(self.canvas.selected)
        total = len(self._catalog.analysts)
        self.count.set_state(f"{count} SELECTED", self._accent if count else theme.RED)
        self.confirm_btn.setText(f"CONFIRM {count}" if count else "CONFIRM")
        self.confirm_btn.setEnabled(count > 0)
        if count:
            self.hint.setText(f"{count} of {total} analysts · selection only changes research, never execution")
        else:
            self.hint.setText("Select at least one analyst. A selects all.")

    def _confirm(self) -> None:
        if not self.canvas.selected:
            self.hint.setText("Select at least one analyst before confirming.")
            self.canvas.setFocus()
            return
        self.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self.focusWidget() is not self.canvas and self.canvas.handle_key(event):
            return
        super().keyPressEvent(event)

    def selection(self) -> list[str]:
        return self.canvas.selected_keys()

    def selected_names(self) -> list[str]:
        chosen = set(self.canvas.selected_keys())
        return [a.name for a in self._catalog.analysts if a.key in chosen]


def ask(parent: QWidget, catalog, selected: list[str], accent: str = theme.ORANGE) -> list[str] | None:
    dialog = AnalystDialog(catalog, selected, accent, parent)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.selection()
    return None
