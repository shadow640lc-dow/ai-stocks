"""MEGACRYPTO: Jupiter router, arbitrage scanner, wallet, ledger, risk, swap."""

from __future__ import annotations

import csv
import importlib.util
import re
from datetime import datetime, timezone
from functools import lru_cache

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import config, theme
from ..components import (
    Card,
    ChoiceGroup,
    KeyRow,
    Pill,
    SegmentBar,
    Stat,
    field,
    ghost_button,
    primary_button,
    section,
)
from ..engine import CallThread, ProcessRunner, bus
from ..report import ReportStream
from ..research import MetricRow

TABS = [
    ("scanner", "SCANNER"),
    ("jupiter", "JUPITER"),
    ("wallet", "WALLET"),
    ("paper", "PAPER"),
    ("risk", "RISK"),
    ("live", "LIVE SWAP"),
]

RISK_FIELDS = [
    ("max_trade_usdc", "MAX TRADE (USDC)", 0.01, 1_000_000.0, 2, 1.0),
    ("daily_loss_limit_usdc", "DAILY LOSS LIMIT (USDC)", 0.01, 1_000_000.0, 2, 1.0),
    ("min_net_edge_pct", "MIN NET EDGE (%)", 0.0, 100.0, 3, 0.05),
    ("strong_edge_pct", "STRONG EDGE (%)", 0.0, 100.0, 3, 0.05),
    ("max_price_impact_pct", "MAX PRICE IMPACT (%)", 0.0, 100.0, 2, 0.1),
    ("slippage_bps", "SLIPPAGE (BPS)", 1, 10_000, 0, 10.0),
]


