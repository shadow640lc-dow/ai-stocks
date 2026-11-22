"""MEGATRON desktop shell: sidebar, header gate, page router."""

from __future__ import annotations

import sys

from PySide6.QtCore import QDateTime, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__, config, theme
from .components import Pill, Toggle, section
from .engine import bus
from .pages.calls import CallsPage
from .pages.crypto import CryptoPage
from .pages.dashboard import DashboardPage
from .pages.stocks import StocksPage

NAV = [
    ("dashboard", "01", "DASHBOARD", theme.BLUE, "UNIFIED DESK", "One desk for stocks, covered calls and Solana"),
    ("stocks", "02", "MEGASTOCKS", theme.ORANGE, "STOCK INTELLIGENCE", "AI analysts · local models · backtests · Alpaca execution"),
    ("calls", "03", "MEGACALLS", theme.PURPLE, "COVERED CALL HUNTER", "Liquid candidate ranking · confirmed execution"),
    ("crypto", "04", "MEGACRYPTO", theme.YELLOW, "SOLANA COMMAND CENTER", "Jupiter quotes · arbitrage · wallet · gated swaps"),
]


def make_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 32, 48, 64, 128, 256, 512):
        asset = config.ROOT / "assets" / f"megatron-{size}.png"
        if asset.exists():
            icon.addFile(str(asset))
    if not icon.isNull():
        return icon

    pixmap = QPixmap(256, 256)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    gradient = QLinearGradient(0, 0, 256, 256)
    gradient.setColorAt(0.0, QColor(theme.ORANGE))
    gradient.setColorAt(0.55, QColor(theme.PURPLE))
    gradient.setColorAt(1.0, QColor(theme.YELLOW))

    path = QPainterPath()
    path.addRoundedRect(QRectF(12, 12, 232, 232), 54, 54)
    painter.fillPath(path, QBrush(gradient))

    pen = QPen(QColor(theme.INK), 20, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawPolyline([
        QPointF(70, 184),
        QPointF(70, 84),
        QPointF(128, 146),
        QPointF(186, 84),
        QPointF(186, 184),
    ])
    painter.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MEGATRON · Unified Trading Terminal")
        self.setWindowIcon(make_icon())
        self.resize(1480, 920)
        self.setMinimumSize(1024, 700)

        self.nav_buttons: dict[str, QPushButton] = {}
        self.pages: dict[str, QWidget] = {}

        root = QFrame()
        root.setObjectName("Root")
        self.setCentralWidget(root)

        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_sidebar())

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._build_header())

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(26, 18, 26, 20)
        body_layout.setSpacing(0)
        self.stack = QStackedWidget()
        body_layout.addWidget(self.stack)
        content_layout.addWidget(body, 1)
        outer.addWidget(content, 1)

        self._build_pages()

        self.dashboard.open_engine.connect(self.show_page)
        self.dashboard.request_live.connect(self._on_toggle_request)

        bus.switch_changed.connect(self._sync_switch)
        self._sync_switch(config.switch_on())
        self.show_page("dashboard")

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick)
        self._clock_timer.start(1000)
        self._tick()

        QShortcut(QKeySequence("Ctrl+1"), self, activated=lambda: self.show_page("dashboard"))
        QShortcut(QKeySequence("Ctrl+2"), self, activated=lambda: self.show_page("stocks"))
        QShortcut(QKeySequence("Ctrl+3"), self, activated=lambda: self.show_page("calls"))
        QShortcut(QKeySequence("Ctrl+4"), self, activated=lambda: self.show_page("crypto"))

        bus.activity.emit("MEGATRON", "session started")

    # ------------------------------------------------------------------
    # Shell
    # ------------------------------------------------------------------

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(244)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(6)

        stripe = QFrame()
        stripe.setFixedHeight(3)
        stripe.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            f"stop:0 {theme.ORANGE}, stop:0.5 {theme.PURPLE}, stop:1 {theme.YELLOW});"
            "border-radius: 1px;"
        )
        layout.addWidget(stripe)
        layout.addSpacing(12)

        brand = QLabel("MEGATRON")
        brand.setFont(theme.font(21, QFont.Weight.Bold, mono=True, spacing=3.0))
        layout.addWidget(brand)

        tagline = QLabel("UNIFIED TRADING DESK")
        tagline.setFont(theme.font(8, QFont.Weight.DemiBold, mono=True, spacing=2.2))
        tagline.setStyleSheet(f"color: {theme.DIM};")
        layout.addWidget(tagline)
        layout.addSpacing(20)

        layout.addWidget(section("TERMINALS", theme.DIM))
        layout.addSpacing(4)

        for key, index, label, accent, _title, _sub in NAV:
            button = QPushButton(f"{index}    {label}")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setMinimumHeight(40)
            button.setFont(theme.font(10, QFont.Weight.DemiBold, mono=True, spacing=1.4))
            button.setStyleSheet(
                f"""
                QPushButton {{
                    background: transparent;
                    color: {theme.MUTED};
                    border: 1px solid transparent;
                    border-radius: 9px;
                    text-align: left;
                    padding: 9px 12px;
                }}
                QPushButton:hover {{ background: {theme.HOVER}; color: {theme.TEXT}; }}
                QPushButton:checked {{
                    background: {theme.rgba(accent, 0.10)};
                    color: {accent};
                    border-color: {theme.rgba(accent, 0.35)};
                }}
                """
            )
            button.clicked.connect(lambda _=False, target=key: self.show_page(target))
            layout.addWidget(button)
            self.nav_buttons[key] = button

        layout.addStretch(1)

        safety = QFrame()
        safety.setObjectName("CardFlat")
        safety_layout = QVBoxLayout(safety)
        safety_layout.setContentsMargins(13, 12, 13, 12)
        safety_layout.setSpacing(8)
        safety_layout.addWidget(section("MASTER GATE", theme.DIM))
        self.sidebar_pill = Pill("LIVE OFF", theme.RED)
        safety_layout.addWidget(self.sidebar_pill)
        note = QLabel("Research stays open.\nLive paths check this gate first.")
        note.setStyleSheet(f"color: {theme.DIM}; font-size: 10px;")
        note.setWordWrap(True)
        safety_layout.addWidget(note)
        layout.addWidget(safety)

        layout.addSpacing(12)
        footer = QLabel(f"v{__version__}  ·  LOCAL  ·  OMARCHY")
        footer.setFont(theme.font(8, mono=True, spacing=1.0))
        footer.setStyleSheet(f"color: {theme.DIM};")
        layout.addWidget(footer)
        return sidebar

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("HeaderBar")
        header.setFixedHeight(90)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(26, 14, 26, 14)
        layout.setSpacing(18)

        titles = QVBoxLayout()
        titles.setSpacing(4)
        self.title = QLabel("DASHBOARD")
        self.title.setObjectName("PageTitle")
        self.title.setFont(theme.font(23, QFont.Weight.Bold, mono=True, spacing=1.4))
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("PageSub")
        self.subtitle.setFont(theme.font(10, mono=True, spacing=1.0))
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        layout.addLayout(titles)
        layout.addStretch(1)

        clock_box = QVBoxLayout()
        clock_box.setSpacing(1)
        self.clock = QLabel("--:--:--")
        self.clock.setFont(theme.font(16, QFont.Weight.DemiBold, mono=True, spacing=1.0))
        self.clock.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.date = QLabel("")
        self.date.setFont(theme.font(8, QFont.Weight.DemiBold, mono=True, spacing=1.2))
        self.date.setStyleSheet(f"color: {theme.DIM};")
        self.date.setAlignment(Qt.AlignmentFlag.AlignRight)
        clock_box.addWidget(self.clock)
        clock_box.addWidget(self.date)
        layout.addLayout(clock_box)

        divider = QFrame()
        divider.setFixedSize(1, 34)
        divider.setStyleSheet(f"background: {theme.LINE};")
        layout.addWidget(divider)

        live_box = QHBoxLayout()
        live_box.setSpacing(10)
        live_label = QLabel("LIVE TRADING")
        live_label.setFont(theme.font(8, QFont.Weight.DemiBold, mono=True, spacing=1.4))
        live_label.setStyleSheet(f"color: {theme.DIM};")
        self.header_pill = Pill("OFF", theme.RED)
        self.live_toggle = Toggle(False, theme.GREEN)
        self.live_toggle.toggled.connect(self._on_toggle_request)
        live_box.addWidget(live_label)
        live_box.addWidget(self.header_pill)
        live_box.addWidget(self.live_toggle)
        layout.addLayout(live_box)
        return header

    def _build_pages(self) -> None:
        self.dashboard = DashboardPage()
        self.stocks = StocksPage()
        self.calls = CallsPage()
        self.crypto = CryptoPage()

        self.pages = {
            "dashboard": self.dashboard,
            "stocks": self.stocks,
            "calls": self.calls,
            "crypto": self.crypto,
        }
        for page in self.pages.values():
            self.stack.addWidget(page)

    # ------------------------------------------------------------------
    # Routing + gate
    # ------------------------------------------------------------------

    def show_page(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        for name, button in self.nav_buttons.items():
            button.setChecked(name == key)
        self.stack.setCurrentWidget(page)
        for nav_key, _index, _label, _accent, title, subtitle in NAV:
            if nav_key == key:
                self.title.setText(title)
                self.subtitle.setText(subtitle.upper())
                break
        if hasattr(page, "on_show"):
            page.on_show()

    def _tick(self) -> None:
        now = QDateTime.currentDateTime()
        self.clock.setText(now.toString("HH:mm:ss"))
        self.date.setText(now.toString("ddd dd MMM yyyy").upper())

    def _sync_switch(self, on: bool) -> None:
        self.header_pill.set_state("ON" if on else "OFF", theme.GREEN if on else theme.RED)
        self.sidebar_pill.set_state("LIVE ON" if on else "LIVE OFF", theme.GREEN if on else theme.RED)
        self.live_toggle.set_on(on)

    def shutdown(self) -> None:
        """Stop every child engine and release local model memory."""
        if getattr(self, "_shutting_down", False):
            return
        self._shutting_down = True
        self._clock_timer.stop()
        for page in self.pages.values():
            close = getattr(page, "shutdown", None)
            if callable(close):
                close()

    def closeEvent(self, event) -> None:  # noqa: N802
        self.shutdown()
        event.accept()

    def _on_toggle_request(self, on: bool) -> None:
        if on:
            answer = QMessageBox.question(
                self,
                "Enable live trading?",
                "The master gate makes every live path eligible to execute.\n\n"
                "Orders and swaps still require explicit approval, and the gate can be "
                "turned off at any moment.\n\nEnable live trading?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                bus.switch_changed.emit(config.switch_on())
                return

        config.set_switch(on)
        bus.switch_changed.emit(on)
        bus.activity.emit("SAFETY", f"master gate {'enabled' if on else 'disabled'}")


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("MEGATRON")
    app.setApplicationDisplayName("MEGATRON · Unified Trading Terminal")
    app.setOrganizationName("MEGATRON")
    app.setDesktopFileName("megatron")
    app.setQuitOnLastWindowClosed(True)
    app.setFont(theme.font(13))
    theme.apply_palette(app)
    app.setStyleSheet(theme.build_qss())
    app.setWindowIcon(make_icon())

    window = MainWindow()
    window.show()
    return app.exec()
