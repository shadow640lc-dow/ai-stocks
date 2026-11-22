"""MEGACALLS: covered-call screening with optional confirmed execution."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import config, theme
from ..components import (
    Card,
    ChoiceGroup,
    KeyRow,
    TickerField,
    Toggle,
    field,
    ghost_button,
    primary_button,
    section,
)
from ..engine import ProcessRunner, bus
from ..report import ReportStream

STYLES = [
    ("conservative", "Conservative / liquid", "Volume ≥ 100 · open interest ≥ 500 · top 10", ""),
    ("wider", "Wider candidate search", "Volume ≥ 50 · open interest ≥ 250 · top 15", ""),
    ("test", "Test universe", "Smoke-test universe · limit 3 · top 5", "SAFE"),
]


class CallsPage(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(14)

        # -- tickers -----------------------------------------------------
        universe = Card(accent=theme.PURPLE)
        universe.body.addWidget(section("UNDERLYINGS", theme.PURPLE))
        title = QLabel("Ticker selection")
        title.setFont(theme.font(16, QFont.Weight.DemiBold))
        universe.body.addWidget(title)
        self.tickers = TickerField(theme.PURPLE)
        universe.body.addWidget(self.tickers)
        hint = QLabel("Ignored by the test universe mode.")
        hint.setObjectName("Hint")
        universe.body.addWidget(hint)
        left.addWidget(universe)

        # -- scan style --------------------------------------------------
        styles = Card(accent=theme.PURPLE)
        styles.body.addWidget(section("SCAN STYLE", theme.PURPLE))
        self.styles = ChoiceGroup(STYLES, theme.PURPLE)
        styles.body.addWidget(self.styles)
        left.addWidget(styles)

        # -- execution ---------------------------------------------------
        execution = Card()
        execution.body.addWidget(section("EXECUTION", theme.MUTED))

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(10)
        toggle_label = QLabel("Route winning contract to Alpaca")
        toggle_label.setObjectName("Muted")
        self.alpaca = Toggle(False, theme.GREEN)
        toggle_row.addWidget(toggle_label, 1)
        toggle_row.addWidget(self.alpaca)
        execution.body.addLayout(toggle_row)

        self.contracts = QSpinBox()
        self.contracts.setRange(1, 25)
        self.contracts.setValue(1)
        self.contracts.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.contracts.setMinimumHeight(38)
        self.contracts.setFont(theme.font(13, mono=True))

        self.max_cap = QDoubleSpinBox()
        self.max_cap.setRange(0, 1_000_000)
        self.max_cap.setDecimals(0)
        self.max_cap.setSingleStep(100)
        self.max_cap.setValue(0)
        self.max_cap.setSpecialValueText("env default")
        self.max_cap.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.max_cap.setMinimumHeight(38)
        self.max_cap.setFont(theme.font(13, mono=True))

        numbers = QHBoxLayout()
        numbers.setSpacing(12)
        numbers.addWidget(field("Contracts", self.contracts), 1)
        numbers.addWidget(field("Stock-leg cap", self.max_cap, "0 = env cap"), 1)
        execution.body.addLayout(numbers)

        self.row_switch = KeyRow("Master kill switch")
        execution.body.addWidget(self.row_switch)
        left.addWidget(execution)
        left.addStretch(1)

        # -- actions -----------------------------------------------------
        self.run_btn = primary_button("SCAN CANDIDATES", theme.PURPLE)
        self.run_btn.clicked.connect(self.run)
        self.stop_btn = ghost_button("STOP", theme.RED)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self.run_btn, 1)
        actions.addWidget(self.stop_btn)
        left.addLayout(actions)

        left_wrap = QWidget()
        left_wrap.setLayout(left)
        left_wrap.setMinimumWidth(0)
        left_wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        left_scroll.viewport().setAutoFillBackground(False)
        left_scroll.setWidget(left_wrap)
        left_scroll.setMinimumWidth(300)
        left_scroll.setMaximumWidth(380)

        self.report = ReportStream("REPORT", theme.PURPLE)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(left_scroll)
        splitter.addWidget(self.report)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 1000])
        root.addWidget(splitter, 1)

        self.runner = ProcessRunner(self)
        self.runner.output.connect(self.report.feed)
        self.runner.exited.connect(self._exited)
        self.report.submitted.connect(self._stdin)

        bus.switch_changed.connect(lambda _on: self.refresh_gate())
        self.refresh_gate()

    def refresh_gate(self) -> None:
        on = config.switch_on()
        self.row_switch.set(on, "ON" if on else "OFF")

    def run(self) -> None:
        if self.runner.busy():
            return

        style = self.styles.value()
        tickers = self.tickers.tickers()
        if style != "test" and not tickers:
            QMessageBox.warning(self, "No tickers", "Enter at least one underlying, or pick the test universe.")
            return

        live = self.alpaca.is_on()
        if live:
            if not config.switch_on():
                QMessageBox.warning(
                    self,
                    "Live trading is OFF",
                    "The master kill switch is OFF, so the scanner's execution path will refuse every order.\n\n"
                    "Enable the master gate from the header first.",
                )
                return
            answer = QMessageBox.question(
                self,
                "Confirm execution path",
                "After the scan this can submit a real covered-call order:\n"
                "buy 100 shares per contract, then sell the call.\n\n"                    "Each leg asks for confirmation in the report input. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        argv = config.calls_argv(
            tickers,
            style,
            alpaca=live,
            contracts=self.contracts.value(),
            max_cap=float(self.max_cap.value()),
        )

        self.report.clear()
        self.report.set_status("RUNNING", theme.PURPLE)
        self.report.begin(
            f"SCAN · {config.CALL_STYLES[style]['label']}",
            argv,
            subtitle="research only",
        )
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        bus.activity.emit("MEGACALLS", f"{config.CALL_STYLES[style]['label']}{' · alpaca' if live else ''}")
        self.runner.start(argv, config.ROOT)

    def _exited(self, code: int) -> None:
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if code == 0:
            self.report.write("✓ scan complete — no automatic execution without approval")
        elif code == 130:
            self.report.write("🛑 scan stopped by user")
        else:
            self.report.write(f"✖ scanner exited with code {code}")
        self.report.finish(code, stopped=code == 130)
        bus.activity.emit("MEGACALLS", f"scanner exit {code}")

    def stop(self) -> None:
        self.runner.stop()
        self.report.set_status("STOPPING", theme.YELLOW)
        self.report.write("stop requested…")

    def shutdown(self) -> None:
        self.runner.shutdown()

    def _stdin(self, text: str) -> None:
        if self.runner.busy():
            self.runner.send(text)
        else:
            self.report.write("No scanner is running.")
