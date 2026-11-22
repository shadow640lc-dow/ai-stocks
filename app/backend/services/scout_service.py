import logging
import re
from typing import Any, Dict

import yfinance as yf
from ollama import AsyncClient


logger = logging.getLogger(__name__)


class ScoutService:
    """
    AI Scout intelligence layer.

    Scout is research/alert-only.
    It does NOT place trades.
    """

    DEFAULT_MODEL = "llama3.1:latest"

    def __init__(self):
        self.ollama = AsyncClient()

    # ============================================================
    # MAIN INVESTIGATION PIPELINE
    # ============================================================

    async def investigate(
        self,
        ticker: str,
        action: str | None = None,
        price: float | None = None,
        timeframe: str | None = None,
        message: str | None = None,
        model: str = DEFAULT_MODEL,
    ) -> Dict[str, Any]:

        ticker = ticker.upper().strip()

        market_data = await self._get_market_snapshot(ticker)

        if not market_data:
            return {
                "success": False,
                "ticker": ticker,
                "classification": "ERROR",
                "confidence": 0,
                "human_summary": (
                    f"Unable to retrieve current market data for {ticker}."
                ),
                "trading_enabled": False,
            }

        validation = self._validate_alert(
            action=action,
            price=price,
            message=message,
            market_data=market_data,
        )

        prompt = self._build_prompt(
            ticker=ticker,
            action=action,
            price=price,
            timeframe=timeframe,
            message=message,
            market_data=market_data,
            validation=validation,
        )

        try:
            response = await self.ollama.chat(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are AI Scout, a conservative stock-market "
                            "research assistant. You do not place trades. "
                            "Use the supplied market data as the source of "
                            "truth for numerical facts. Never invent news, "
                            "earnings, indicators, or events. If TradingView "
                            "and the supplied market data disagree, clearly "
                            "say so. Keep the analysis concise and practical."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
            )

            analysis = response["message"]["content"]

            classification = self._classify(analysis)
            confidence = self._extract_confidence(analysis)

            human_summary = self._build_human_summary(
                ticker=ticker,
                action=action,
                price=price,
                timeframe=timeframe,
                classification=classification,
                confidence=confidence,
                analysis=analysis,
                market_data=market_data,
                validation=validation,
            )

            return {
                "success": True,
                "ticker": ticker,
                "classification": classification,
                "confidence": confidence,
                "human_summary": human_summary,
                "analysis": analysis,
                "market_data": market_data,
                "alert_validation": validation,
                "model": model,
                "trading_enabled": False,
            }

        except Exception as exc:
            logger.exception("Scout Ollama analysis failed")

            return {
                "success": False,
                "ticker": ticker,
                "classification": "ERROR",
                "confidence": 0,
                "reason": str(exc),
                "human_summary": (
                    f"AI Scout could not complete the analysis for "
                    f"{ticker}: {exc}"
                ),
                "market_data": market_data,
                "alert_validation": validation,
                "trading_enabled": False,
            }

    # ============================================================
    # MARKET DATA
    # ============================================================

    async def _get_market_snapshot(
        self,
        ticker: str,
    ) -> Dict[str, Any]:
        """Retrieve a lightweight Yahoo Finance market snapshot."""

        try:
            stock = yf.Ticker(ticker)
            info = stock.fast_info

            price = info.get("lastPrice")
            previous_close = info.get("previousClose")

            price_change = None
            price_change_pct = None

            if price is not None and previous_close:
                price_change = float(price) - float(previous_close)
                price_change_pct = (
                    price_change / float(previous_close)
                ) * 100

            volume = info.get("lastVolume")
            average_volume = info.get("threeMonthAverageVolume")

            relative_volume = None

            if volume is not None and average_volume:
                relative_volume = float(volume) / float(average_volume)

            return {
                "price": price,
                "previous_close": previous_close,
                "price_change": price_change,
                "price_change_pct": price_change_pct,
                "day_high": info.get("dayHigh"),
                "day_low": info.get("dayLow"),
                "year_high": info.get("yearHigh"),
                "year_low": info.get("yearLow"),
                "market_cap": info.get("marketCap"),
                "volume": volume,
                "average_volume": average_volume,
                "relative_volume": relative_volume,
                "currency": info.get("currency"),
                "exchange": info.get("exchange"),
            }

        except Exception as exc:
            logger.warning(
                "Yahoo Finance snapshot failed for %s: %s",
                ticker,
                exc,
            )
            return {}

    # ============================================================
    # ALERT VALIDATION
    # ============================================================

    @staticmethod
    def _validate_alert(
        action: str | None,
        price: float | None,
        message: str | None,
        market_data: Dict[str, Any],
    ) -> Dict[str, Any]:

        validation = {
            "status": "NO_CONFLICT",
            "notes": [],
        }

        # --------------------------------------------------------
        # PRICE CHECK
        # --------------------------------------------------------

        if price is not None and market_data.get("price") is not None:

            alert_price = float(price)
            yahoo_price = float(market_data["price"])
            difference = abs(alert_price - yahoo_price)

            validation["alert_price"] = alert_price
            validation["yahoo_price"] = yahoo_price
            validation["price_difference"] = difference

            if difference > max(0.05, yahoo_price * 0.002):
                validation["status"] = "PRICE_MISMATCH"

                validation["notes"].append(
                    "Alert price differs materially from the current "
                    "market price."
                )

        # --------------------------------------------------------
        # VOLUME CHECK
        # --------------------------------------------------------

        message_lower = (message or "").lower()

        volume_claimed = (
            "volume" in message_lower
            and "above average" in message_lower
        )

        if volume_claimed:

            volume = market_data.get("volume")
            average = market_data.get("average_volume")

            if volume is not None and average is not None:

                if float(volume) >= float(average):

                    validation["volume_claim"] = "CONFIRMED"

                    validation["notes"].append(
                        "Current volume is at or above the "
                        "three-month average."
                    )

                else:

                    validation["volume_claim"] = "NOT_CONFIRMED"

                    if validation["status"] == "NO_CONFLICT":
                        validation["status"] = "ALERT_DISCREPANCY"

                    validation["notes"].append(
                        "The alert claims above-average volume, "
                        "but the supplied market data does not confirm it."
                    )

            else:
                validation["volume_claim"] = "UNKNOWN"

                validation["notes"].append(
                    "Volume could not be independently verified."
                )

        # --------------------------------------------------------
        # DEFAULT
        # --------------------------------------------------------

        if not validation["notes"]:
            validation["notes"].append(
                "No obvious conflict detected between the alert "
                "and the supplied market snapshot."
            )

        return validation

    # ============================================================
    # AI PROMPT
    # ============================================================

    def _build_prompt(
        self,
        ticker: str,
        action: str | None,
        price: float | None,
        timeframe: str | None,
        message: str | None,
        market_data: Dict[str, Any],
        validation: Dict[str, Any],
    ) -> str:

        return f"""
Analyze this stock-market alert as AI Scout.

TICKER
{ticker}

TRADINGVIEW ALERT
Action: {action or "UNKNOWN"}
Alert Price: {price if price is not None else "UNKNOWN"}
Timeframe: {timeframe or "UNKNOWN"}
Message: {message or "NONE"}

MARKET DATA
{market_data}

ALERT VALIDATION
{validation}

Choose exactly ONE classification:

IGNORE
WATCH
INVESTIGATE
HIGH_INTEREST

Confidence must be a whole number from 0 to 100.

Explain the alert in plain English.

IMPORTANT RULES:

- Treat the supplied market data as the numerical source of truth.
- Do not blindly trust the TradingView alert.
- If the alert conflicts with the market data, explicitly say so.
- Do not call a breakout confirmed unless the evidence supports it.
- Do not invent news.
- Do not invent earnings information.
- Do not invent technical indicators.
- Do not invent market events.
- Do not recommend a specific trade.
- Do not place or simulate a trade.
- This is research and alert analysis only.

Return these sections:

Classification
Confidence
Why it matters
Important risks
Recommended analyst team
What should be checked next
"""

    # ============================================================
    # HUMAN-READABLE REPORT
    # ============================================================

    def _build_human_summary(
        self,
        ticker: str,
        action: str | None,
        price: float | None,
        timeframe: str | None,
        classification: str,
        confidence: int,
        analysis: str,
        market_data: Dict[str, Any],
        validation: Dict[str, Any],
    ) -> str:

        icons = {
            "HIGH_INTEREST": "🚨",
            "INVESTIGATE": "🟠",
            "WATCH": "🟡",
            "IGNORE": "⚪",
            "ERROR": "❌",
        }

        icon = icons.get(classification, "🤖")

        current_price = market_data.get("price")
        previous_close = market_data.get("previous_close")
        change_pct = market_data.get("price_change_pct")

        volume = market_data.get("volume")
        average_volume = market_data.get("average_volume")
        relative_volume = market_data.get("relative_volume")

        market_cap = market_data.get("market_cap")

        lines = [
            "",
            "╭──────────────────────────────────────────────────╮",
            "│                  🤖 AI SCOUT                     │",
            "│               MARKET INTELLIGENCE               │",
            "├──────────────────────────────────────────────────┤",
            f"│ {ticker:<8} {icon} {classification:<22} │",
            f"│ Confidence: {confidence:>3}%                                │",
            "╰──────────────────────────────────────────────────╯",
            "",
            "📊 MARKET SNAPSHOT",
            "────────────────────────────────────────────────────",
            f"  Price          {self._money(current_price)}",
        ]

        if previous_close is not None:
            lines.append(
                f"  Previous Close {self._money(previous_close)}"
            )

        if change_pct is not None:
            lines.append(
                f"  Change         {change_pct:+.2f}%"
            )

        if action:
            lines.append(
                f"  Alert          {action.upper()}"
            )

        if timeframe:
            lines.append(
                f"  Timeframe      {timeframe}"
            )

        if volume is not None:
            lines.append(
                f"  Volume         {self._compact_number(volume)}"
            )

        if average_volume is not None:
            lines.append(
                f"  Avg Volume     {self._compact_number(average_volume)}"
            )

        if relative_volume is not None:
            lines.append(
                f"  Relative Vol.  {relative_volume:.2f}x"
            )

        if market_cap is not None:
            lines.append(
                f"  Market Cap     {self._money(market_cap)}"
            )

        # --------------------------------------------------------
        # VALIDATION
        # --------------------------------------------------------

        lines.extend(
            [
                "",
                "🔎 ALERT VALIDATION",
                "────────────────────────────────────────────────────",
            ]
        )

        status = validation.get("status")

        if status == "ALERT_DISCREPANCY":

            lines.append("  ⚠ ALERT NOT CONFIRMED")
            lines.append("")
            lines.append(
                "  TradingView and the supplied market data disagree."
            )

        elif status == "PRICE_MISMATCH":

            lines.append("  ⚠ PRICE MISMATCH")
            lines.append("")
            lines.append(
                "  Alert price differs materially from market data."
            )

        else:

            lines.append("  ✓ ALERT CONSISTENT")
            lines.append("")
            lines.append(
                "  No obvious conflict was detected."
            )

        for note in validation.get("notes", [])[:2]:
            lines.append(f"  • {note}")

        # --------------------------------------------------------
        # SCOUT VERDICT
        # --------------------------------------------------------

        lines.extend(
            [
                "",
                "🧠 SCOUT VERDICT",
                "────────────────────────────────────────────────────",
            ]
        )

        verdict = self._build_verdict(
            classification=classification,
            validation=validation,
        )

        lines.extend(
            self._wrap_text(verdict)
        )

        # --------------------------------------------------------
        # WHY IT MATTERS
        # --------------------------------------------------------

        why = self._extract_section(
            analysis,
            ["why it matters"],
        )

        if why:

            lines.extend(
                [
                    "",
                    "💡 WHY IT MATTERS",
                    "────────────────────────────────────────────────────",
                ]
            )

            lines.extend(
                self._wrap_text(
                    why,
                    bullet=True,
                )
            )

        # --------------------------------------------------------
        # RISKS
        # --------------------------------------------------------

        risks = self._extract_section(
            analysis,
            [
                "important risks",
                "risks",
            ],
        )

        if risks:

            lines.extend(
                [
                    "",
                    "⚠️ KEY RISKS",
                    "────────────────────────────────────────────────────",
                ]
            )

            lines.extend(
                self._format_list(
                    risks,
                )
            )

        # --------------------------------------------------------
        # TEAM
        # --------------------------------------------------------

        team = self._extract_section(
            analysis,
            [
                "recommended analyst team",
                "recommended team",
            ],
        )

        if team:

            lines.extend(
                [
                    "",
                    "👥 RECOMMENDED AI TEAM",
                    "────────────────────────────────────────────────────",
                ]
            )

            lines.extend(
                self._format_team(team)
            )

        # --------------------------------------------------------
        # NEXT CHECKS
        # --------------------------------------------------------

        next_checks = self._extract_section(
            analysis,
            [
                "what should be checked next",
                "what to check next",
                "next steps",
            ],
        )

        if next_checks:

            lines.extend(
                [
                    "",
                    "📋 NEXT CHECKS",
                    "────────────────────────────────────────────────────",
                ]
            )

            lines.extend(
                self._format_list(
                    next_checks,
                    numbered=True,
                )
            )

        # --------------------------------------------------------
        # FOOTER
        # --------------------------------------------------------

        lines.extend(
            [
                "",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "🚫 NO TRADE EXECUTED",
                "Research & alert mode only",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "",
            ]
        )

        return "\n".join(lines)

    # ============================================================
    # TEXT PARSING
    # ============================================================

    @staticmethod
    def _extract_section(
        text: str,
        headings: list[str],
    ) -> str:
        """Extract one section from the LLM response."""

        lines = text.splitlines()

        start = None

        for index, line in enumerate(lines):

            normalized = re.sub(
                r"[*#:_-]",
                " ",
                line.lower(),
            ).strip()

            if any(
                heading in normalized
                for heading in headings
            ):
                start = index + 1
                break

        if start is None:
            return ""

        collected = []

        stop_headings = [
            "classification",
            "confidence",
            "why it matters",
            "important risks",
            "recommended analyst team",
            "recommended team",
            "what should be checked next",
            "what to check next",
            "next steps",
        ]

        for line in lines[start:]:

            clean = line.strip()

            if not clean:
                if collected:
                    break
                continue

            normalized = re.sub(
                r"[*#:_-]",
                " ",
                clean.lower(),
            ).strip()

            if any(
                normalized.startswith(stop)
                for stop in stop_headings
            ):
                break

            collected.append(clean)

        return " ".join(collected).strip()

    @staticmethod
    def _wrap_text(
        text: str,
        bullet: bool = False,
        width: int = 72,
    ) -> list[str]:
        """Wrap text into clean terminal lines."""

        text = re.sub(
            r"[*#]+",
            "",
            text,
        )

        text = text.replace("\\n", " ")

        text = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        if not text:
            return []

        words = text.split()

        lines = []
        current = []

        for word in words:

            candidate = " ".join(
                current + [word]
            )

            if len(candidate) > width and current:

                prefix = "  • " if bullet else "  "

                lines.append(
                    prefix + " ".join(current)
                )

                current = [word]

            else:
                current.append(word)

        if current:

            prefix = "  • " if bullet else "  "

            lines.append(
                prefix + " ".join(current)
            )

        return lines

    @staticmethod
    def _format_list(
        text: str,
        numbered: bool = False,
    ) -> list[str]:
        """Convert AI lists into clean terminal lists."""

        text = re.sub(
            r"[*#]+",
            "",
            text,
        )

        # Normalize common list formats.
        text = re.sub(
            r"\s*(?:\d+[.)]|[-•])\s*",
            "\n",
            text,
        )

        items = []

        for item in text.splitlines():

            item = re.sub(
                r"\s+",
                " ",
                item,
            ).strip()

            if not item:
                continue

            items.append(item)

        if not items:
            return []

        result = []

        for index, item in enumerate(items, 1):

            wrapped = ScoutService._wrap_text(
                item,
                bullet=False,
            )

            if not wrapped:
                continue

            if numbered:
                wrapped[0] = (
                    f"  {index}. "
                    + wrapped[0].strip()
                )

            else:
                wrapped[0] = (
                    "  • "
                    + wrapped[0].strip()
                )

            result.extend(wrapped)

        return result

    @staticmethod
    def _format_team(
        text: str,
    ) -> list[str]:
        """Display recognized AI analysts only."""

        analysts = [
            "Technical Analyst",
            "Fundamentals Analyst",
            "Growth Analyst",
            "News Sentiment Analyst",
            "Sentiment Analyst",
            "Valuation Analyst",
            "Risk Management",
            "Warren Buffett",
            "Peter Lynch",
            "Phil Fisher",
            "Cathie Wood",
        ]

        found = []

        for analyst in analysts:

            if analyst.lower() in text.lower():
                found.append(analyst)

        if not found:
            return [
                "  • Use the core analyst team for deeper review."
            ]

        return [
            f"  {index}. {analyst}"
            for index, analyst in enumerate(
                found,
                1,
            )
        ]

    # ============================================================
    # CLASSIFICATION
    # ============================================================

    @staticmethod
    def _classify(
        analysis: str,
    ) -> str:

        text = analysis.upper()

        for classification in (
            "HIGH_INTEREST",
            "INVESTIGATE",
            "WATCH",
            "IGNORE",
        ):

            if classification in text:
                return classification

        return "WATCH"

    @staticmethod
    def _extract_confidence(
        analysis: str,
    ) -> int:

        match = re.search(
            r"confidence[^0-9]{0,20}([0-9]{1,3})",
            analysis,
            re.IGNORECASE,
        )

        if not match:
            return 50

        return max(
            0,
            min(
                100,
                int(match.group(1)),
            ),
        )

    # ============================================================
    # VERDICT
    # ============================================================

    @staticmethod
    def _build_verdict(
        classification: str,
        validation: Dict[str, Any],
    ) -> str:

        if validation.get("status") == "ALERT_DISCREPANCY":

            return (
                "The alert is not fully confirmed by the supplied "
                "market data. Scout recommends caution and deeper "
                "verification before treating this as a meaningful "
                "market signal."
            )

        if validation.get("status") == "PRICE_MISMATCH":

            return (
                "The alert price does not match the current market "
                "snapshot. Verify the alert before relying on it."
            )

        if classification == "HIGH_INTEREST":

            return (
                "The signal has enough supporting evidence to deserve "
                "immediate deeper investigation by the AI Hedge Fund team."
            )

        if classification == "INVESTIGATE":

            return (
                "The signal is interesting enough for deeper analyst "
                "review, but it is not a confirmed trading signal."
            )

        if classification == "WATCH":

            return (
                "The signal is worth monitoring, but the current "
                "evidence is not strong enough for escalation."
            )

        if classification == "IGNORE":

            return (
                "The available evidence does not support escalating "
                "this alert right now. Revisit it only if conditions change."
            )

        return (
            "Scout could not establish a reliable conclusion from "
            "the available information."
        )

    # ============================================================
    # DISPLAY HELPERS
    # ============================================================

    @staticmethod
    def _compact_number(
        value: Any,
    ) -> str:

        if value is None:
            return "N/A"

        value = float(value)

        if abs(value) >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2f}B"

        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:.2f}M"

        if abs(value) >= 1_000:
            return f"{value / 1_000:.2f}K"

        return f"{value:,.0f}"

    @staticmethod
    def _money(
        value: Any,
    ) -> str:

        if value is None:
            return "N/A"

        value = float(value)

        if abs(value) >= 1_000_000_000_000:
            return f"${value / 1_000_000_000_000:.2f}T"

        if abs(value) >= 1_000_000_000:
            return f"${value / 1_000_000_000:.2f}B"

        if abs(value) >= 1_000_000:
            return f"${value / 1_000_000:.2f}M"

        return f"${value:,.2f}"


scout_service = ScoutService()
