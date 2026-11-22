"""Dashboard: gate status, the three engines and the session feed.

A polished, animated MEGATRON dashboard with glowing stat tiles, hover-lit
engine cards and a live session feed.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QPropertyAnimation, QEasingCurve, QTimer, Qt, Signal, QTime, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import config, theme
from ..components import Card, KeyRow, Pill, Stat, Toggle, ghost_button, section
from ..engine import bus


ENGINES = [
    (
        "stocks",
        "01",
        "STOCK INTELLIGENCE",
        "MEGASTOCKS",
        "19 AGENTS · OLLAMA · ALPACA",
        theme.ORANGE,
        [
            "Full analyst stack: Buffett, Munger, Burry, Wood and 15 more",
            "Local Ollama runs with zero API cost",
            "Reasoning traces and historical backtests",
            "Alpaca execution with per-order approval",
        ],
    ),
    (
        "calls",
        "02",
        "COVERED CALL HUNTER",
        "MEGACALLS",
        "DELTA 0.15–0.40 · 21–45 DTE",
        theme.PURPLE,
        [
            "Conservative and wider liquidity screens",
            "Delta, OTM and open-interest ranking",
            "Test universe for smoke runs",
            "Stock leg + sell-to-open call with approval",
        ],
    ),
    (
        "crypto",
        "03",
        "SOLANA COMMAND CENTER",
        "MEGACRYPTO",
        "JUPITER · MAINNET · WATCH-ONLY",
        theme.YELLOW,
        [
            "Live Jupiter quote router with impact readout",
            "Cross-venue arbitrage scanner",
            "Watch-only wallet balances — no keys stored",
            "Paper ledger, risk gates and a gated live swap",
        ],
    ),
]

# -- helper: add a soft glow shadow to a widget ---------------------------------
def _shadow(widget: QWidget, color: str = theme.ORANGE, blur: int = 18) -> None:
    """Give a widget a soft glow shadow for depth."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setOffset(0, 0)
    shadow.setBlurRadius(blur)
    shadow.setColor(QColor(theme.rgba(color, 0.28)))
    widget.setGraphicsEffect(shadow)


# -- animated value label -------------------------------------------------------
class _AnimatedValue(QLabel):
    """A label that animates a text swap when the value changes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._target_text: str = ""
        self._anim: QPropertyAnimation | None = None
        self.setVisible(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_target(self, text: str) -> None:
        if text == self._target_text:
            return
        self._target_text = text
        if self._anim is not None:
            self._anim.stop()
        self.setVisible(True)
        self._anim = QPropertyAnimation(self, b"text", self.parent() if self.parent() else None)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._anim.setStartValue(self.text())
        self._anim.setEndValue(text)
        self._anim.finished.connect(self._on_anim_finished)
        self._anim.start()

    def _on_anim_finished(self) -> None:
        self._anim = None


# -- pulsing status label -------------------------------------------------------
class _PulseStat(QLabel):
    """A stat label that gently pulses while it stays active."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active = False
        self.setVisible(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._pulse = self._idle  # defined before use
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pulse)
        self._timer_interval = 900

    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self.setVisible(active)
        if active:
            self._timer.start(self._timer_interval)
            self._pulse = self._do_pulse
            self.setStyleSheet(f"color: {theme.GREEN};")
        else:
            self._timer.stop()
            self._pulse = self._idle
            self.setStyleSheet(f"color: {theme.DIM};")

    def _do_pulse(self) -> None:
        self._timer.start(self._timer_interval)

    def _idle(self) -> None:
        pass


