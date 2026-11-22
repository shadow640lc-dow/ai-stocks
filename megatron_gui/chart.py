"""Market candlesticks and the MEGASTOCKS buy / no-buy alert.

The chart is painted directly with Qt so the GUI keeps its single dependency
(PySide6). Yahoo's public chart endpoint supplies real OHLCV bars; no order or
account credential is involved.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .components import Card, Pill, section
from .engine import CallThread

RANGES = {
    "1M": ("1mo", "1d", "1 month"),
    "3M": ("3mo", "1d", "3 months"),
    "6M": ("6mo", "1d", "6 months"),
    "1Y": ("1y", "1wk", "1 year"),
}


def _daily_change(ticker: str) -> float | None:
    """Latest daily move, independent of the chart's display interval."""
    symbol = urllib.parse.quote(ticker.strip().upper(), safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        "?range=5d&interval=1d&includePrePost=false"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 MEGATRON"})
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.load(response)
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        return None
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = []
    for value in quote.get("close") or []:
        try:
            closes.append(float(value))
        except (TypeError, ValueError):
            continue
    if len(closes) < 2 or closes[-2] == 0:
        return None
    return (closes[-1] / closes[-2] - 1.0) * 100.0


def fetch_candles(ticker: str, range_key: str = "6M") -> dict:
    """Fetch daily/weekly OHLCV bars from Yahoo's public chart endpoint."""
    range_value, interval, _label = RANGES.get(range_key, RANGES["6M"])
    symbol = urllib.parse.quote(ticker.strip().upper(), safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?range={range_value}&interval={interval}&includePrePost=false"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 MEGATRON"})
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.load(response)

    chart = payload.get("chart") or {}
    results = chart.get("result") or []
    if not results:
        error = (chart.get("error") or {}).get("description") or "Yahoo returned no chart data"
        raise RuntimeError(error)
    result = results[0]
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    candles: list[dict] = []
    for index, stamp in enumerate(timestamps):
        try:
            open_value = float(opens[index])
            high_value = float(highs[index])
            low_value = float(lows[index])
            close_value = float(closes[index])
        except (IndexError, TypeError, ValueError):
            continue
        if not all(value == value for value in (open_value, high_value, low_value, close_value)):
            continue
        try:
            volume_value = int(volumes[index] or 0)
        except (IndexError, TypeError, ValueError):
            volume_value = 0
        moment = datetime.fromtimestamp(int(stamp), tz=timezone.utc)
        candles.append(
            {
                "time": moment.isoformat(),
                "label": moment.strftime("%d %b"),
                "open": open_value,
                "high": high_value,
                "low": low_value,
                "close": close_value,
                "volume": volume_value,
            }
        )
    if not candles:
        raise RuntimeError("Yahoo returned no usable candles for this ticker")

    meta = result.get("meta") or {}
    last = candles[-1]
    # Use the previous daily candle, not meta.chartPreviousClose: on a 6M/1Y
    # chart Yahoo reports the price at the *start of the range* there. Weekly
    # bars need a separate daily quote so the percentage is a daily move.
    previous = candles[-2]["close"] if len(candles) > 1 and interval == "1d" else None
    change = ((last["close"] / previous) - 1.0) * 100.0 if previous else None
    if interval != "1d":
        try:
            change = _daily_change(ticker)
        except Exception:
            change = None
    return {
        "ticker": ticker.upper(),
        "range": range_key,
        "candles": candles,
        "price": last["close"],
        "previous_close": previous,
        "change": change,
        "currency": meta.get("currency") or "USD",
    }