@lru_cache(maxsize=1)
def _crypto_module():
    """Reuse megacrypto.py's own Jupiter/wallet helpers."""
    spec = importlib.util.spec_from_file_location("megacrypto_cli", config.ROOT / "megacrypto.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("megacrypto.py not found")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CryptoPage(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.cfg = config.load_crypto_config()
        self._threads: list[CallThread] = []
        self.gate_rows: dict[str, KeyRow] = {}

        self.runner = ProcessRunner(self)
        self.runner.output.connect(self._stream)
        self.runner.exited.connect(self._exited)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        self.tabs = SegmentBar(TABS, theme.YELLOW)
        root.addWidget(self.tabs, 0, Qt.AlignmentFlag.AlignLeft)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._scanner_tab())
        self.stack.addWidget(self._jupiter_tab())
        self.stack.addWidget(self._wallet_tab())
        self.stack.addWidget(self._paper_tab())
        self.stack.addWidget(self._risk_tab())
        self.stack.addWidget(self._live_tab())
        self.stack.setMinimumHeight(300)
        self.stack_scroll = QScrollArea()
        self.stack_scroll.setWidgetResizable(True)
        self.stack_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.stack_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.stack_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.stack_scroll.viewport().setAutoFillBackground(False)
        self.stack_scroll.setWidget(self.stack)

        self.report = ReportStream("REPORT", theme.YELLOW)
        self.report.setMinimumHeight(190)
        self.report.submitted.connect(self._stdin)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.stack_scroll)
        splitter.addWidget(self.report)
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([520, 300])
        root.addWidget(splitter, 1)

        self.tabs.changed.connect(self._tab_changed)
        self._refresh_gates()
        self._load_paper()
        self._sync_wallet()

    # ==================================================================
    # Scanner
    # ==================================================================

    def _scanner_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        card = Card(accent=theme.YELLOW)
        card.body.addWidget(section("ARBITRAGE SCANNER", theme.YELLOW))
        title = QLabel("USDC ↔ SOL research")
        title.setFont(theme.font(16, QFont.Weight.DemiBold))
        card.body.addWidget(title)

        self.scan_mode = ChoiceGroup(
            [
                ("once", "Single scan", "One full cross-venue round trip, then exit", ""),
                ("continuous", "Continuous scan", "Repeats on the interval until you stop it", ""),
                ("gate", "Scan + safety gate", "Adds live-trade eligibility checks — still no broadcast", "GATE"),
            ],
            theme.YELLOW,
        )
        card.body.addWidget(self.scan_mode)

        self.scan_interval = QDoubleSpinBox()
        self.scan_interval.setRange(2, 600)
        self.scan_interval.setDecimals(0)
        self.scan_interval.setValue(10)
        self.scan_interval.setSuffix(" s")
        self.scan_interval.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.scan_interval.setMinimumHeight(38)
        self.scan_interval.setFont(theme.font(13, mono=True))
        card.body.addWidget(field("Interval (continuous)", self.scan_interval))

        self.scan_run = primary_button("RUN SCANNER", theme.YELLOW)
        self.scan_run.clicked.connect(self._run_scanner)
        self.scan_stop = ghost_button("STOP", theme.RED)
        self.scan_stop.setEnabled(False)
        self.scan_stop.clicked.connect(self._stop)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addWidget(self.scan_run, 1)
        buttons.addWidget(self.scan_stop)
        card.body.addLayout(buttons)
        card.body.addStretch(1)

        wrap = QWidget()
        wrap.setLayout(QVBoxLayout())
        wrap.layout().setContentsMargins(0, 0, 0, 0)
        wrap.layout().addWidget(card)
        wrap.setFixedWidth(380)
        layout.addWidget(wrap)

        info = Card(pad=18, spacing=9)
        info.body.addWidget(section("RESEARCH CONTRACT", theme.MUTED))
        info.body.addWidget(self._subtitle("What this engine can and cannot do"))
        for label, ok, detail in (
            ("Jupiter quotes", True, "LIVE"),
            ("Wallet connection", True, "NONE"),
            ("Transaction signing", True, "DISABLED"),
            ("Broadcast", True, "DISABLED"),
            ("Funds at risk", True, "ZERO"),
        ):
            row = KeyRow(label)
            row.set(ok, detail)
            info.body.addWidget(row)
        info.body.addStretch(1)
        note = QLabel(
            "The scanner only reads quotes and computes round-trip edges. "
            "Real execution lives behind the separate gated executor."
        )
        note.setObjectName("Hint")
        note.setWordWrap(True)
        info.body.addWidget(note)
        layout.addWidget(info, 1)
        return page

    def _run_scanner(self) -> None:
        if self.runner.busy():
            self.report.write("An engine is already running.")
            return
        mode = self.scan_mode.value()
        argv = config.arb_argv(
            once=mode != "continuous",
            live=mode == "gate",
            interval=float(self.scan_interval.value()),
        )
        label = {"once": "SINGLE SCAN", "continuous": "CONTINUOUS SCAN", "gate": "SCAN + SAFETY GATE"}[mode]
        self.report.clear()
        self.report.set_status("RUNNING", theme.YELLOW)
        self.report.begin(label, argv, subtitle="no broadcast")
        self.scan_run.setEnabled(False)
        self.scan_stop.setEnabled(True)
        bus.activity.emit("MEGACRYPTO", label.lower())
        self.runner.start(argv, config.CRYPTO_DIR)

    # ==================================================================
    # Jupiter
    # ==================================================================

    def _jupiter_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        controls = Card(accent=theme.YELLOW)
        controls.body.addWidget(section("JUPITER QUOTE ROUTER", theme.YELLOW))
        title = QLabel("USDC → SOL")
        title.setFont(theme.font(16, QFont.Weight.DemiBold))
        controls.body.addWidget(title)

        self.quote_amount = QDoubleSpinBox()
        self.quote_amount.setRange(0.01, 10_000_000)
        self.quote_amount.setDecimals(2)
        self.quote_amount.setValue(10.0)
        self.quote_amount.setSingleStep(5)
        self.quote_amount.setSuffix(" USDC")
        self.quote_amount.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.quote_amount.setMinimumHeight(42)
        self.quote_amount.setFont(theme.font(15, QFont.Weight.DemiBold, mono=True))
        controls.body.addWidget(field("Input amount", self.quote_amount))

        presets = QHBoxLayout()
        presets.setSpacing(6)
        for amount in (10, 25, 100, 500):
            chip = ghost_button(f"${amount}", theme.YELLOW, height=30)
            chip.clicked.connect(lambda _=False, a=amount: self.quote_amount.setValue(a))
            presets.addWidget(chip)
        presets.addStretch(1)
        controls.body.addLayout(presets)

        self.quote_btn = primary_button("FETCH QUOTE", theme.YELLOW)
        self.quote_btn.clicked.connect(self._fetch_quote)
        controls.body.addWidget(self.quote_btn)
        controls.body.addStretch(1)

        note = QLabel("Read-only: pulls a live Jupiter route. Nothing is signed or broadcast.")
        note.setObjectName("Hint")
        note.setWordWrap(True)
        controls.body.addWidget(note)

        wrap = QWidget()
        wrap.setLayout(QVBoxLayout())
        wrap.layout().setContentsMargins(0, 0, 0, 0)
        wrap.layout().addWidget(controls)
        wrap.setFixedWidth(380)
        layout.addWidget(wrap)

        result = Card(pad=20, spacing=10)
        head = QHBoxLayout()
        head.addWidget(section("LIVE QUOTE", theme.MUTED))
        head.addStretch(1)
        self.quote_pill = Pill("IDLE", theme.DIM)
        head.addWidget(self.quote_pill)
        result.body.addLayout(head)

        self.quote_value = QLabel("— SOL")
        self.quote_value.setFont(theme.font(34, QFont.Weight.Bold, mono=True))
        self.quote_value.setStyleSheet(f"color: {theme.YELLOW};")
        result.body.addWidget(self.quote_value)

        self.quote_sub = QLabel("awaiting quote")
        self.quote_sub.setObjectName("Hint")
        result.body.addWidget(self.quote_sub)

        self.quote_impact = MetricRow("Price impact", "0.00%")
        self.quote_impact.set_value("0.00%", color=theme.DIM)
        result.body.addWidget(self.quote_impact)

        self.quote_rows = {}
        for key, label in (
            ("routes", "Route steps"),
            ("input", "Input"),
        ):
            row = KeyRow(label)
            row.set(False, "—", color=theme.DIM)
            result.body.addWidget(row)
            self.quote_rows[key] = row

        result.body.addStretch(1)
        result.body.addWidget(
            self._subtitle("Quoted through lite-api.jup.ag · research only")
        )
        layout.addWidget(result, 1)
        return page

    def _fetch_quote(self) -> None:
        amount = float(self.quote_amount.value())
        self.quote_btn.setEnabled(False)
        self.quote_btn.setText("QUOTING…")
        self.quote_pill.set_state("QUOTING", theme.YELLOW)

        def task():
            return _crypto_module().jupiter_quote(amount)

        def ok(quote):
            self.quote_btn.setEnabled(True)
            self.quote_btn.setText("FETCH QUOTE")
            out_amount = int(quote.get("outAmount", 0)) / 1_000_000_000
            impact = quote.get("priceImpact")
            routes = quote.get("routePlan") or []
            self.quote_value.setText(f"{out_amount:,.6f} SOL")
            self.quote_sub.setText(f"for ${amount:,.2f} USDC")
            self.quote_rows["input"].set(True, f"${amount:,.2f} USDC")
            if impact is not None:
                try:
                    pct = float(impact) * 100
                    tone = theme.GREEN if pct < 0.5 else theme.YELLOW if pct < 1.5 else theme.RED
                    self.quote_impact.set_value(f"{pct:.4f}%", color=tone)
                except (TypeError, ValueError):
                    self.quote_impact.set_value(str(impact), color=theme.MUTED)
            self.quote_rows["routes"].set(True, f"{len(routes)} hop(s)")
            self.quote_pill.set_state("LIVE QUOTE", theme.GREEN)
            bus.activity.emit("MEGACRYPTO", f"quote ${amount:,.2f} → {out_amount:,.6f} SOL")

        def failed(message: str):
            self.quote_btn.setEnabled(True)
            self.quote_btn.setText("FETCH QUOTE")
            self.quote_value.setText("— SOL")
            self.quote_sub.setText(f"✖ {message}")
            self.quote_impact.set_value("0.00%", color=theme.DIM)
            self.quote_pill.set_state("FAILED", theme.RED)
            bus.activity.emit("MEGACRYPTO", f"quote failed: {message}")

        self._call(task, ok, failed)

    # ==================================================================
    # Wallet
    # ==================================================================

    def _wallet_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        controls = Card(accent=theme.YELLOW)
        controls.body.addWidget(section("WATCH-ONLY WALLET", theme.YELLOW))
        title = QLabel("Public address")
        title.setFont(theme.font(16, QFont.Weight.DemiBold))
        controls.body.addWidget(title)

        self.wallet_input = QLineEdit()
        self.wallet_input.setPlaceholderText("Solana public address")
        self.wallet_input.setFont(theme.font(12, mono=True))
        self.wallet_input.setMinimumHeight(40)
        controls.body.addWidget(self.wallet_input)

        row = QHBoxLayout()
        row.setSpacing(9)
        save = primary_button("SAVE", theme.YELLOW, height=36)
        save.clicked.connect(self._save_wallet)
        refresh = ghost_button("REFRESH", theme.YELLOW)
        refresh.clicked.connect(self._refresh_balance)
        remove = ghost_button("REMOVE", theme.RED)
        remove.clicked.connect(self._remove_wallet)
        row.addWidget(save, 1)
        row.addWidget(refresh)
        row.addWidget(remove)
        controls.body.addLayout(row)

        hint = QLabel("Balances are read from Solana mainnet. Private keys and seed phrases are never stored.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        controls.body.addWidget(hint)
        controls.body.addStretch(1)

        wrap = QWidget()
        wrap.setLayout(QVBoxLayout())
        wrap.layout().setContentsMargins(0, 0, 0, 0)
        wrap.layout().addWidget(controls)
        wrap.setFixedWidth(380)
        layout.addWidget(wrap)

        results = Card(pad=20, spacing=12)
        results.body.addWidget(section("BALANCES", theme.MUTED))
        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.sol_stat = Stat("SOL", "—", "native balance", theme.YELLOW)
        self.usdc_stat = Stat("USDC", "—", "stablecoin balance", theme.GREEN)
        tiles.addWidget(self.sol_stat, 1)
        tiles.addWidget(self.usdc_stat, 1)
        results.body.addLayout(tiles)

        self.wallet_address = QLabel("no address saved")
        self.wallet_address.setFont(theme.font(10, mono=True))
        self.wallet_address.setStyleSheet(f"color: {theme.DIM};")
        self.wallet_address.setWordWrap(True)
        results.body.addWidget(self.wallet_address)
        results.body.addStretch(1)
        results.body.addWidget(self._subtitle("Watch-only — no signing capability"))
        layout.addWidget(results, 1)
        return page

    def _sync_wallet(self) -> None:
        address = str(self.cfg.get("wallet_address") or "")
        self.wallet_input.setText(address)
        self.wallet_address.setText(address or "no address saved")

    def _save_wallet(self) -> None:
        value = self.wallet_input.text().strip()
        if not _valid_address(value):
            QMessageBox.warning(self, "Invalid address", "That does not look like a Solana public address.")
            return
        self.cfg["wallet_address"] = value
        config.save_crypto_config(self.cfg)
        self._sync_wallet()
        bus.activity.emit("MEGACRYPTO", "watch-only wallet saved")
        self._refresh_balance()

    def _remove_wallet(self) -> None:
        self.cfg["wallet_address"] = ""
        config.save_crypto_config(self.cfg)
        self._sync_wallet()
        self.sol_stat.set("—", color=theme.YELLOW, hint="native balance")
        self.usdc_stat.set("—", color=theme.GREEN, hint="stablecoin balance")
        bus.activity.emit("MEGACRYPTO", "wallet removed")

    def _refresh_balance(self) -> None:
        address = str(self.cfg.get("wallet_address") or self.wallet_input.text().strip())
        if not _valid_address(address):
            QMessageBox.warning(self, "No wallet", "Save a valid watch-only address first.")
            return
        self.sol_stat.set("…", color=theme.YELLOW, hint="fetching")
        self.usdc_stat.set("…", color=theme.GREEN, hint="fetching")

        def task():
            return _crypto_module().wallet_balances(address)

        def ok(balances):
            sol, usdc = balances
            self.sol_stat.set(f"{sol:,.6f}", color=theme.YELLOW, hint="native balance")
            self.usdc_stat.set(f"${usdc:,.2f}", color=theme.GREEN, hint="stablecoin balance")
            bus.activity.emit("MEGACRYPTO", f"balances {sol:.4f} SOL / {usdc:.2f} USDC")

        def failed(message: str):
            self.sol_stat.set("—", color=theme.RED, hint=message[:40])
            self.usdc_stat.set("—", color=theme.RED, hint=message[:40])
            bus.activity.emit("MEGACRYPTO", f"balance lookup failed: {message}")

        self._call(task, ok, failed)

    # ==================================================================
    # Paper ledger
    # ==================================================================

    def _paper_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        form = Card(accent=theme.YELLOW)
        form.body.addWidget(section("PAPER TRADE", theme.YELLOW))
        title = QLabel("Record a trade")
        title.setFont(theme.font(16, QFont.Weight.DemiBold))
        form.body.addWidget(title)

        self.paper_asset = QLineEdit("SOL/USDC")
        self.paper_asset.setFont(theme.font(12, mono=True))
        self.paper_asset.setMinimumHeight(38)
        form.body.addWidget(field("Asset / pair", self.paper_asset))

        self.paper_capital = QDoubleSpinBox()
        self.paper_capital.setRange(0.0, 1_000_000)
        self.paper_capital.setDecimals(2)
        self.paper_capital.setValue(25.0)
        self.paper_capital.setSuffix(" USDC")
        self.paper_capital.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.paper_capital.setMinimumHeight(38)
        self.paper_capital.setFont(theme.font(13, mono=True))
        form.body.addWidget(field("Capital", self.paper_capital))

        self.paper_pnl = QDoubleSpinBox()
        self.paper_pnl.setRange(-1_000_000, 1_000_000)
        self.paper_pnl.setDecimals(2)
        self.paper_pnl.setSingleStep(0.5)
        self.paper_pnl.setSuffix(" USDC")
        self.paper_pnl.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.paper_pnl.setMinimumHeight(38)
        self.paper_pnl.setFont(theme.font(13, mono=True))
        form.body.addWidget(field("Simulated P&L", self.paper_pnl))

        record = primary_button("RECORD TRADE", theme.YELLOW, height=36)
        record.clicked.connect(self._record_paper)
        form.body.addWidget(record)

        self.paper_hint = QLabel(f"Max paper size ${self.cfg['max_trade_usdc']:.2f}")
        self.paper_hint.setObjectName("Hint")
        self.paper_hint.setWordWrap(True)
        form.body.addWidget(self.paper_hint)
        form.body.addStretch(1)

        wrap = QWidget()
        wrap.setLayout(QVBoxLayout())
        wrap.layout().setContentsMargins(0, 0, 0, 0)
        wrap.layout().addWidget(form)
        wrap.setFixedWidth(380)
        layout.addWidget(wrap)

        ledger = Card(pad=16, spacing=10)
        ledger.body.addWidget(section("LEDGER · crypto_arb/paper_trades.csv", theme.MUTED))
        self.paper_table = QTableWidget(0, 4)
        self.paper_table.setHorizontalHeaderLabels(["TIME", "ASSET", "CAPITAL", "P&L"])
        self.paper_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.paper_table.verticalHeader().setVisible(False)
        self.paper_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.paper_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.paper_table.setShowGrid(False)
        self.paper_table.setFont(theme.font(11, mono=True))
        ledger.body.addWidget(self.paper_table, 1)
        layout.addWidget(ledger, 1)
        return page

    def _record_paper(self) -> None:
        capital = float(self.paper_capital.value())
        pnl = float(self.paper_pnl.value())
        limit = float(self.cfg.get("max_trade_usdc") or 0)

        if capital <= 0 or capital > limit:
            QMessageBox.warning(
                self,
                "Outside paper limit",
                f"Capital must be greater than 0 and at most ${limit:.2f} (max_trade_usdc).",
            )
            return

        asset = self.paper_asset.text().strip().upper() or "SOL/USDC"
        config.CRYPTO_DIR.mkdir(parents=True, exist_ok=True)
        is_new = not config.PAPER_LOG.exists()
        with config.PAPER_LOG.open("a", newline="") as handle:
            writer = csv.writer(handle)
            if is_new:
                writer.writerow(["timestamp", "asset", "capital_usdc", "pnl_usdc", "mode"])
            writer.writerow([
                datetime.now(timezone.utc).isoformat(),
                asset,
                f"{capital:.6f}",
                f"{pnl:.6f}",
                "PAPER",
            ])
        self._load_paper()
        bus.activity.emit("MEGACRYPTO", f"paper trade {asset} ${capital:,.2f} → {pnl:+,.2f}")

    def _load_paper(self) -> None:
        if not hasattr(self, "paper_table"):
            return
        rows: list[list[str]] = []
        if config.PAPER_LOG.exists():
            try:
                with config.PAPER_LOG.open(newline="") as handle:
                    reader = csv.reader(handle)
                    next(reader, None)
                    rows = [row for row in reader if row]
            except OSError:
                rows = []

        self.paper_table.setRowCount(len(rows))
        for index, row in enumerate(reversed(rows[-200:])):
            stamp = (row[0] if len(row) > 0 else "").replace("T", " ")[:19]
            asset = row[1] if len(row) > 1 else ""
            capital = row[2] if len(row) > 2 else ""
            pnl = row[3] if len(row) > 3 else ""

            try:
                tone = theme.GREEN if float(pnl) >= 0 else theme.RED
            except (TypeError, ValueError):
                tone = theme.MUTED

            for column, value in enumerate((stamp, asset, f"${capital}", f"{pnl}")):
                item = QTableWidgetItem(value)
                if column == 3:
                    item.setForeground(QBrush(QColor(tone)))
                self.paper_table.setItem(index, column, item)

    # ==================================================================
    # Risk settings
    # ==================================================================

    def _risk_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        card = Card(accent=theme.YELLOW)
        card.body.addWidget(section("HARD RISK LIMITS", theme.YELLOW))
        title = QLabel("Scanner + executor thresholds")
        title.setFont(theme.font(16, QFont.Weight.DemiBold))
        card.body.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)
        self.risk_spins: dict[str, QDoubleSpinBox] = {}
        for index, (key, label, low, high, decimals, step) in enumerate(RISK_FIELDS):
            spin = QDoubleSpinBox()
            spin.setRange(low, high)
            spin.setDecimals(decimals)
            spin.setSingleStep(step)
            spin.setValue(float(self.cfg.get(key, low)))
            spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
            spin.setMinimumHeight(38)
            spin.setFont(theme.font(13, mono=True))
            self.risk_spins[key] = spin
            grid.addWidget(field(label, spin), index // 2, index % 2)
        card.body.addLayout(grid)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        save = primary_button("SAVE SETTINGS", theme.YELLOW, height=38)
        save.clicked.connect(self._save_risk)
        self.risk_status = QLabel("Saved to crypto_arb/megacrypto_config.json")
        self.risk_status.setObjectName("Hint")
        actions.addWidget(save)
        actions.addWidget(self.risk_status, 1)
        card.body.addLayout(actions)

        card.body.addWidget(
            self._subtitle(
                "These values gate the arbitrage safety checks and the gated executor. "
                "The daily loss limit is enforced by the scanner, not the GUI."
            )
        )
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _save_risk(self) -> None:
        for key, spin in self.risk_spins.items():
            value = spin.value()
            self.cfg[key] = int(round(value)) if key == "slippage_bps" else float(value)
        config.save_crypto_config(self.cfg)
        self.risk_status.setText("✓ saved just now")
        self.risk_status.setStyleSheet(f"color: {theme.GREEN}; font-size: 11px;")
        self.paper_hint.setText(f"Max paper size ${self.cfg['max_trade_usdc']:.2f}")
        bus.activity.emit("MEGACRYPTO", "risk settings saved")

    # ==================================================================
    # Live swap
    # ==================================================================

    def _live_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        gates = Card(accent=theme.GREEN)
        gates.body.addWidget(section("EXECUTION GATE", theme.GREEN))
        title = QLabel("Six checks, all required")
        title.setFont(theme.font(16, QFont.Weight.DemiBold))
        gates.body.addWidget(title)

        for key, label in (
            ("exec", "MEGATRON_LIVE_EXECUTION"),
            ("jupiter", "Jupiter API key"),
            ("key", "Signing key"),
            ("wallet", "Wallet address (env)"),
            ("switch", "Master kill switch"),
            ("script", "Executor script"),
        ):
            row = KeyRow(label)
            row.set(False, "—", color=theme.DIM)
            gates.body.addWidget(row)
            self.gate_rows[key] = row

        gates.body.addStretch(1)
        refresh = ghost_button("REFRESH GATES", theme.GREEN)
        refresh.clicked.connect(self._refresh_gates)
        gates.body.addWidget(refresh)

        wrap = QWidget()
        wrap.setLayout(QVBoxLayout())
        wrap.layout().setContentsMargins(0, 0, 0, 0)
        wrap.layout().addWidget(gates)
        wrap.setFixedWidth(380)
        layout.addWidget(wrap)

        actions = Card(pad=20, spacing=12)
        actions.body.addWidget(section("GATED SWAP", theme.MUTED))

        warning = QLabel(
            "This is the only path in the terminal that can move real funds. "
            "The executor simulates the swap first, then requires a typed YES before signing."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(f"color: {theme.YELLOW};")
        actions.body.addWidget(warning)

        self.buy_amount = QDoubleSpinBox()
        self.buy_amount.setRange(0.01, 100_000)
        self.buy_amount.setDecimals(2)
        self.buy_amount.setValue(min(10.0, float(self.cfg.get("max_trade_usdc") or 10.0)))
        self.buy_amount.setSuffix(" USDC")
        self.buy_amount.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.buy_amount.setMinimumHeight(38)
        self.buy_amount.setFont(theme.font(13, mono=True))

        self.sell_amount = QDoubleSpinBox()
        self.sell_amount.setRange(0.001, 100_000)
        self.sell_amount.setDecimals(3)
        self.sell_amount.setValue(0.1)
        self.sell_amount.setSuffix(" SOL")
        self.sell_amount.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.sell_amount.setMinimumHeight(38)
        self.sell_amount.setFont(theme.font(13, mono=True))

        amounts = QHBoxLayout()
        amounts.setSpacing(12)
        amounts.addWidget(field("BUY amount", self.buy_amount), 1)
        amounts.addWidget(field("SELL amount", self.sell_amount), 1)
        actions.body.addLayout(amounts)

        buy = primary_button("BUY USDC → SOL", theme.YELLOW, height=40)
        buy.clicked.connect(lambda: self._confirm_swap("BUY"))
        sell = ghost_button("SELL SOL → USDC", theme.YELLOW)
        sell.clicked.connect(lambda: self._confirm_swap("SELL"))
        actions.body.addWidget(buy)
        actions.body.addWidget(sell)

        status = primary_button("READ GATE STATUS (SAFE)", theme.GREEN, height=36)
        status.clicked.connect(lambda: self._run_executor("GATE STATUS", config.gate_argv()))
        actions.body.addWidget(status)

        actions.body.addStretch(1)
        actions.body.addWidget(
            self._subtitle("Order of operations: gates → fresh quote → simulation → typed YES → sign → broadcast")
        )
        layout.addWidget(actions, 1)
        return page

    def _refresh_gates(self) -> None:
        r = config.readiness()
        env = config.read_env()
        wallet_env = bool(env.get("SOLANA_WALLET_ADDRESS"))
        checks = {
            "exec": r["live_execution"],
            "jupiter": r["jupiter"],
            "key": r["solana_key"],
            "wallet": wallet_env,
            "switch": r["live_switch"],
            "script": r["executor"],
        }
        for key, ok in checks.items():
            label = "ON" if key == "switch" and ok else "OFF" if key == "switch" else (
                "TRUE" if key == "exec" and ok else "FALSE" if key == "exec" else (
                    "PRESENT" if key == "script" and ok else "MISSING" if key == "script" else (
                        "SET" if ok else "MISSING"
                    )
                )
            )
            self.gate_rows[key].set(ok, label)

    def _confirm_swap(self, direction: str) -> None:
        if not config.switch_on():
            QMessageBox.warning(
                self,
                "Master gate is OFF",
                "The master kill switch is OFF, so the executor will refuse.\n\n"
                "Enable the gate from the header only when you intend to trade.",
            )
            return

        amount = float(self.buy_amount.value() if direction == "BUY" else self.sell_amount.value())
        unit = "USDC" if direction == "BUY" else "SOL"

        box = QMessageBox(self)
        box.setWindowTitle("Confirm gated swap")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(f"{direction} {amount:g} {unit} on Solana mainnet")
        box.setInformativeText(
            "The executor pulls a fresh Jupiter quote, simulates the swap, then asks for YES "
            "in the console. A real transaction can be broadcast after that confirmation."
        )
        proceed = box.addButton("OPEN EXECUTOR", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("CANCEL", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not proceed:
            return

        self._run_executor(f"GATED {direction}", config.swap_argv(direction, amount))

    def _run_executor(self, label: str, argv: list[str]) -> None:
        if self.runner.busy():
            self.report.write("An engine is already running. Stop it first.")
            return
        self.report.clear()
        self.report.set_status("RUNNING", theme.YELLOW)
        self.report.begin(label, argv, subtitle="approval required")
        bus.activity.emit("MEGACRYPTO", label.lower())
        self.runner.start(argv, config.ROOT)

    # ==================================================================
    # Shared
    # ==================================================================

    def _subtitle(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Hint")
        label.setWordWrap(True)
        return label

    def _call(self, task, ok, failed) -> None:
        thread = CallThread(task, parent=self)
        thread.ok.connect(ok)
        thread.failed.connect(failed)
        thread.finished.connect(lambda t=thread: self._reap(t))
        self._threads.append(thread)
        thread.start()

    def _reap(self, thread: CallThread) -> None:
        if thread in self._threads:
            self._threads.remove(thread)
        thread.deleteLater()

    def _stream(self, line: str) -> None:
        self.report.feed(line)

    def _stdin(self, text: str) -> None:
        if self.runner.busy():
            self.runner.send(text)
        else:
            self.report.write("No engine is running.")

    def _stop(self) -> None:
        self.runner.stop()
        self.report.set_status("STOPPING", theme.YELLOW)
        self.report.write("stop requested…")

    def _exited(self, code: int) -> None:
        self.scan_run.setEnabled(True)
        self.scan_stop.setEnabled(False)
        if code == 0:
            self.report.write("✓ engine complete — no transaction broadcast without approval")
        elif code == 130:
            self.report.write("🛑 engine stopped by user")
        else:
            self.report.write(f"✖ engine exited with code {code}")
        self.report.finish(code, stopped=code == 130)
        bus.activity.emit("MEGACRYPTO", f"engine exit {code}")

    def shutdown(self) -> None:
        self.runner.shutdown()
        for thread in list(self._threads):
            thread.requestInterruption()

    def _tab_changed(self, value: str) -> None:
        order = [key for key, _ in TABS]
        self.stack.setCurrentIndex(order.index(value))
        if value == "paper":
            self._load_paper()
        elif value == "live":
            self._refresh_gates()
        elif value == "wallet":
            self._sync_wallet()


def _valid_address(value: str) -> bool:
    try:
        return bool(_crypto_module().valid_solana_address(value))
    except Exception:
        return bool(re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", value))
