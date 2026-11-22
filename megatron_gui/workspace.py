"""Multi-ticker chart and research workspaces.

Each visible ticker owns its own :class:`MarketChart` and
:class:`ResearchStream`, so changing a timeframe or receiving a report for one
symbol can never mutate another symbol's state.
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .catalog import Analyst
from .chart import MarketChart
from .components import Card, section
from .research import ResearchStream

CHART_MIN_HEIGHT = 300


class ChartGrid(Card):
    """Responsive 1 / 2 / 2x2 / scrollable grid of independent charts."""

    def __init__(self, accent: str = theme.ORANGE, parent: QWidget | None = None):
        super().__init__(pad=12, spacing=8, parent=parent)
        self._accent = accent
        self._tickers: list[str] = []
        self._charts: dict[str, MarketChart] = {}

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(section("MULTI-CHART WORKSPACE", accent))
        head.addStretch(1)
        self.count = QLabel("NO CHARTS")
        self.count.setFont(theme.font(8, QFont.Weight.DemiBold, mono=True, spacing=0.9))
        self.count.setStyleSheet(f"color: {theme.MUTED};")
        head.addWidget(self.count)
        self.layout_note = QLabel("ADD TICKERS")
        self.layout_note.setFont(theme.font(8, QFont.Weight.DemiBold, mono=True, spacing=0.9))
        self.layout_note.setStyleSheet(f"color: {theme.DIM};")
        head.addWidget(self.layout_note)
        self.body.addLayout(head)

        self._stack = QStackedWidget()
        self._empty_page = QWidget()
        empty_layout = QVBoxLayout(self._empty_page)
        empty_layout.setContentsMargins(20, 30, 20, 30)
        empty = QLabel("ENTER ONE OR MORE TICKERS\nCHARTS FOLLOW THE RESEARCH QUEUE")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setWordWrap(True)
        empty.setFont(theme.font(10, QFont.Weight.DemiBold, mono=True, spacing=1.1))
        empty.setStyleSheet(f"color: {theme.DIM};")
        empty_layout.addWidget(empty)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._scroll.viewport().setAutoFillBackground(False)
        self._canvas = QWidget()
        self._canvas.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._canvas)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(9)
        self._grid.setVerticalSpacing(9)
        self._scroll.setWidget(self._canvas)

        self._stack.addWidget(self._empty_page)
        self._stack.addWidget(self._scroll)
        self.body.addWidget(self._stack, 1)
        self._stack.setCurrentWidget(self._empty_page)

    # -- tickers -------------------------------------------------------

    def _ensure_chart(self, ticker: str) -> MarketChart:
        symbol = str(ticker or "").strip().upper()
        if not symbol:
            raise ValueError("ticker is required")
        chart = self._charts.get(symbol)
        if chart is None:
            chart = MarketChart(self._accent)
            chart.setMinimumHeight(CHART_MIN_HEIGHT)
            self._charts[symbol] = chart
            chart.load_ticker(symbol, analyzing=False)
        return chart

    def set_tickers(self, tickers: list[str]) -> None:
        normalized: list[str] = []
        for ticker in tickers:
            symbol = str(ticker or "").strip().upper()
            if symbol and symbol not in normalized:
                normalized.append(symbol)
        for symbol in normalized:
            self._ensure_chart(symbol)
        if normalized == self._tickers:
            return
        self._tickers = normalized
        self._rebuild()

    def load_ticker(self, ticker: str) -> MarketChart:
        chart = self._ensure_chart(ticker)
        chart.mark_analyzing()
        chart.refresh()
        return chart

    def focus_ticker(self, ticker: str) -> None:
        symbol = str(ticker or "").strip().upper()
        chart = self._ensure_chart(symbol)
        if symbol not in self._tickers:
            self._tickers.append(symbol)
            self._rebuild()
        QTimer.singleShot(0, lambda: self._scroll.ensureWidgetVisible(chart, 16, 16))

    def chart_for(self, ticker: str) -> MarketChart | None:
        return self._charts.get(str(ticker or "").strip().upper())

    @property
    def tickers(self) -> list[str]:
        return list(self._tickers)

    @property
    def charts(self) -> dict[str, MarketChart]:
        return dict(self._charts)

    # -- grid ----------------------------------------------------------

    def _rebuild(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()

        total = len(self._tickers)
        if total == 0:
            self.count.setText("NO CHARTS")
            self.layout_note.setText("ADD TICKERS")
            self._stack.setCurrentWidget(self._empty_page)
            self._canvas.setMinimumHeight(0)
            return

        columns = 1 if total == 1 else 2
        rows = math.ceil(total / columns)
        for index, symbol in enumerate(self._tickers):
            chart = self._charts[symbol]
            chart.show()
            self._grid.addWidget(chart, index // columns, index % columns)

        for column in range(2):
            self._grid.setColumnStretch(column, 1 if column < columns else 0)
        for row in range(max(rows, 1)):
            self._grid.setRowStretch(row, 1)
        for row in range(rows, rows + 4):
            self._grid.setRowStretch(row, 0)

        self.count.setText(f"{total} CHART" + ("" if total == 1 else "S"))
        if total == 1:
            note = "1 · LARGE"
        elif total == 2:
            note = "2 · SIDE BY SIDE"
        elif total <= 4:
            note = f"{total} · 2×2 GRID"
        else:
            note = f"{total} · SCROLL · 2 COL"
        self.layout_note.setText(note)

        # Give the grid a real vertical extent so the chart scroll area owns
        # its scrolling instead of stretching the whole page.
        spacing_total = max(0, rows - 1) * self._grid.verticalSpacing()
        self._canvas.setMinimumHeight(rows * CHART_MIN_HEIGHT + spacing_total)
        self._stack.setCurrentWidget(self._scroll)

    def set_alert(self, ticker: str, action: str, confidence: str, rationale: object) -> None:
        chart = self.chart_for(ticker)
        if chart is not None:
            chart.set_alert(ticker, action, confidence, list(rationale or []))

    def finish_run(self, ticker: str, code: int, stopped: bool) -> None:
        chart = self.chart_for(ticker)
        if chart is not None:
            chart.finish_run(code, stopped)

    def shutdown(self) -> None:
        for chart in self._charts.values():
            chart.shutdown()


class ResearchWorkspace(Card):
    """Ticker-isolated research output tabs."""

    submitted = Signal(str)
    decision_ready = Signal(str, str, str, object)
    ticker_selected = Signal(str)

    def __init__(self, accent: str = theme.ORANGE, parent: QWidget | None = None):
        super().__init__(pad=10, spacing=8, parent=parent)
        self._accent = accent
        self._roster: dict[str, Analyst] = {}
        self._streams: dict[str, ResearchStream] = {}
        self._restoring_tab = False

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(section("RESEARCH OUTPUT", accent))
        head.addStretch(1)
        self.count = QLabel("NO RUNS")
        self.count.setFont(theme.font(8, QFont.Weight.DemiBold, mono=True, spacing=0.9))
        self.count.setStyleSheet(f"color: {theme.MUTED};")
        head.addWidget(self.count)
        isolated = QLabel("TICKER-ISOLATED")
        isolated.setFont(theme.font(8, QFont.Weight.DemiBold, mono=True, spacing=0.9))
        isolated.setStyleSheet(f"color: {theme.DIM};")
        head.addWidget(isolated)
        self.body.addLayout(head)

        self._pages = QStackedWidget()
        self._empty_page = QWidget()
        empty_layout = QVBoxLayout(self._empty_page)
        empty_layout.setContentsMargins(20, 26, 20, 26)
        empty = QLabel("NO RESEARCH YET\nRUN ANALYSIS TO CREATE PER-TICKER REPORT TABS")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setWordWrap(True)
        empty.setFont(theme.font(10, QFont.Weight.DemiBold, mono=True, spacing=1.1))
        empty.setStyleSheet(f"color: {theme.DIM};")
        empty_layout.addWidget(empty)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("ResearchTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(False)
        self.tabs.setMovable(False)
        self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setUsesScrollButtons(True)
        self.tabs.currentChanged.connect(self._tab_changed)

        self._pages.addWidget(self._empty_page)
        self._pages.addWidget(self.tabs)
        self.body.addWidget(self._pages, 1)
        self._pages.setCurrentWidget(self._empty_page)

    # -- roster --------------------------------------------------------

    def set_roster(self, roster: dict[str, Analyst]) -> None:
        self._roster = dict(roster)
        for stream in self._streams.values():
            stream.set_roster(self._roster)

    # -- tabs ----------------------------------------------------------

    def stream_for(self, ticker: str) -> ResearchStream:
        symbol = str(ticker or "").strip().upper()
        if not symbol:
            raise ValueError("ticker is required")
        stream = self._streams.get(symbol)
        if stream is None:
            stream = ResearchStream(f"RESEARCH · {symbol}", self._accent)
            stream.set_roster(self._roster)
            stream.decision_ready.connect(self.decision_ready.emit)
            stream.submitted.connect(self.submitted.emit)
            self._streams[symbol] = stream
            self.tabs.addTab(stream, symbol)
            self.tabs.setTabToolTip(self.tabs.count() - 1, f"Isolated research report for {symbol}")
            self._pages.setCurrentWidget(self.tabs)
            self._update_count()
        return stream

    def has_ticker(self, ticker: str) -> bool:
        return str(ticker or "").strip().upper() in self._streams

    def focus_ticker(self, ticker: str) -> None:
        symbol = str(ticker or "").strip().upper()
        self._select_tab(symbol)
        stream = self._streams.get(symbol)
        if stream is not None:
            self.tabs.setCurrentWidget(stream)

    def active_ticker(self) -> str:
        index = self.tabs.currentIndex()
        return self.tabs.tabText(index) if index >= 0 else ""

    def _select_tab(self, symbol: str) -> None:
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == symbol:
                if self.tabs.currentIndex() != index:
                    self._restoring_tab = True
                    self.tabs.setCurrentIndex(index)
                    self._restoring_tab = False
                return

    def _tab_changed(self, _index: int) -> None:
        if self._restoring_tab:
            return
        ticker = self.active_ticker()
        if ticker:
            self.ticker_selected.emit(ticker)

    def _update_count(self) -> None:
        total = len(self._streams)
        self.count.setText("NO RUNS" if total == 0 else f"{total} TICKER" + ("" if total == 1 else "S"))

    # -- lifecycle -----------------------------------------------------

    def reset(self, tickers: list[str]) -> None:
        for ticker in tickers:
            symbol = str(ticker or "").strip().upper()
            stream = self._streams.get(symbol)
            if stream is not None:
                stream.clear()

    def begin_run(self, ticker: str, mode: str, names: list[str], index: int, total: int) -> None:
        symbol = str(ticker or "").strip().upper()
        stream = self.stream_for(symbol)
        self.focus_ticker(symbol)
        stream.begin_run(symbol, mode, names, index, total)

    def show_command(self, ticker: str, command: str) -> None:
        stream = self._streams.get(str(ticker or "").strip().upper())
        if stream is not None:
            stream.show_command(command)

    def progress_event(self, ticker: str, payload: dict) -> None:
        stream = self._streams.get(str(ticker or "").strip().upper())
        if stream is not None:
            stream.progress_event(payload)

    def feed(self, ticker: str, line: str) -> None:
        stream = self._streams.get(str(ticker or "").strip().upper())
        if stream is not None:
            stream.feed(line)

    def write(self, ticker: str, text: str, kind: str | None = None) -> None:
        stream = self._streams.get(str(ticker or "").strip().upper())
        if stream is not None:
            stream.write(text, kind)

    def set_status(self, ticker: str, text: str, color: str) -> None:
        stream = self._streams.get(str(ticker or "").strip().upper())
        if stream is not None:
            stream.set_status(text, color)

    def end_run(self, ticker: str, code: int, *, stopped: bool = False) -> None:
        stream = self._streams.get(str(ticker or "").strip().upper())
        if stream is not None:
            stream.end_run(code, stopped=stopped)


class TickerTabs(QTabBar):
    """Compact ticker quick-select strip in the control rail."""

    ticker_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("TickerTabs")
        self.setDrawBase(False)
        self.setExpanding(False)
        self.setElideMode(Qt.TextElideMode.ElideRight)
        self.setUsesScrollButtons(True)
        self.setVisible(False)
        self.currentChanged.connect(self._changed)

    def set_tickers(self, tickers: list[str]) -> None:
        symbols: list[str] = []
        for ticker in tickers:
            symbol = str(ticker or "").strip().upper()
            if symbol and symbol not in symbols:
                symbols.append(symbol)
        existing = [self.tabText(index) for index in range(self.count())]
        if symbols == existing:
            self.setVisible(bool(symbols))
            return
        current = self.tabText(self.currentIndex()) if self.currentIndex() >= 0 else ""
        self.blockSignals(True)
        while self.count():
            self.removeTab(0)
        for symbol in symbols:
            self.addTab(symbol)
        if current in symbols:
            self.setCurrentIndex(symbols.index(current))
        elif symbols:
            self.setCurrentIndex(0)
        self.blockSignals(False)
        self.setVisible(bool(symbols))

    def select(self, ticker: str) -> None:
        symbol = str(ticker or "").strip().upper()
        for index in range(self.count()):
            if self.tabText(index) == symbol:
                self.blockSignals(True)
                self.setCurrentIndex(index)
                self.blockSignals(False)
                return

    def _changed(self, index: int) -> None:
        if index >= 0:
            self.ticker_selected.emit(self.tabText(index))