class CandleChart(QWidget):
    """Responsive OHLC candlesticks with volume and a moving average."""

    hovered = Signal(object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._candles: list[dict] = []
        self._loading = False
        self._error = ""
        self._placeholder = "ENTER A TICKER\nRUN ANALYSIS TO LOAD CANDLES"
        self._hover: int | None = None
        self._geom: dict | None = None
        self.setMinimumHeight(155)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_payload(self, payload: dict) -> None:
        self._candles = list(payload.get("candles") or [])
        self._loading = False
        self._error = ""
        self._hover = None
        self.update()

    def set_loading(self) -> None:
        self._candles = []
        self._loading = True
        self._error = ""
        self._hover = None
        self.update()

    def set_empty(self, message: str) -> None:
        self._candles = []
        self._loading = False
        self._error = ""
        self._placeholder = str(message)
        self._hover = None
        self.update()

    def set_error(self, message: str) -> None:
        self._candles = []
        self._loading = False
        self._error = str(message).strip() or "Chart unavailable"
        self._hover = None
        self.update()

    def _geometry(self) -> dict:
        width = max(1, self.width())
        height = max(1, self.height())
        left = 8.0
        right = max(left + 30.0, width - 62.0)
        top = 8.0
        bottom = max(top + 50.0, height - 20.0)
        volume_height = max(22.0, min(42.0, height * 0.16))
        price_bottom = bottom - volume_height - 8.0
        return {
            "left": left,
            "right": right,
            "top": top,
            "bottom": bottom,
            "price_bottom": price_bottom,
            "volume_top": price_bottom + 8.0,
            "volume_bottom": bottom,
        }

    def _map_price(self, value: float, low: float, high: float, top: float, bottom: float) -> float:
        span = max(high - low, 0.0001)
        return bottom - ((value - low) / span) * (bottom - top)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self._candles or not self._geom:
            return
        left = self._geom["left"]
        right = self._geom["right"]
        width = max(right - left, 1.0)
        index = int((event.position().x() - left) / width * len(self._candles))
        index = max(0, min(len(self._candles) - 1, index))
        if index != self._hover:
            self._hover = index
            self.hovered.emit(self._candles[index])
            self.update()

    def leaveEvent(self, _event) -> None:  # noqa: N802
        if self._hover is not None:
            self._hover = None
            self.hovered.emit(None)
            self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(theme.font(9, mono=True))

        if not self._candles:
            if self._loading:
                message = "FETCHING YAHOO CANDLES…"
                color = theme.DIM
            elif self._error:
                message = f"CHART UNAVAILABLE\n{self._error}"
                color = theme.RED
            else:
                message = self._placeholder
                color = theme.DIM
            painter.setPen(QColor(color))
            painter.drawText(self.rect().adjusted(12, 12, -12, -12), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, message)
            return

        geom = self._geometry()
        self._geom = geom
        left, right = geom["left"], geom["right"]
        top, price_bottom = geom["top"], geom["price_bottom"]
        volume_top, volume_bottom = geom["volume_top"], geom["volume_bottom"]
        candles = self._candles
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        high = max(highs)
        low = min(lows)
        padding = max((high - low) * 0.055, high * 0.002)
        high += padding
        low -= padding

        # Grid and price labels.
        line_pen = QPen(QColor(theme.rgba(theme.LINE, 0.85)), 1, Qt.PenStyle.DashLine)
        label_pen = QPen(QColor(theme.DIM), 1)
        for level in range(5):
            ratio = level / 4
            y = price_bottom - ratio * (price_bottom - top)
            painter.setPen(line_pen)
            painter.drawLine(QPointF(left, y), QPointF(right, y))
            value = low + ratio * (high - low)
            painter.setPen(label_pen)
            painter.drawText(
                QRectF(right + 5, y - 8, 55, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{value:,.2f}",
            )

        # Volume panel.
        volume_max = max((c["volume"] for c in candles), default=0) or 1
        volume_color = theme.rgba(theme.GREEN, 0.30)
        for index, candle in enumerate(candles):
            slot = (right - left) / len(candles)
            x = left + slot * (index + 0.5)
            bar_height = (candle["volume"] / volume_max) * max(1.0, volume_bottom - volume_top)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme.GREEN if candle["close"] >= candle["open"] else theme.RED))
            painter.setOpacity(0.32)
            painter.drawRect(QRectF(x - max(1.0, slot * 0.28), volume_bottom - bar_height, max(1.0, slot * 0.56), bar_height))
        painter.setOpacity(1.0)
        painter.setPen(QPen(QColor(theme.LINE), 1))
        painter.drawLine(QPointF(left, volume_bottom), QPointF(right, volume_bottom))

        # Candles.
        slot = (right - left) / len(candles)
        body_width = min(8.0, max(1.8, slot * 0.62))
        for index, candle in enumerate(candles):
            x = left + slot * (index + 0.5)
            color = QColor(theme.GREEN if candle["close"] >= candle["open"] else theme.RED)
            y_high = self._map_price(candle["high"], low, high, top, price_bottom)
            y_low = self._map_price(candle["low"], low, high, top, price_bottom)
            y_open = self._map_price(candle["open"], low, high, top, price_bottom)
            y_close = self._map_price(candle["close"], low, high, top, price_bottom)
            painter.setPen(QPen(color, 1))
            painter.drawLine(QPointF(x, y_high), QPointF(x, y_low))
            body_top = min(y_open, y_close)
            body_height = max(1.2, abs(y_close - y_open))
            painter.fillRect(QRectF(x - body_width / 2, body_top, body_width, body_height), color)

        # Moving average.
        closes = [c["close"] for c in candles]
        period = 20 if len(candles) >= 40 else 10
        if len(closes) >= period:
            points: list[QPointF] = []
            for index in range(period - 1, len(closes)):
                average = sum(closes[index - period + 1 : index + 1]) / period
                x = left + slot * (index + 0.5)
                points.append(QPointF(x, self._map_price(average, low, high, top, price_bottom)))
            painter.setPen(QPen(QColor(theme.ORANGE), 1.4))
            painter.drawPolyline(QPolygonF(points))
            painter.setPen(QColor(theme.rgba(theme.ORANGE, 0.82)))
            painter.drawText(QRectF(left + 2, top + 1, 80, 12), Qt.AlignmentFlag.AlignLeft, f"MA{period}")

        # Date labels.
        painter.setPen(QColor(theme.MUTED))
        metrics = QFontMetrics(painter.font())
        for index in sorted({0, len(candles) // 3, 2 * len(candles) // 3, len(candles) - 1}):
            x = left + slot * (index + 0.5)
            text = metrics.elidedText(candles[index]["label"], Qt.TextElideMode.ElideRight, int(max(44, slot * 3)))
            painter.drawText(
                QRectF(x - 30, volume_bottom + 2, 60, 14),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                text,
            )

        # Hover crosshair.
        if self._hover is not None:
            candle = candles[self._hover]
            x = left + slot * (self._hover + 0.5)
            y = self._map_price(candle["close"], low, high, top, price_bottom)
            painter.setPen(QPen(QColor(theme.rgba(theme.TEXT, 0.45)), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(x, top), QPointF(x, volume_bottom))
            painter.drawLine(QPointF(left, y), QPointF(right, y))
            box = QRectF(left + 2, top + 2, max(80.0, right - left - 4), 18)
            painter.fillRect(box, QColor(theme.BG))
            painter.setPen(QColor(theme.TEXT))
            painter.drawText(
                box.adjusted(4, 0, -4, 0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{candle['label']}   O {candle['open']:,.2f}   H {candle['high']:,.2f}   L {candle['low']:,.2f}   C {candle['close']:,.2f}",
            )


class SignalAlert(QFrame):
    """A clear BUY / DO NOT BUY research alert tied to one fund decision."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SignalAlert")
        self._tone = theme.DIM

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 9, 12, 9)
        root.setSpacing(5)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.eyebrow = section("SIGNAL ALERT", theme.DIM)
        self.eyebrow.setMinimumWidth(0)
        self.symbol = QLabel("—")
        self.symbol.setFont(theme.font(11, QFont.Weight.Bold, mono=True, spacing=1.1))
        self.symbol.setMinimumWidth(0)
        self.confidence = QLabel("")
        self.confidence.setFont(theme.font(9, mono=True))
        self.confidence.setMinimumWidth(0)
        self.confidence.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.action = Pill("WAITING", theme.DIM)
        top.addWidget(self.eyebrow)
        top.addWidget(self.symbol)
        top.addStretch(1)
        top.addWidget(self.confidence)
        top.addWidget(self.action)
        root.addLayout(top)

        self.headline = QLabel("AWAITING FUND DECISION")
        self.headline.setFont(theme.font(15, QFont.Weight.Bold, mono=True, spacing=1.0))
        self.headline.setWordWrap(True)
        self.headline.setMinimumWidth(0)
        self.headline.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        root.addWidget(self.headline)

        self.reason = QLabel("Run MEGASTOCKS to produce a research signal.")
        self.reason.setWordWrap(True)
        self.reason.setFont(theme.font(9))
        self.reason.setMinimumWidth(0)
        self.reason.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        root.addWidget(self.reason)

        self.footnote = QLabel("RESEARCH SIGNAL · NOT AN ORDER")
        self.footnote.setFont(theme.font(8, QFont.Weight.DemiBold, mono=True, spacing=1.1))
        root.addWidget(self.footnote)
        self.clear()

    def _style(self, tone: str) -> None:
        self._tone = tone
        self.setStyleSheet(
            f"""
            QFrame#SignalAlert {{
                background: {theme.rgba(tone, 0.08)};
                border: 1px solid {theme.rgba(tone, 0.38)};
                border-left: 3px solid {tone};
                border-radius: 9px;
            }}
            QLabel {{ background: transparent; border: none; }}
            """
        )
        self.eyebrow.setStyleSheet(f"color: {tone};")
        self.headline.setStyleSheet(f"color: {tone};")
        self.symbol.setStyleSheet(f"color: {theme.TEXT};")
        self.confidence.setStyleSheet(f"color: {theme.MUTED};")
        self.reason.setStyleSheet(f"color: {theme.rgba(theme.TEXT, 0.86)};")
        self.footnote.setStyleSheet(f"color: {theme.rgba(tone, 0.76)};")
        self.footnote.setMinimumWidth(0)
        self.footnote.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def clear(self) -> None:
        self._style(theme.DIM)
        self.eyebrow.setText("SIGNAL ALERT")
        self.symbol.setText("—")
        self.confidence.setText("")
        self.action.set_state("WAITING", theme.DIM)
        self.headline.setText("AWAITING FUND DECISION")
        self.reason.setText("Run MEGASTOCKS to produce a research signal.")
        self.footnote.setText("RESEARCH SIGNAL · NOT AN ORDER")

    def set_loading(self, ticker: str) -> None:
        self._style(theme.BLUE)
        self.symbol.setText(ticker or "—")
        self.confidence.setText("")
        self.action.set_state("ANALYZING", theme.BLUE)
        self.headline.setText("ANALYSIS IN PROGRESS")
        self.reason.setText("Waiting for the portfolio manager's final decision.")
        self.footnote.setText("RESEARCH RUNNING · NO ORDER SENT")

    def set_no_decision(self, ticker: str, message: str = "No fund decision was returned.") -> None:
        self._style(theme.YELLOW)
        self.symbol.setText(ticker or "—")
        self.confidence.setText("")
        self.action.set_state("NO DECISION", theme.YELLOW)
        self.headline.setText("NO BUY SIGNAL")
        self.reason.setText(message)
        self.footnote.setText("RESEARCH SIGNAL · NOT AN ORDER")

    def set_preview(self, ticker: str) -> None:
        self._style(theme.DIM)
        self.symbol.setText(ticker or "—")
        self.confidence.setText("")
        self.action.set_state("PREVIEW", theme.DIM)
        self.headline.setText("AWAITING ANALYSIS")
        self.reason.setText("Chart preview only. Run MEGASTOCKS for a fund decision.")
        self.footnote.setText("RESEARCH SIGNAL · NOT AN ORDER")

    def set_decision(self, ticker: str, action: str, confidence: str, rationale: list[str]) -> None:
        raw_action = str(action or "").strip().upper()
        base = re.split(r"[\s:/]+", raw_action)[0] if raw_action else ""
        if base in {"BUY", "COVER"}:
            tone = theme.GREEN
            headline = "BUY ALERT"
            note = "The fund decision is BUY."
        elif base in {"SELL", "SHORT"}:
            tone = theme.RED
            headline = "DO NOT BUY"
            note = "The fund decision is SELL."
        elif base in {"HOLD", "WAIT"}:
            tone = theme.YELLOW
            headline = "NO BUY — HOLD"
            note = "The fund decision is HOLD."
        else:
            tone = theme.DIM
            headline = "NO BUY SIGNAL"
            note = "The fund decision is unavailable."

        match = re.search(r"([\d.]+%)", str(confidence or ""))
        confidence_text = match.group(1) if match else str(confidence or "").strip()
        text = " ".join(str(item).strip() for item in (rationale or []) if str(item).strip())
        text = re.sub(r"\s+", " ", text)[:300] or note
        self._style(tone)
        self.symbol.setText(ticker or "—")
        self.confidence.setText(f"CONF {confidence_text}" if confidence_text else "")
        self.action.set_state(base or "—", tone)
        self.headline.setText(headline)
        self.reason.setText(text)
        self.footnote.setText("RESEARCH SIGNAL · NOT AN ORDER")


class MarketChart(Card):
    """Candles, timeframe controls and the buy / no-buy decision banner."""

    def __init__(self, accent: str = theme.ORANGE, parent: QWidget | None = None):
        super().__init__(accent=accent, pad=14, spacing=9, parent=parent)
        self._ticker = ""
        self._range = "6M"
        self._request = 0
        self._threads: list[CallThread] = []
        self._awaiting = False
        self._has_alert = False

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(section("CANDLE CHART", accent))
        self.symbol = QLabel("—")
        self.symbol.setFont(theme.font(15, QFont.Weight.Bold, mono=True, spacing=1.0))
        self.symbol.setStyleSheet(f"color: {accent};")
        self.symbol.setMinimumWidth(0)
        top.addWidget(self.symbol)
        top.addStretch(1)
        self.price = QLabel("—")
        self.price.setFont(theme.font(16, QFont.Weight.Bold, mono=True))
        self.price.setMinimumWidth(0)
        top.addWidget(self.price)
        self.change = QLabel("")
        self.change.setFont(theme.font(9, QFont.Weight.DemiBold, mono=True))
        self.change.setMinimumWidth(0)
        top.addWidget(self.change)
        self.body.addLayout(top)

        ranges = QHBoxLayout()
        ranges.setSpacing(5)
        self._range_group = QButtonGroup(self)
        self._range_group.setExclusive(True)
        for key in RANGES:
            button = QPushButton(key)
            button.setObjectName("Chip")
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, value=key: self.set_range(value))
            self._range_group.addButton(button)
            ranges.addWidget(button)
            if key == self._range:
                button.setChecked(True)
        ranges.addStretch(1)
        self.source = QLabel("YAHOO FINANCE · WAITING FOR TICKER")
        self.source.setFont(theme.font(8, QFont.Weight.DemiBold, mono=True, spacing=0.8))
        self.source.setStyleSheet(f"color: {theme.DIM};")
        self.source.setMinimumWidth(0)
        self.source.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        ranges.addWidget(self.source, 1)
        self.body.addLayout(ranges)

        self.alert = SignalAlert()
        self.alert.setMinimumWidth(0)
        self.body.addWidget(self.alert)
        self.chart = CandleChart()
        self.chart.set_empty("ENTER A TICKER\nRUN ANALYSIS TO LOAD CANDLES")
        self.chart.hovered.connect(self._show_hover)
        self.body.addWidget(self.chart, 1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.ohlc = QLabel("")
        self.ohlc.setFont(theme.font(8, mono=True))
        self.ohlc.setStyleSheet(f"color: {theme.MUTED};")
        self.ohlc.setMinimumWidth(0)
        self.ohlc.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        footer.addWidget(self.ohlc, 1)
        note = QLabel("CANDLES · VOLUME · MA")
        note.setFont(theme.font(8, QFont.Weight.DemiBold, mono=True, spacing=0.8))
        note.setStyleSheet(f"color: {theme.DIM};")
        footer.addWidget(note)
        self.body.addLayout(footer)

        self.setMinimumWidth(0)
        self.setMinimumHeight(300)

    def set_range(self, range_key: str) -> None:
        if range_key not in RANGES or range_key == self._range:
            return
        self._range = range_key
        self.refresh()

    def load_ticker(self, ticker: str, *, analyzing: bool = True) -> None:
        ticker = str(ticker or "").strip().upper()
        if not ticker:
            return
        self._ticker = ticker
        self.symbol.setText(ticker)
        self.price.setText("—")
        self.change.setText("")
        self.ohlc.setText("")
        if analyzing:
            self.alert.set_loading(ticker)
        else:
            self.alert.set_preview(ticker)
        self._awaiting = analyzing
        self._has_alert = False
        self.refresh()

    def mark_analyzing(self) -> None:
        if not self._ticker:
            return
        self.alert.set_loading(self._ticker)
        self._awaiting = True
        self._has_alert = False

    def refresh(self) -> None:
        if not self._ticker:
            return
        self._request += 1
        token = self._request
        self.chart.set_loading()
        self.source.setText("FETCHING YAHOO CANDLES…")
        thread = CallThread(fetch_candles, self._ticker, self._range, parent=self)
        self._threads.append(thread)
        thread.ok.connect(lambda payload, current=token: self._loaded(payload, current))
        thread.failed.connect(lambda message, current=token: self._failed(message, current))
        thread.finished.connect(lambda current=thread: self._forget(current))
        thread.start()

    def _forget(self, thread: CallThread) -> None:
        if thread in self._threads:
            self._threads.remove(thread)

    def _loaded(self, payload: object, token: int) -> None:
        if token != self._request or not isinstance(payload, dict):
            return
        self.chart.set_payload(payload)
        price = payload.get("price")
        change = payload.get("change")
        if isinstance(price, (int, float)):
            self.price.setText(f"${price:,.2f}")
        if isinstance(change, (int, float)):
            tone = theme.GREEN if change >= 0 else theme.RED
            self.change.setText(f"{change:+.2f}%")
            self.change.setStyleSheet(f"color: {tone};")
        currency = str(payload.get("currency") or "")
        candles = list(payload.get("candles") or [])
        span = f"{candles[0]['label'].upper()}–{candles[-1]['label'].upper()}" if candles else ""
        self.source.setText(f"YAHOO · {self._range} · {span}" if span else f"YAHOO FINANCE · {currency}")
        self.source.setStyleSheet(f"color: {theme.DIM};")
        self.source.setToolTip(f"Yahoo Finance {currency} OHLCV · research only")

    def _failed(self, message: str, token: int) -> None:
        if token != self._request:
            return
        self.chart.set_error(message)
        self.price.setText("—")
        self.change.setText("")
        self.source.setText("YAHOO FINANCE · UNAVAILABLE")
        self.source.setStyleSheet(f"color: {theme.RED};")

    def _show_hover(self, candle: object) -> None:
        if not isinstance(candle, dict):
            self.ohlc.setText("")
            return
        self.ohlc.setText(
            f"{candle['label']}  O {candle['open']:,.2f}  H {candle['high']:,.2f}  "
            f"L {candle['low']:,.2f}  C {candle['close']:,.2f}  V {int(candle['volume']):,}"
        )

    def set_alert(self, ticker: str, action: str, confidence: str, rationale: object) -> None:
        self._has_alert = True
        self.alert.set_decision(ticker, action, confidence, list(rationale or []))

    def finish_run(self, code: int, stopped: bool) -> None:
        if self._awaiting and not self._has_alert:
            if stopped or code == 130:
                self.alert.set_no_decision(self._ticker, "Run stopped before a fund decision.")
            else:
                self.alert.set_no_decision(self._ticker)
            self._awaiting = False

    def shutdown(self) -> None:
        for thread in list(self._threads):
            thread.requestInterruption()
            thread.wait(1800)
