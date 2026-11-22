"""MEGASTOCKS: AI hedge fund research, backtests and gated execution."""

from __future__ import annotations

import time

import json

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import analyst_dialog, catalog, config, theme
from ..components import (
    Card,
    KeyRow,
    TickerField,
    divider,
    ghost_button,
    primary_button,
    section,
)
from src.ai import compatibility as ai_compatibility
from src.ai import discovery as ai_discovery
from src.ai import preflight as ai_preflight

from ..ai_status import AiStatusDialog
from ..engine import CallThread, ProcessRunner, bus
from ..workspace import ChartGrid, ResearchWorkspace, TickerTabs

MODES = [
    ("full", "Full AI hedge fund", "Valuation · risk · portfolio manager", ""),
    ("ollama", "Local Ollama stack", "Your local model — no API cost", "LOCAL"),
    ("reasoning", "Full AI + reasoning", "Prints every analyst thesis to the stream", ""),
    ("backtest", "Backtester", "Replays the signal stack over history", ""),
    ("ollama_reasoning", "Ollama + reasoning", "Local model with full thesis output", ""),
    ("live", "AI hedge fund + Alpaca", "Routes non-hold signals after per-order approval", "LIVE"),
]


class StocksPage(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self._queue: list[tuple[str, list[str]]] = []
        self._names: list[str] = []
        self._total = 0
        self._done = 0
        self._code = 0
        self._stop_requested = False
        self._catalog: catalog.Catalog | None = None
        self._selected: list[str] = []
        self._local_models: set[str] = set()
        self._settings = QSettings("MEGATRON", "ResearchDesk")
        self._ai_snapshot = None
        self._ai_running = False
        self._local_only = bool(self._settings.value("ai/local_only", False, type=bool))
        self._auto = bool(self._settings.value("ai/auto", False, type=bool))
        self._running_ticker = ""
        self._rail_collapsed = bool(self._settings.value("ui/rail_collapsed", False, type=bool))
        try:
            self._rail_ratio = float(self._settings.value("ui/rail_ratio", 0.25))
        except (TypeError, ValueError):
            self._rail_ratio = 0.25
        self._rail_ratio = min(0.27, max(0.22, self._rail_ratio))
        self._workspace_orientation = ""
        self._applying_layout = False

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.rail_strip = QFrame()
        self.rail_strip.setObjectName("RailStrip")
        self.rail_strip.setFixedWidth(25)
        strip_layout = QVBoxLayout(self.rail_strip)
        strip_layout.setContentsMargins(2, 8, 2, 8)
        strip_layout.setSpacing(0)
        self.rail_toggle = QPushButton("‹")
        self.rail_toggle.setObjectName("RailToggle")
        self.rail_toggle.setFixedSize(20, 38)
        self.rail_toggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rail_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rail_toggle.setToolTip("Collapse the control rail")
        self.rail_toggle.clicked.connect(self._toggle_rail)
        strip_layout.addWidget(self.rail_toggle, 0, Qt.AlignmentFlag.AlignTop)
        strip_layout.addStretch(1)
        root.addWidget(self.rail_strip)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(5)

        self.rail = QWidget()
        self.rail.setMinimumWidth(300)
        self.rail.setMaximumWidth(560)
        self.rail.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        rail_layout = QVBoxLayout(self.rail)
        rail_layout.setContentsMargins(0, 0, 0, 0)
        rail_layout.setSpacing(8)

        config_widget = QWidget()
        config_widget.setMinimumWidth(0)
        config_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        config_layout = QVBoxLayout(config_widget)
        config_layout.setContentsMargins(0, 0, 8, 0)
        config_layout.setSpacing(8)

        # -- tickers -----------------------------------------------------
        universe = Card(accent=theme.ORANGE, pad=12, spacing=7)
        universe.body.addWidget(section("UNIVERSE", theme.ORANGE))
        title = QLabel("Ticker selection")
        title.setFont(theme.font(16, QFont.Weight.DemiBold))
        universe.body.addWidget(title)
        self.tickers = TickerField(theme.ORANGE)
        universe.body.addWidget(self.tickers)
        self.ticker_tabs = TickerTabs()
        universe.body.addWidget(self.ticker_tabs)
        hint = QLabel("Space or comma separated. Click a tab to focus its chart and report.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        universe.body.addWidget(hint)
        config_layout.addWidget(universe)

        # -- modes -------------------------------------------------------
        modes = Card(accent=theme.ORANGE, pad=12, spacing=7)
        modes.body.addWidget(section("RESEARCH CONFIG", theme.ORANGE))
        mode_label = QLabel("MODE")
        mode_label.setFont(theme.font(9, QFont.Weight.DemiBold, mono=True, spacing=1.4))
        mode_label.setStyleSheet(f"color: {theme.DIM};")
        modes.body.addWidget(mode_label)
        self.modes = QComboBox()
        self.modes.setMinimumHeight(34)
        self.modes.setMinimumWidth(0)
        self.modes.setMinimumContentsLength(8)
        self.modes.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.modes.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.modes.view().setMinimumWidth(340)
        for value, title, subtitle, tag in MODES:
            label = f"{title}" + (f"  ·  {tag}" if tag else "")
            self.modes.addItem(label, value)
            self.modes.setItemData(self.modes.count() - 1, subtitle, Qt.ItemDataRole.ToolTipRole)
        modes.body.addWidget(self.modes)

        modes.body.addWidget(divider())
        modes.body.addWidget(section("RESEARCH STAFF", theme.MUTED))

        staff_row = QHBoxLayout()
        staff_row.setSpacing(8)
        staff_text = QVBoxLayout()
        staff_text.setSpacing(2)
        self.staff_count = QLabel("Loading registry…")
        self.staff_count.setFont(theme.font(12, QFont.Weight.DemiBold))
        self.staff_note = QLabel("Analysts come from the engine registry")
        self.staff_note.setObjectName("Hint")
        self.staff_note.setWordWrap(True)
        staff_text.addWidget(self.staff_count)
        staff_text.addWidget(self.staff_note)
        self.edit_staff = ghost_button("EDIT", theme.ORANGE, height=30)
        self.edit_staff.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.edit_staff.setEnabled(False)
        self.edit_staff.clicked.connect(self.edit_analysts)
        self.focus_staff = ghost_button("F5", theme.GREEN, height=30)
        self.focus_staff.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.focus_staff.setEnabled(False)
        self.focus_staff.setToolTip("FOCUS 5 · Buffett · Graham · Wood · Technical · Fundamentals")
        self.focus_staff.clicked.connect(self.focus_analysts)
        staff_row.addLayout(staff_text, 1)
        staff_row.addWidget(self.edit_staff)
        staff_row.addWidget(self.focus_staff)
        modes.body.addLayout(staff_row)

        model_label = QLabel("MODEL")
        model_label.setFont(theme.font(9, QFont.Weight.DemiBold, mono=True, spacing=1.4))
        model_label.setStyleSheet(f"color: {theme.DIM};")
        modes.body.addWidget(model_label)
        self.model = QComboBox()
        self.model.setMinimumHeight(34)
        self.model.setMinimumWidth(0)
        self.model.setMinimumContentsLength(8)
        self.model.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.model.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.model.view().setMinimumWidth(430)
        self.model.setEnabled(False)
        modes.body.addWidget(self.model)

        ai_row = QHBoxLayout()
        ai_row.setSpacing(8)
        self.ai_line = QLabel("AI inventory: waiting for the registry…")
        self.ai_line.setObjectName("Hint")
        self.ai_line.setWordWrap(True)
        self.ai_btn = ghost_button("AI STATUS", theme.MUTED, height=30)
        self.ai_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.ai_btn.clicked.connect(self._open_ai_status)
        ai_row.addWidget(self.ai_line, 1)
        ai_row.addWidget(self.ai_btn)
        modes.body.addLayout(ai_row)

        options = QHBoxLayout()
        options.setSpacing(12)
        self.local_only_box = QCheckBox("LOCAL ONLY")
        self.local_only_box.setChecked(self._local_only)
        self.local_only_box.setToolTip("Hide configured cloud models and run local models only")
        self.local_only_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.auto_box = QCheckBox("AUTO PICK")
        self.auto_box.setChecked(self._auto)
        self.auto_box.setToolTip("Automatically pick the best compatible model for the research mode")
        self.auto_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        options.addWidget(self.local_only_box)
        options.addWidget(self.auto_box)
        options.addStretch(1)
        modes.body.addLayout(options)
        config_layout.addWidget(modes)

        # -- gate --------------------------------------------------------
        gate = Card(pad=12, spacing=6)
        gate.body.addWidget(section("EXECUTION GATE", theme.MUTED))
        self.row_switch = KeyRow("Master kill switch")
        self.row_alpaca = KeyRow("Alpaca trading keys")
        gate.body.addWidget(self.row_switch)
        gate.body.addWidget(self.row_alpaca)
        self.gate_note = QLabel("Research mode never sends an order.")
        self.gate_note.setObjectName("Hint")
        self.gate_note.setWordWrap(True)
        gate.body.addWidget(self.gate_note)
        config_layout.addStretch(1)

        config_scroll = QScrollArea()
        config_scroll.setWidgetResizable(True)
        config_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        config_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        config_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        config_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        config_scroll.viewport().setAutoFillBackground(False)
        config_scroll.setWidget(config_widget)
        rail_layout.addWidget(config_scroll, 1)
        rail_layout.addWidget(gate)

        # -- actions -----------------------------------------------------
        self.run_btn = primary_button("RUN ANALYSIS", theme.ORANGE)
        self.run_btn.clicked.connect(self.run)
        self.stop_btn = ghost_button("STOP", theme.RED)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(self.run_btn, 1)
        actions.addWidget(self.stop_btn)
        rail_layout.addLayout(actions)

        # -- chart grid + isolated research output ----------------------
        self.chart_grid = ChartGrid(theme.ORANGE)
        self.research_ws = ResearchWorkspace(theme.ORANGE)
        self.research_ws.decision_ready.connect(self.chart_grid.set_alert)
        self.research_ws.submitted.connect(self._stdin)
        self.research_ws.ticker_selected.connect(self._focus_ticker)

        self.workspace = QSplitter(Qt.Orientation.Vertical)
        self.workspace.setChildrenCollapsible(False)
        self.workspace.setHandleWidth(5)
        self.workspace.addWidget(self.chart_grid)
        self.workspace.addWidget(self.research_ws)
        self.workspace.setStretchFactor(0, 3)
        self.workspace.setStretchFactor(1, 2)
        self.workspace.setSizes([430, 320])

        self.splitter.addWidget(self.rail)
        self.splitter.addWidget(self.workspace)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        root.addWidget(self.splitter, 1)

        self.runner = ProcessRunner(self)
        self.runner.output.connect(self._on_output)
        self.runner.started.connect(self._started)
        self.runner.exited.connect(self._exited)

        bus.switch_changed.connect(lambda _on: self.refresh_gate())
        self.refresh_gate()

        self._loader = CallThread(catalog.load, parent=self)
        self._loader.ok.connect(self._catalog_ready)
        self._loader.failed.connect(self._catalog_failed)
        self._loader.start()
        saved_mode = str(self._settings.value("research/mode", "full") or "full")
        mode_index = self.modes.findData(saved_mode)
        if mode_index >= 0:
            self.modes.setCurrentIndex(mode_index)
        self.modes.currentIndexChanged.connect(self._mode_changed)
        self.model.currentIndexChanged.connect(self._model_changed)
        self.local_only_box.toggled.connect(self._set_local_only)
        self.auto_box.toggled.connect(self._set_auto)
        self.ticker_tabs.ticker_selected.connect(self._focus_ticker)
        self._chart_timer = QTimer(self)
        self._chart_timer.setSingleShot(True)
        self._chart_timer.setInterval(500)
        self._chart_timer.timeout.connect(self._preview_chart)
        self.tickers.edit.textChanged.connect(self._tickers_edited)
        self.splitter.splitterMoved.connect(self._splitter_moved)
        self.workspace.splitterMoved.connect(self._workspace_moved)
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.setInterval(30)
        self._layout_timer.timeout.connect(self._apply_responsive)

        saved_tickers = str(self._settings.value("research/tickers", "") or "").strip()
        if saved_tickers:
            self.tickers.edit.setText(saved_tickers)
        QTimer.singleShot(0, self._restore_layout)

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    def _catalog_ready(self, result: object) -> None:
        if not isinstance(result, catalog.Catalog):
            self._catalog_failed("The registry reader returned an unexpected payload.")
            return
        self._catalog = result
        allowed = set(result.keys())
        stored = self._settings.value("research/analysts", [])
        if isinstance(stored, str):
            stored = [item for item in stored.split(",") if item]
        picked = [key for key in (stored or []) if key in allowed]
        self._selected = picked or list(result.keys())

        self._populate_models()
        self._load_ai()
        self.research_ws.set_roster(result.by_name())
        self.edit_staff.setEnabled(True)
        self.focus_staff.setEnabled(True)
        self.staff_note.setText("Selection never enables execution")

        if not result.fresh:
            self.staff_count.setToolTip("Loaded from the local catalog cache.")
        self._sync_staff()

    def _catalog_failed(self, message: str) -> None:
        self._catalog = None
        self.edit_staff.setEnabled(False)
        self.focus_staff.setEnabled(False)
        self.staff_count.setText("Registry unavailable")
        self.staff_note.setText(str(message)[:120])
        self.staff_note.setStyleSheet(f"color: {theme.RED};")

    def _sync_staff(self) -> None:
        if self._catalog is None:
            return
        total = len(self._catalog.analysts)
        chosen = [a for a in self._catalog.analysts if a.key in set(self._selected)]
        if not chosen:
            self.staff_count.setText("No analysts selected")
            self.staff_count.setStyleSheet(f"color: {theme.RED};")
            return
        self.staff_count.setText(f"{len(chosen)} of {total} analysts")
        modern = sum(1 for a in chosen if a.specialist)
        self.staff_count.setStyleSheet(f"color: {theme.TEXT};")
        hint = f"{len(chosen) - modern} legends · {modern} specialists · research only"
        if len(chosen) == total:
            hint += " · FOCUS 5 is faster"
        self.staff_note.setText(hint)
        self.staff_note.setStyleSheet(f"color: {theme.DIM};")

    def focus_analysts(self) -> None:
        if self._catalog is None:
            return
        allowed = set(self._catalog.keys())
        picked = [key for key in analyst_dialog.FOCUS_KEYS if key in allowed]
        if not picked:
            return
        self._selected = picked
        self._settings.setValue("research/analysts", picked)
        self._sync_staff()

    def edit_analysts(self) -> None:
        if self._catalog is None:
            QMessageBox.warning(self, "Registry unavailable", "The analyst registry is still loading or could not be read.")
            return
        picked = analyst_dialog.ask(self.window(), self._catalog, self._selected, theme.ORANGE)
        if picked is None:
            return
        self._selected = picked
        self._settings.setValue("research/analysts", picked)
        self._sync_staff()

    def _selected_names(self) -> list[str]:
        if self._catalog is None:
            return []
        chosen = set(self._selected)
        return [a.name for a in self._catalog.analysts if a.key in chosen]

    # ------------------------------------------------------------------
    # AI runtime discovery / preflight
    # ------------------------------------------------------------------

    def _task_for_mode(self, mode: str) -> str:
        if mode == "backtest":
            return "backtesting"
        if mode in {"full", "reasoning", "live"}:
            return "multi_agent"
        return "analyst_research"

    def _cloud_specs(self) -> list[dict]:
        if self._catalog is None:
            return []
        return [model for model in self._catalog.models if model.get("provider") != "Ollama"]

    def _ai_snapshot_task(self):
        return ai_discovery.build_snapshot(cloud_models=self._cloud_specs())

    def _load_ai(self) -> None:
        if self._ai_running:
            return
        self._ai_running = True
        self.ai_line.setText("AI inventory: scanning runtimes…")
        self._ai_thread = CallThread(self._ai_snapshot_task, parent=self)
        self._ai_thread.ok.connect(self._ai_ready)
        self._ai_thread.failed.connect(self._ai_failed)
        self._ai_thread.start()

    def _ai_ready(self, snapshot: object) -> None:
        self._ai_running = False
        if isinstance(snapshot, ai_discovery.Snapshot):
            self._ai_snapshot = snapshot
        self._populate_models()

    def _ai_failed(self, message: str) -> None:
        self._ai_running = False
        self.ai_line.setText(f"AI discovery failed: {str(message)[:90]}")
        self.ai_line.setStyleSheet(f"color: {theme.RED};")

    def _populate_models(self) -> None:
        snapshot = self._ai_snapshot
        self.model.blockSignals(True)
        self.model.clear()
        if snapshot is None:
            self.model.addItem("Scanning AI runtimes…", None)
            self.model.setEnabled(False)
            self.model.blockSignals(False)
            self._update_ai_line()
            return

        models = [m for m in snapshot.models(local_only=self._local_only) if m.available and m.configured]
        models.sort(key=lambda m: (0 if m.local else 1, m.name.lower()))
        for m in models:
            dot = "●" if m.local else "○"
            label = f"{dot} {m.name}"
            if not m.local:
                label = f"{dot} {m.provider} · {m.name}"
            if m.parameter_size:
                label += f" · {m.parameter_size}"
            self.model.addItem(
                label,
                {"id": m.id, "name": m.name, "provider": m.provider, "local": m.local, "runtime": m.runtime_id},
            )
            self.model.setItemData(
                self.model.count() - 1,
                f"{m.provider} · {m.name} · {'local' if m.local else 'cloud'}",
                Qt.ItemDataRole.ToolTipRole,
            )

        target = ""
        if self._auto:
            best = ai_preflight.select_auto(snapshot, self._task_for_mode(self._mode()), local_only=self._local_only)
            target = best.id if best else ""
        if not target:
            target = self._settings.value("ai/model_id", "")
        index = self._index_for(target) if target else -1
        if index < 0:
            saved_name = self._settings.value("research/model", "")
            index = self._index_for_name(saved_name) if saved_name else -1
        if index < 0 and self.model.count():
            index = 0
        if index >= 0:
            self.model.setCurrentIndex(index)
            if not self._settings.value("ai/model_id", ""):
                data = self.model.itemData(index)
                if isinstance(data, dict):
                    self._settings.setValue("ai/model_id", data.get("id", ""))
                    self._settings.setValue("research/model", data.get("name", ""))
        self.model.setEnabled(self.model.count() > 0)
        self.model.blockSignals(False)
        self._update_ai_line()

    def _index_for(self, model_id: str) -> int:
        for index in range(self.model.count()):
            data = self.model.itemData(index)
            if isinstance(data, dict) and data.get("id") == model_id:
                return index
        return -1

    def _index_for_name(self, name: str) -> int:
        for index in range(self.model.count()):
            data = self.model.itemData(index)
            if isinstance(data, dict) and data.get("name") == name:
                return index
        return -1

    def _update_ai_line(self) -> None:
        snapshot = self._ai_snapshot
        if snapshot is None:
            self.ai_line.setText("AI inventory: waiting for the registry…")
            self.ai_line.setStyleSheet(f"color: {theme.DIM};")
            return
        entry = self.model.currentData()
        text = ai_discovery.summary_line(snapshot)
        color = theme.MUTED
        if isinstance(entry, dict):
            model, _runtime = snapshot.model(entry.get("id", ""))
            if model is not None:
                verdict = ai_compatibility.evaluate(model, self._task_for_mode(self._mode()))
                text += f" · {verdict.status}"
                color = {
                    "READY": theme.GREEN,
                    "READY WITH LIMITATIONS": theme.YELLOW,
                    "NOT SUPPORTED": theme.RED,
                    "UNAVAILABLE": theme.DIM,
                }.get(verdict.status, theme.MUTED)
                lines = verdict.reasons + verdict.notes
                self.ai_line.setToolTip("\n".join(lines) or "All declared requirements are met.")
        self.ai_line.setText(text)
        self.ai_line.setStyleSheet(f"color: {color};")

    def _model_changed(self, _index: int = 0) -> None:
        entry = self.model.currentData()
        if isinstance(entry, dict):
            self._settings.setValue("ai/model_id", entry.get("id", ""))
            self._settings.setValue("research/model", entry.get("name", ""))
        self._update_ai_line()

    def _set_default_model(self, model_id: str) -> None:
        index = self._index_for(model_id)
        if index >= 0:
            self.model.setCurrentIndex(index)
            self._settings.setValue("ai/model_id", model_id)

    def _set_local_only(self, on: bool) -> None:
        self._local_only = on
        self.local_only_box.blockSignals(True)
        self.local_only_box.setChecked(on)
        self.local_only_box.blockSignals(False)
        self._settings.setValue("ai/local_only", on)
        self._populate_models()

    def _set_auto(self, on: bool) -> None:
        self._auto = on
        self.auto_box.blockSignals(True)
        self.auto_box.setChecked(on)
        self.auto_box.blockSignals(False)
        self._settings.setValue("ai/auto", on)
        self._populate_models()

    def _open_ai_status(self) -> None:
        entry = self.model.currentData()
        dialog = AiStatusDialog(
            self._ai_snapshot,
            self._ai_snapshot_task,
            task_id=self._task_for_mode(self._mode()),
            local_only=self._local_only,
            auto=self._auto,
            selected_id=entry.get("id") if isinstance(entry, dict) else None,
            parent=self.window(),
        )
        dialog.default_changed.connect(self._set_default_model)
        dialog.local_only_changed.connect(self._set_local_only)
        dialog.auto_changed.connect(self._set_auto)
        dialog.exec()
        self._ai_snapshot = dialog.snapshot()
        self._populate_models()

    # ------------------------------------------------------------------
    # Gate
    # ------------------------------------------------------------------

    def refresh_gate(self) -> None:
        r = config.readiness()
        self.row_switch.set(r["live_switch"], "ON" if r["live_switch"] else "OFF")
        self.row_alpaca.set(r["alpaca"], r["alpaca_mode"].upper() if r["alpaca"] else "MISSING")
        self.gate_note.setText(
            "Alpaca execution asks for approval on every order."
            if r["alpaca"]
            else "Add ALPACA_API_KEY and ALPACA_SECRET_KEY to .env to enable execution."
        )

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self) -> None:
        if self.runner.busy():
            return

        tickers = self.tickers.tickers()
        if not tickers:
            QMessageBox.warning(self, "No tickers", "Enter at least one ticker symbol to analyze.")
            return

        if self._catalog is None:
            QMessageBox.warning(
                self,
                "Analyst registry unavailable",
                "The engine's analyst registry could not be read, so research cannot start.\n\n"
                "Check that the poetry environment is available and try again.",
            )
            return

        if not self._selected:
            self.edit_analysts()
            if not self._selected:
                return

        mode = self._mode()
        model = self.model.currentData()
        if not isinstance(model, dict):
            QMessageBox.warning(self, "No model", "Pick an installed local model or a configured cloud model.")
            return

        if self._ai_snapshot is None or time.time() - self._ai_snapshot.generated_at > 60:
            try:
                self._ai_snapshot = self._ai_snapshot_task()
            except Exception as exc:
                QMessageBox.warning(self, "AI preflight failed", f"Could not scan AI runtimes:\n{exc}")
                return

        preflight = ai_preflight.check(
            self._ai_snapshot,
            model.get("id"),
            task_id=self._task_for_mode(mode),
            local_only=self._local_only,
        )
        if not preflight.ok:
            lines = [preflight.status, *preflight.reasons]
            if preflight.alternatives:
                lines += ["", "Compatible alternatives:"]
                lines += [
                    f"· {candidate.name} — {ai_compatibility.evaluate(candidate, self._task_for_mode(mode)).status}"
                    for candidate in preflight.alternatives[:4]
                ]
            lines += ["", "Open AI STATUS to test a model or change the default."]
            QMessageBox.warning(self, "Model preflight failed", "\n".join(lines))
            return

        if mode == "live":
            if not config.switch_on():
                QMessageBox.warning(
                    self,
                    "Live trading is OFF",
                    "The master kill switch is OFF, so the execution path will refuse every order.\n\n"
                    "Enable the master gate from the header first.",
                )
                return
            answer = QMessageBox.question(
                self,
                "Confirm live path",
                "This run can place real Alpaca orders.\n\n"
                "Every order is printed first and needs your explicit approval in the console.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        # Snapshot: later edits cannot change a run that is already queued.
        analysts = list(self._selected)
        names = self._selected_names()
        ollama = model.get("provider") == "Ollama" or mode in {"ollama", "ollama_reasoning"}
        if model.get("provider") == "Ollama":
            self._local_models.add(str(model.get("name") or ""))

        self._queue = [
            (ticker, config.stocks_argv(ticker, mode, analysts=analysts, model=model.get("name", ""), ollama=ollama))
            for ticker in tickers
        ]
        self._names = names
        self._total = len(self._queue)
        self._done = 0
        self._code = 0
        self._stop_requested = False

        self.chart_grid.set_tickers(tickers)
        self.ticker_tabs.set_tickers(tickers)
        self.research_ws.reset(tickers)
        self._settings.setValue("research/model", model.get("name", ""))
        self._settings.setValue("research/tickers", " ".join(tickers))
        self._settings.setValue("research/mode", mode)
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        bus.activity.emit("MEGASTOCKS", f"{self._total} ticker(s) · {len(names)} analysts · {config.STOCK_MODES[mode][0]}")
        self._next()

    def _next(self) -> None:
        if not self._queue:
            self._finish()
            return

        ticker, argv = self._queue.pop(0)
        self._done += 1
        self._running_ticker = ticker
        mode_label = config.STOCK_MODES[self._mode()][0]
        self.chart_grid.load_ticker(ticker)
        self.chart_grid.focus_ticker(ticker)
        self.ticker_tabs.select(ticker)
        self.research_ws.begin_run(ticker, mode_label, self._names, self._done, self._total)
        self.research_ws.set_status(ticker, "STARTING · MODEL LOAD", theme.BLUE)
        self.runner.start(argv, config.ROOT)

    @staticmethod
    def _sentinel_payloads(text: str, marker: str) -> list[dict]:
        """Decode one or more JSON payloads, even when terminal redraws merge lines."""
        payloads: list[dict] = []
        decoder = json.JSONDecoder()
        index = text.find(marker)
        while index != -1:
            start = index + len(marker)
            while start < len(text) and text[start] == " ":
                start += 1
            try:
                payload, end = decoder.raw_decode(text[start:])
            except ValueError:
                break
            if isinstance(payload, dict):
                payloads.append(payload)
            index = text.find(marker, start + end)
        return payloads

    def _started(self, command: str) -> None:
        if self._running_ticker:
            self.research_ws.show_command(self._running_ticker, command)

    def _on_output(self, line: str) -> None:
        """Route engine sentinels to the active ticker's isolated report."""
        text = str(line)
        ticker = self._running_ticker
        if "@@MEGATRON_PROGRESS@@" in text:
            for payload in self._sentinel_payloads(text, "@@MEGATRON_PROGRESS@@"):
                self.research_ws.progress_event(ticker, payload)
            return
        if "@@MEGATRON_PROMPT@@" in text:
            for payload in self._sentinel_payloads(text, "@@MEGATRON_PROMPT@@"):
                QTimer.singleShot(0, lambda data=payload: self._ask_engine(data))
            return
        self.research_ws.feed(ticker, text)

    def _ask_engine(self, payload: dict) -> None:
        message = str(payload.get("message") or "The engine is waiting for confirmation.")
        ticker = self._running_ticker
        self.research_ws.set_status(ticker, "WAITING FOR INPUT", theme.YELLOW)
        answer = QMessageBox.question(
            self,
            "Engine confirmation",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        approved = answer == QMessageBox.StandardButton.Yes
        self.runner.send("y" if approved else "n")
        self.research_ws.write(ticker, f"Confirmation: {'YES' if approved else 'NO'}")
        self.research_ws.set_status(ticker, "RUNNING", theme.ORANGE)

    def _exited(self, code: int) -> None:
        stopped = self._stop_requested or code == 130
        ticker = self._running_ticker
        self.research_ws.end_run(ticker, code, stopped=stopped)
        self.chart_grid.finish_run(ticker, code, stopped)
        if code == 130 or self._stop_requested:
            self._queue.clear()
            self._code = 130
        elif code != 0:
            self._code = self._code or code
        self._next()

    def _finish(self) -> None:
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        stopped = self._code == 130 or self._stop_requested
        ticker = self._running_ticker
        if ticker:
            self.research_ws.set_status(
                ticker,
                "STOPPED" if stopped else "DONE",
                theme.YELLOW if stopped else theme.GREEN,
            )
        bus.activity.emit("MEGASTOCKS", "run stopped" if stopped else "run finished")

    def _tickers_edited(self, _text: str) -> None:
        self.ticker_tabs.set_tickers(self.tickers.tickers())
        self._chart_timer.start()

    def _preview_chart(self) -> None:
        if self.runner.busy():
            return
        tickers = self.tickers.tickers()
        self.ticker_tabs.set_tickers(tickers)
        self.chart_grid.set_tickers(tickers)
        if tickers:
            self._settings.setValue("research/tickers", " ".join(tickers))

    def _focus_ticker(self, ticker: str) -> None:
        symbol = str(ticker or "").strip().upper()
        if not symbol:
            return
        self.ticker_tabs.select(symbol)
        self.chart_grid.focus_ticker(symbol)
        self.research_ws.focus_ticker(symbol)

    def stop(self) -> None:
        self._queue.clear()
        self._stop_requested = True
        self._code = 130
        self.runner.stop()
        if self._running_ticker:
            self.research_ws.set_status(self._running_ticker, "STOPPING", theme.YELLOW)

    def _stdin(self, text: str) -> None:
        if self.runner.busy():
            self.runner.send(text)
        else:
            ticker = self._running_ticker or self.research_ws.active_ticker()
            if ticker:
                self.research_ws.write(ticker, "No engine is running.")

    # ------------------------------------------------------------------
    # Responsive split / persisted layout
    # ------------------------------------------------------------------

    def _mode(self) -> str:
        return str(self.modes.currentData() or "full")

    def _mode_changed(self, _index: int = 0) -> None:
        self._settings.setValue("research/mode", self._mode())
        self._update_ai_line()

    def _splitter_moved(self, _position: int, _index: int) -> None:
        if self._rail_collapsed:
            return
        sizes = self.splitter.sizes()
        total = sum(sizes)
        if total and sizes[0] > 0:
            self._rail_ratio = max(0.18, min(0.42, sizes[0] / total))
            self._settings.setValue("ui/rail_ratio", self._rail_ratio)

    def _workspace_moved(self, _position: int, _index: int) -> None:
        key = "ui/workspace_h" if self.workspace.orientation() == Qt.Orientation.Horizontal else "ui/workspace_v"
        self._settings.setValue(key, self.workspace.sizes())

    def _toggle_rail(self) -> None:
        self._set_rail_collapsed(not self._rail_collapsed)

    def _set_rail_collapsed(self, collapsed: bool, *, persist: bool = True) -> None:
        was_collapsed = self._rail_collapsed
        self._rail_collapsed = collapsed
        if collapsed:
            if not was_collapsed:
                sizes = self.splitter.sizes()
                if len(sizes) > 1 and sum(sizes) and sizes[0] > 0:
                    self._rail_ratio = max(0.18, min(0.42, sizes[0] / sum(sizes)))
            self.rail.setVisible(False)
            self.splitter.setSizes([0, max(1, self.splitter.width())])
            self.rail_toggle.setText("›")
            self.rail_toggle.setToolTip("Expand the control rail")
        else:
            self.rail.setVisible(True)
            self._apply_rail_ratio()
            self.rail_toggle.setText("‹")
            self.rail_toggle.setToolTip("Collapse the control rail")
        if persist:
            self._settings.setValue("ui/rail_collapsed", collapsed)
            self._settings.setValue("ui/rail_ratio", self._rail_ratio)

    def _apply_rail_ratio(self) -> None:
        if self._rail_collapsed or not self.rail.isVisible():
            return
        total = self.splitter.width()
        if total < 320:
            return
        left = int(total * self._rail_ratio)
        left = max(300, min(560, left, max(300, total - 330)))
        self.splitter.setSizes([left, max(1, total - left)])

    def _saved_sizes(self, key: str) -> list[int]:
        raw = self._settings.value(key, [])
        if isinstance(raw, str):
            raw = raw.strip("[]").replace(",", " ").split()
        sizes: list[int] = []
        try:
            for value in raw or []:
                size = int(value)
                if size > 0:
                    sizes.append(size)
        except (TypeError, ValueError):
            return []
        return sizes

    def _apply_responsive(self) -> None:
        width = self.width()
        if width < 320 or self._applying_layout:
            return
        horizontal = width >= 1350
        orientation = Qt.Orientation.Horizontal if horizontal else Qt.Orientation.Vertical
        if self.workspace.orientation() != orientation:
            self._applying_layout = True
            self.workspace.setOrientation(orientation)
            self.workspace.setStretchFactor(0, 3)
            self.workspace.setStretchFactor(1, 2)
            saved = self._saved_sizes("ui/workspace_h" if horizontal else "ui/workspace_v")
            if len(saved) == 2:
                self.workspace.setSizes(saved)
            else:
                total = max(600, width)
                self.workspace.setSizes([int(total * 0.64), int(total * 0.36)])
            self._applying_layout = False
            self._workspace_orientation = "h" if horizontal else "v"
        self._apply_rail_ratio()

    def _restore_layout(self) -> None:
        width = self.width()
        if width >= 1350:
            self.workspace.setOrientation(Qt.Orientation.Horizontal)
        else:
            self.workspace.setOrientation(Qt.Orientation.Vertical)
        self._workspace_orientation = "h" if self.workspace.orientation() == Qt.Orientation.Horizontal else "v"
        saved = self._saved_sizes("ui/workspace_h" if self._workspace_orientation == "h" else "ui/workspace_v")
        if len(saved) == 2:
            self.workspace.setSizes(saved)
        self._set_rail_collapsed(self._rail_collapsed, persist=False)
        self._apply_responsive()

    def _save_layout(self) -> None:
        sizes = self.splitter.sizes()
        if len(sizes) > 1 and sum(sizes) and not self._rail_collapsed:
            self._rail_ratio = max(0.18, min(0.42, sizes[0] / sum(sizes)))
            self._settings.setValue("ui/rail_ratio", self._rail_ratio)
        self._settings.setValue("ui/rail_collapsed", self._rail_collapsed)
        key = "ui/workspace_h" if self.workspace.orientation() == Qt.Orientation.Horizontal else "ui/workspace_v"
        self._settings.setValue(key, self.workspace.sizes())
        self._settings.setValue("research/tickers", " ".join(self.tickers.tickers()))
        self._settings.sync()

    def on_show(self) -> None:
        self._layout_timer.start()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "_layout_timer"):
            self._layout_timer.start()

    def shutdown(self) -> None:
        """Stop the stock engine and evict any local model it left resident."""
        self._stop_requested = True
        self._chart_timer.stop()
        self._save_layout()
        self.runner.shutdown()
        self.chart_grid.shutdown()
        for thread in (getattr(self, "_loader", None), getattr(self, "_ai_thread", None)):
            if thread is not None:
                thread.requestInterruption()
                thread.wait(1200)

        names = {name for name in self._local_models if name}
        entry = self.model.currentData() if hasattr(self, "model") else None
        if isinstance(entry, dict) and entry.get("local"):
            names.add(str(entry.get("name") or ""))
        saved = str(self._settings.value("research/model", "") or "")
        if saved and self._catalog is not None:
            selected = next((m for m in self._catalog.models if m.get("name") == saved), None)
            if selected and selected.get("provider") == "Ollama":
                names.add(saved)
        for name in sorted(name for name in names if name):
            config.unload_ollama_model(name)