class DashboardPage(QWidget):
    open_engine = Signal(str)
    request_live = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setAutoFillBackground(False)
        inner = QWidget()
        inner.setMinimumHeight(720)
        root = QVBoxLayout(inner)
        root.setContentsMargins(0, 0, 6, 0)
        root.setSpacing(16)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        # -- main title ---------------------------------------------------------
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(0, 0, 0, 0)
        title_bar.setSpacing(10)

        self.title_label = QLabel("MEGATRON")
        self.title_label.setFont(theme.font(28, QFont.Weight.Bold, mono=True, spacing=1.2))
        self.title_label.setStyleSheet(
            f"color: {theme.ORANGE}; "
            f"font-family: '{theme.mono_family()}'; "
            f"text-shadow: 0 0 12px {theme.rgba(theme.ORANGE, 0.35)};"
        )
        title_bar.addWidget(self.title_label)

        self.tagline = QLabel("UNIFIED TRADING DESK")
        self.tagline.setFont(theme.font(8, QFont.Weight.DemiBold, mono=True, spacing=2.2))
        self.tagline.setStyleSheet(f"color: {theme.DIM};")
        title_bar.addWidget(self.tagline)

        self.quick_status = _PulseStat()
        self.quick_status.set_active(False)
        title_bar.addWidget(self.quick_status)

        root.addLayout(title_bar)

        # -- status tiles -------------------------------------------------------
        stats = QHBoxLayout()
        stats.setSpacing(14)
        self.stat_gate = Stat("MASTER GATE", "OFF", "live orders blocked", theme.RED)
        self.stat_alpaca = Stat("ALPACA", "NOT SET", "trading keys missing", theme.BLUE)
        self.stat_wallet = Stat("SOLANA WALLET", "—", "watch-only address", theme.YELLOW)
        self.stat_exec = Stat("LIVE EXECUTOR", "GATED", "env gate closed", theme.PURPLE)
        for tile in (self.stat_gate, self.stat_alpaca, self.stat_wallet, self.stat_exec):
            stats.addWidget(tile, 1)
        root.addLayout(stats)

        # -- engine cards -------------------------------------------------------
        engines = QHBoxLayout()
        engines.setSpacing(14)
        for key, index, eyebrow, title, meta, accent, features in ENGINES:
            engines.addWidget(self._engine_card(key, index, eyebrow, title, meta, accent, features), 1)
        root.addLayout(engines, 3)

        # -- safety + activity --------------------------------------------------
        bottom = QHBoxLayout()
        bottom.setSpacing(14)
        bottom.addWidget(self._safety_card(), 1)
        bottom.addWidget(self._activity_card(), 1)
        root.addLayout(bottom, 2)

        bus.activity.connect(self._log)
        bus.switch_changed.connect(self._switch_changed)
        self.refresh()

    # -- cards ------------------------------------------------------------------
    def _engine_card(self, key, index, eyebrow, title, meta, accent, features) -> Card:
        card = Card(accent=accent, pad=18, spacing=10)
        card.setMinimumHeight(290)
        card.setProperty("cardIndex", index)
        card.setProperty("cardVisible", False)
        card.setStyleSheet(
            f"QFrame#Card {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
            f"stop:0 {theme.rgba(accent, 0.06)}, stop:1 {theme.rgba(accent, 0.02)}); "
            f"border: 1px solid {theme.rgba(accent, 0.18)}; border-radius: 14px; "
            f"opacity: 0; }}"
        )
        _shadow(card, accent, blur=14)

        # Entrance animation: fade in + slight scale up
        card.anim_in = QVariantAnimation(card)
        card.anim_in.setDuration(400)
        card.anim_in.setEasingCurve(QEasingCurve.Type.OutBack)
        card.anim_in.setStartValue(0.0)
        card.anim_in.setEndValue(1.0)
        card.anim_in.valueChanged.connect(
            lambda v: card.setStyleSheet(
                f"QFrame#Card {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                f"stop:0 {theme.rgba(accent, 0.06)}, stop:1 {theme.rgba(accent, 0.02)}); "
                f"border: 1px solid {theme.rgba(accent, 0.18)}; border-radius: 14px; "
                f"opacity: {v}; }}"
            )
        )
        card.anim_in.start()

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(section(eyebrow, accent))
        head.addStretch(1)
        num = QLabel(index)
        num.setFont(theme.font(10, QFont.Weight.Bold, mono=True, spacing=1.4))
        num.setStyleSheet(f"color: {theme.rgba(accent, 0.55)};")
        _shadow(num, accent, blur=8)
        head.addWidget(num)
        card.body.addLayout(head)

        name = QLabel(title)
        name.setFont(theme.font(21, QFont.Weight.Bold, mono=True, spacing=1.2))
        card.body.addWidget(name)

        meta_label = QLabel(meta)
        meta_label.setFont(theme.font(9, QFont.Weight.DemiBold, mono=True, spacing=1.0))
        meta_label.setStyleSheet(f"color: {theme.DIM};")
        card.body.addWidget(meta_label)

        card.body.addWidget(section("FUNCTIONS", theme.DIM))
        for feature in features:
            card.body.addWidget(self._feature(feature, accent))

        card.body.addStretch(1)
        open_button = ghost_button(f"OPEN {title}", accent)
        open_button.clicked.connect(lambda _=False, target=key: self.open_engine.emit(target))
        card.body.addWidget(open_button)
        return card

    def _feature(self, text: str, accent: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        dash = QLabel("—")
        dash.setFont(theme.font(11, mono=True))
        dash.setStyleSheet(f"color: {theme.rgba(accent, 0.75)};")
        label = QLabel(text)
        label.setStyleSheet(f"color: {theme.MUTED};")
        label.setWordWrap(True)
        layout.addWidget(dash, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(label, 1)
        return row

    def _safety_card(self) -> Card:
        card = Card(accent=theme.GREEN, pad=18, spacing=10)
        card.setStyleSheet(
            f"QFrame#Card {{ border-top: 2px solid {theme.GREEN}; }}"
        )
        card.body.addWidget(section("SAFETY MODEL", theme.GREEN))
        title = QLabel("Nothing runs live by accident")
        title.setFont(theme.font(16, QFont.Weight.DemiBold))
        card.body.addWidget(title)
        for text in (
            "Every live path checks the master gate first.",
            "Orders still require approval in the console.",
            "Research works with the gate off — always.",
            "Turning the gate off blocks new orders instantly.",
        ):
            card.body.addWidget(self._feature(text, theme.GREEN))
        card.body.addStretch(1)
        gate_row = QHBoxLayout()
        gate_row.setSpacing(10)
        self.side_pill = Pill("LIVE OFF", theme.RED)
        self.safety_toggle = Toggle(False, theme.GREEN)
        self.safety_toggle.toggled.connect(self.request_live.emit)
        gate_row.addWidget(self.side_pill)
        gate_row.addStretch(1)
        gate_row.addWidget(self.safety_toggle)
        card.body.addLayout(gate_row)
        self.switch_path = QLabel(str(config.SWITCH_FILE))
        self.switch_path.setFont(theme.font(9, mono=True))
        self.switch_path.setStyleSheet(f"color: {theme.DIM};")
        self.switch_path.setWordWrap(True)
        card.body.addWidget(self.switch_path)
        return card

    def _activity_card(self) -> Card:
        card = Card(pad=18, spacing=10)
        card.setStyleSheet(
            f"QFrame#Card {{ border-top: 2px solid {theme.MUTED}; }}"
        )
        card.body.addWidget(section("SESSION FEED", theme.MUTED))
        self.activity = QPlainTextEdit()
        self.activity.setObjectName("Activity")
        self.activity.setReadOnly(True)
        self.activity.setMaximumBlockCount(300)
        self.activity.setFont(theme.font(11, mono=True))
        self.activity.setStyleSheet(
            f"QPlainTextEdit {{ background: transparent; border: none; color: {theme.MUTED}; }}"
        )
        card.body.addWidget(self.activity, 1)
        return card

    # -- state ------------------------------------------------------------------
    def refresh(self) -> None:
        r = config.readiness()
        on = r["live_switch"]

        self.stat_gate.set(
            "ON" if on else "OFF",
            color=theme.GREEN if on else theme.RED,
            hint="live paths eligible" if on else "live orders blocked",
        )
        self.stat_alpaca.set(
            "READY" if r["alpaca"] else "NOT SET",
            color=theme.GREEN if r["alpaca"] else theme.ORANGE,
            hint=f"{r['alpaca_mode']} mode" if r["alpaca"] else "ALPACA_API_KEY missing",
        )
        self.stat_wallet.set(
            "SET" if r["solana_wallet"] else "—",
            color=theme.YELLOW if r["solana_wallet"] else theme.DIM,
            hint=(r["solana_wallet"][:10] + "…") if r["solana_wallet"] else "no watch-only address",
        )
        self.stat_exec.set(
            "ARMED" if r["live_execution"] else "GATED",
            color=theme.PURPLE if r["live_execution"] else theme.DIM,
            hint="MEGATRON_LIVE_EXECUTION true" if r["live_execution"] else "execution gate closed",
        )

        self.safety_toggle.set_on(on)
        self.side_pill.set_state("LIVE ON" if on else "LIVE OFF", theme.GREEN if on else theme.RED)
        self.quick_status.set_active(on)

    def _switch_changed(self, on: bool) -> None:
        self.refresh()

    def _log(self, engine: str, message: str) -> None:
        stamp = QTime.currentTime().toString("HH:mm:ss")
        self.activity.appendPlainText(f"{stamp}  {engine:<10} {message}")

    def on_show(self) -> None:
        self.refresh()
        self.activity.clear()
