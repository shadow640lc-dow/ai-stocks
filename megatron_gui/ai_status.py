"""AI SYSTEM STATUS: runtimes, models, compatibility and inference tests."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.ai import compatibility, discovery, preflight, verification
from src.ai.runtime_registry import HttpResult  # noqa: F401  (patch point for tests)
from src.ai.types import ModelInfo, Snapshot

from . import theme
from .components import Pill, ghost_button, primary_button, section
from .engine import CallThread

STATUS_COLORS = {
    "READY": theme.GREEN,
    "READY WITH LIMITATIONS": theme.YELLOW,
    "NOT SUPPORTED": theme.RED,
    "UNAVAILABLE": theme.DIM,
}
RUNTIME_COLORS = {"READY": theme.GREEN, "STOPPED": theme.YELLOW, "UNREACHABLE": theme.RED, "NO MODELS": theme.YELLOW, "NOT INSTALLED": theme.RED, "CONFIGURED": theme.GREEN, "NO CREDENTIAL": theme.DIM}


def _capability_text(model: ModelInfo) -> str:
    declared = sorted(model.capabilities)
    text = ", ".join(declared) or "undeclared"
    if "json" in model.verified_capabilities and "json" not in model.capabilities:
        text += " + json (verified)"
    return text


def _chip(text: str, *, checkable: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("Chip")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setCheckable(checkable)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return button


class RuntimeCard(QWidget):
    def __init__(self, runtime, parent: QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QWidget {{ background: {theme.PANEL}; border: 1px solid {theme.LINE}; border-radius: 10px; }}"
            f"QLabel {{ border: none; background: transparent; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(8)
        name = QLabel(runtime.name)
        name.setFont(theme.font(12, QFont.Weight.DemiBold))
        top.addWidget(name)
        top.addStretch(1)
        state = runtime.status()
        top.addWidget(Pill(state, RUNTIME_COLORS.get(state, theme.DIM)))
        layout.addLayout(top)

        detail = QLabel(runtime.endpoint)
        detail.setObjectName("Hint")
        detail.setWordWrap(True)
        layout.addWidget(detail)

        bits = []
        if runtime.version:
            bits.append(f"v{runtime.version}")
        bits.append(f"{len(runtime.models)} model(s)")
        if runtime.hardware and runtime.hardware.gpu:
            bits.append(runtime.hardware.gpu)
        line = QLabel(" · ".join(bits))
        line.setFont(theme.font(9, mono=True))
        line.setStyleSheet(f"color: {theme.MUTED};")
        layout.addWidget(line)

        if runtime.error:
            error = QLabel(runtime.error)
            error.setWordWrap(True)
            error.setStyleSheet(f"color: {theme.RED}; font-size: 10px;")
            layout.addWidget(error)
        elif runtime.detail:
            note = QLabel(runtime.detail)
            note.setWordWrap(True)
            note.setObjectName("Hint")
            layout.addWidget(note)


class AiStatusDialog(QDialog):
    default_changed = Signal(str)
    local_only_changed = Signal(bool)
    auto_changed = Signal(bool)

    def __init__(
        self,
        snapshot: Snapshot | None,
        loader,
        *,
        task_id: str = "analyst_research",
        local_only: bool = False,
        auto: bool = False,
        selected_id: str | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._snapshot = snapshot
        self._loader = loader
        self._selected_id = selected_id
        self._task_id = task_id
        self._local_only = local_only
        self._auto = auto
        self._tests: dict[str, str] = {}

        self.setWindowTitle("AI system status")
        self.setModal(True)
        self.setMinimumSize(900, 720)
        self.setStyleSheet(f"QDialog {{ background: {theme.BG}; border: 1px solid {theme.LINE}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(section("AI SYSTEM STATUS", theme.ORANGE))
        head.addStretch(1)
        self.refresh_btn = _chip("REFRESH AI INVENTORY")
        self.refresh_btn.clicked.connect(lambda: self._load(refresh=True))
        head.addWidget(self.refresh_btn)
        root.addLayout(head)

        self.subtitle = QLabel("Loading runtime inventory…")
        self.subtitle.setObjectName("Hint")
        self.subtitle.setWordWrap(True)
        root.addWidget(self.subtitle)

        self.runtime_grid = QGridLayout()
        self.runtime_grid.setHorizontalSpacing(8)
        self.runtime_grid.setVerticalSpacing(8)
        root.addLayout(self.runtime_grid)

        options = QHBoxLayout()
        options.setSpacing(12)
        options.addWidget(section("TASK", theme.MUTED))
        self.task = QComboBox()
        for task in compatibility.TASKS.values():
            self.task.addItem(task.label, task.id)
        index = self.task.findData(task_id)
        self.task.setCurrentIndex(index if index >= 0 else 0)
        self.task.currentIndexChanged.connect(self._task_changed)
        options.addWidget(self.task, 1)
        self.local_only = QCheckBox("Local-only mode")
        self.local_only.setChecked(local_only)
        self.local_only.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.local_only.toggled.connect(self._local_toggled)
        options.addWidget(self.local_only)
        self.auto = QCheckBox("Automatic selection")
        self.auto.setChecked(auto)
        self.auto.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.auto.toggled.connect(self._auto_toggled)
        options.addWidget(self.auto)
        root.addLayout(options)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(7)
        self.tree.setHeaderLabels(["MODEL", "RUNTIME", "WHERE", "SIZE", "CONTEXT", "CAPABILITIES", "COMPATIBILITY"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(False)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.setStyleSheet(
            f"""
            QTreeWidget {{
                background: {theme.PANEL};
                alternate-background-color: {theme.PANEL};
                border: 1px solid {theme.LINE};
                border-radius: 10px;
                color: {theme.TEXT};
            }}
            QTreeWidget::item {{ padding: 5px 4px; }}
            QTreeWidget::item:selected {{ background: {theme.rgba(theme.ORANGE, 0.18)}; color: {theme.TEXT}; }}
            QHeaderView::section {{
                background: {theme.RAISED};
                color: {theme.MUTED};
                border: none;
                border-bottom: 1px solid {theme.LINE};
                padding: 6px;
                font-size: 9px;
            }}
            """
        )
        self.tree.header().setStretchLastSection(True)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        root.addWidget(self.tree, 1)

        self.detail = QLabel("Select a model to see why it is or is not compatible.")
        self.detail.setWordWrap(True)
        self.detail.setObjectName("Hint")
        root.addWidget(self.detail)

        self.last_test = QLabel("Last inference: none this session")
        self.last_test.setFont(theme.font(9, mono=True))
        self.last_test.setStyleSheet(f"color: {theme.DIM};")
        root.addWidget(self.last_test)

        diagnostics_row = QHBoxLayout()
        self.diag_btn = _chip("DIAGNOSTICS")
        self.diag_btn.setCheckable(True)
        diagnostics_row.addWidget(self.diag_btn)
        diagnostics_row.addStretch(1)
        root.addLayout(diagnostics_row)

        self.diagnostics = QLabel("")
        self.diagnostics.setWordWrap(True)
        self.diagnostics.setFont(theme.font(9, mono=True))
        self.diagnostics.setStyleSheet(f"color: {theme.MUTED}; background: {theme.PANEL}; border: 1px solid {theme.LINE}; border-radius: 8px; padding: 8px;")
        self.diagnostics.hide()
        self.diag_btn.toggled.connect(self.diagnostics.setVisible)
        root.addWidget(self.diagnostics)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.test_btn = ghost_button("TEST SELECTED MODEL", theme.BLUE)
        self.verify_btn = ghost_button("VERIFY JSON OUTPUT", theme.GREEN)
        self.default_btn = ghost_button("SET AS DEFAULT", theme.ORANGE)
        self.requirements_btn = ghost_button("VIEW REQUIREMENTS", theme.MUTED)
        close_btn = primary_button("CLOSE", theme.ORANGE, height=38)
        for button in (self.test_btn, self.verify_btn, self.default_btn, self.requirements_btn):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.test_btn.clicked.connect(self._test_selected)
        self.verify_btn.clicked.connect(self._verify_selected)
        self.default_btn.clicked.connect(self._set_default)
        self.requirements_btn.clicked.connect(self._show_requirements)
        close_btn.clicked.connect(self.accept)
        footer.addWidget(self.test_btn)
        footer.addWidget(self.verify_btn)
        footer.addWidget(self.default_btn)
        footer.addWidget(self.requirements_btn)
        footer.addStretch(1)
        footer.addWidget(close_btn)
        root.addLayout(footer)

        self._populate()
        if snapshot is None:
            self._load(refresh=True)

    # -- loading -------------------------------------------------------

    def _load(self, *, refresh: bool = False) -> None:
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("SCANNING…")
        self.subtitle.setText("Scanning local runtimes and configured cloud providers…")
        self._thread = CallThread(self._loader, parent=self)
        self._thread.ok.connect(self._loaded)
        self._thread.failed.connect(self._load_failed)
        self._thread.start()

    def _loaded(self, snapshot: object) -> None:
        if isinstance(snapshot, Snapshot):
            self._snapshot = snapshot
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("REFRESH AI INVENTORY")
        self._populate()

    def _load_failed(self, message: str) -> None:
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("REFRESH AI INVENTORY")
        self.subtitle.setText(f"Discovery failed: {message}")

    # -- rendering -----------------------------------------------------

    def _clear(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _populate(self) -> None:
        self._clear(self.runtime_grid)
        snapshot = self._snapshot
        if snapshot is None:
            return

        selected = snapshot.model(self._selected_id)[0] if self._selected_id else None
        subtitle = f"{discovery.summary_line(snapshot)} · {snapshot.hardware.summary()}"
        if selected is not None:
            subtitle += f" · selected: {selected.name}"
        self.subtitle.setText(subtitle)
        for index, runtime in enumerate(snapshot.runtimes):
            self.runtime_grid.addWidget(RuntimeCard(runtime, self), index // 3, index % 3)

        self.tree.clear()
        task = self.task.currentData()
        for runtime in snapshot.runtimes:
            for model in runtime.models:
                verdict = compatibility.evaluate(model, task)
                item = QTreeWidgetItem(
                    [
                        model.name,
                        runtime.name,
                        "LOCAL" if model.local else "CLOUD",
                        model.size_text(),
                        model.context_text(),
                        _capability_text(model),
                        verdict.status,
                    ]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, model.id)
                item.setForeground(6, QColor(STATUS_COLORS.get(verdict.status, theme.DIM)))
                item.setForeground(0, QColor(theme.TEXT if model.configured else theme.DIM))
                if model.local and model.name in self._tests:
                    item.setToolTip(0, self._tests[model.name])
                self.tree.addTopLevelItem(item)

        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            if self._selected_id and item.data(0, Qt.ItemDataRole.UserRole) == self._selected_id:
                self.tree.setCurrentItem(item)
                break

        errors = list(snapshot.errors)
        self.diagnostics.setText(
            "\n".join(errors) if errors else "No runtime errors reported. Discovery used local endpoints only."
        )
        if self.tree.currentItem() is not None:
            self._selection_changed()
        else:
            self.detail.setText("Select a model to see compatibility reasons and requirements.")

    def _selection_changed(self) -> None:
        model = self._selected_model()
        if model is None:
            return
        verdict = compatibility.evaluate(model, self.task.currentData())
        bits = [f"{verdict.status} for {self.task.currentText()}"]
        if verdict.reasons:
            bits.append(" · ".join(verdict.reasons))
        if verdict.notes:
            bits.append(" · ".join(verdict.notes))
        record = model.verification if isinstance(model.verification, dict) else None
        if record:
            failed = [task for task in record.get("tasks", []) if isinstance(task, dict) and not task.get("ok")]
            if failed:
                bits.append("; ".join(f"{task.get('task_id')}: {task.get('detail')}" for task in failed[:3]))
        if model.capabilities_source == "unknown":
            bits.append("Runtime did not declare capabilities; nothing was assumed.")
        if model.local and model.name in self._tests:
            bits.append(self._tests[model.name])
        self.detail.setText(" — ".join(bits))
        status_color = STATUS_COLORS.get(verdict.status, theme.MUTED)
        self.detail.setStyleSheet(f"color: {status_color};" if not verdict.reasons else f"color: {theme.MUTED};")

    def _selected_model(self) -> ModelInfo | None:
        item = self.tree.currentItem()
        if item is None or self._snapshot is None:
            return None
        model, _runtime = self._snapshot.model(item.data(0, Qt.ItemDataRole.UserRole))
        return model

    # -- controls ------------------------------------------------------

    def _task_changed(self) -> None:
        self._populate()

    def _local_toggled(self, on: bool) -> None:
        self._local_only = on
        self.local_only_changed.emit(on)

    def _auto_toggled(self, on: bool) -> None:
        self._auto = on
        self.auto_changed.emit(on)

    def _test_selected(self) -> None:
        model = self._selected_model()
        if model is None or self._snapshot is None:
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText("TESTING…")
        self._test_thread = CallThread(discovery.test_inference, self._snapshot, model.id, parent=self)
        self._test_thread.ok.connect(lambda result: self._tested(model, result))
        self._test_thread.failed.connect(self._test_failed)
        self._test_thread.start()

    def _tested(self, model: ModelInfo, result) -> None:
        self.test_btn.setEnabled(True)
        self.test_btn.setText("TEST SELECTED MODEL")
        self._tests[model.name] = result.detail
        self.last_test.setText(f"Last inference: {model.name} · {result.detail}")
        self.last_test.setStyleSheet(f"color: {theme.GREEN if result.ok else theme.RED};")
        self._selection_changed()

    def _test_failed(self, message: str) -> None:
        self.test_btn.setEnabled(True)
        self.test_btn.setText("TEST SELECTED MODEL")
        self.last_test.setText(f"Last inference failed: {message}")
        self.last_test.setStyleSheet(f"color: {theme.RED};")

    def _verify_selected(self) -> None:
        model = self._selected_model()
        if model is None or self._snapshot is None:
            return
        runtime = self._snapshot.runtime(model.runtime_id)
        if runtime is None:
            return
        if runtime.kind != "local" or runtime.id != "ollama":
            QMessageBox.information(
                self,
                "Verification unavailable",
                "Schema-constrained verification currently supports Ollama only. "
                "No request was sent for this model.",
            )
            return
        self.verify_btn.setEnabled(False)
        self.verify_btn.setText("VERIFYING 8 PROFILES…")
        self.last_test.setText(f"Verifying structured output on {model.name}…")
        self.last_test.setStyleSheet(f"color: {theme.MUTED};")
        self._verify_thread = CallThread(verification.verify_model, model, runtime, parent=self)
        self._verify_thread.ok.connect(lambda report: self._verified(model, report))
        self._verify_thread.failed.connect(self._verify_failed)
        self._verify_thread.start()

    def _verified(self, model: ModelInfo, report) -> None:
        self.verify_btn.setEnabled(True)
        self.verify_btn.setText("VERIFY JSON OUTPUT")
        verification.save_report(report, model)
        record = verification.load_record(model)
        if record is not None:
            verification.apply_record(model, record)
        self._selected_id = model.id
        passed = sum(1 for check in report.tasks if check.ok)
        self.last_test.setText(f"Structured output: {passed}/{len(report.tasks)} profiles passed · {model.name}")
        self.last_test.setStyleSheet(f"color: {theme.GREEN if report.passed else theme.RED};")
        self._populate()
        self._selection_changed()

    def _verify_failed(self, message: str) -> None:
        self.verify_btn.setEnabled(True)
        self.verify_btn.setText("VERIFY JSON OUTPUT")
        self.last_test.setText(f"Structured-output verification failed: {message}")
        self.last_test.setStyleSheet(f"color: {theme.RED};")

    def _set_default(self) -> None:
        model = self._selected_model()
        if model is None:
            return
        verdict = compatibility.evaluate(model, self.task.currentData())
        if verdict.status in {"NOT SUPPORTED", "UNAVAILABLE"}:
            QMessageBox.warning(self, "Not usable", "\n".join([verdict.status] + verdict.reasons))
            return
        self.default_changed.emit(model.id)
        self.last_test.setText(f"Default model set to {model.name}")
        self.last_test.setStyleSheet(f"color: {theme.ORANGE};")

    def _show_requirements(self) -> None:
        task = compatibility.task(self.task.currentData())
        lines = [
            f"{task.label}",
            "",
            f"Requires: {', '.join(sorted(task.needs))}",
            f"Prefers: {', '.join(sorted(task.prefers))}",
            f"Minimum context: {task.min_context:,} tokens",
        ]
        if task.note:
            lines += ["", task.note]
        lines += [
            "",
            "MEGATRON asks every analyst for structured JSON. Models that do not",
            "declare JSON support are shown as READY WITH LIMITATIONS rather than",
            "being silently treated as equivalent.",
        ]
        QMessageBox.information(self, "Model requirements", "\n".join(lines))

    def selected_model_id(self) -> str | None:
        model = self._selected_model()
        return model.id if model else None

    def snapshot(self) -> Snapshot | None:
        return self._snapshot


def open_dialog(parent: QWidget, snapshot, loader, **kwargs) -> AiStatusDialog:
    dialog = AiStatusDialog(snapshot, loader, parent=parent, **kwargs)
    dialog.exec()
    return dialog
