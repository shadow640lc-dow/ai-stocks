from __future__ import annotations

from dataclasses import dataclass, field
import os
import sys
from typing import Any


# ================================================================
# DECISION ENGINE
# ================================================================
#
# Research-only decision support.
#
# IMPORTANT:
# - Never executes trades.
# - Never places orders.
# - Never invents missing market data.
# - Separates data quality from investment score.
#
# The engine evaluates:
#   1. Underlying stock quality
#   2. Covered-call opportunity
#   3. Risk
#   4. Data completeness
#
# ================================================================


@dataclass
class DecisionResult:
    ticker: str

    decision: str
    confidence: float

    overall_score: float
    stock_score: float
    option_score: float
    risk_score: float
    data_quality_score: float

    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_data: list[str] = field(default_factory=list)

    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "decision": self.decision,
            "confidence": round(self.confidence, 2),
            "overall_score": round(self.overall_score, 2),
            "stock_score": round(self.stock_score, 2),
            "option_score": round(self.option_score, 2),
            "risk_score": round(self.risk_score, 2),
            "data_quality_score": round(self.data_quality_score, 2),
            "reasons": self.reasons,
            "warnings": self.warnings,
            "missing_data": self.missing_data,
            "metrics": self.metrics,
        }


class DecisionEngine:
    """
    Research-only decision engine.

    This engine does NOT execute trades.

    It ranks opportunities using:
        underlying quality
        option attractiveness
        risk
        data quality
    """

    # ------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------

    def evaluate(
        self,
        ticker: str,
        stock: dict[str, Any] | None = None,
        option: dict[str, Any] | None = None,
    ) -> DecisionResult:

        stock = stock or {}
        option = option or {}

        ticker = str(
            ticker or stock.get("ticker") or option.get("ticker") or "UNKNOWN"
        ).upper()

        stock_score, stock_reasons, stock_warnings = (
            self._score_stock(stock)
        )

        option_score, option_reasons, option_warnings = (
            self._score_option(option)
        )

        risk_score, risk_warnings = (
            self._score_risk(stock, option)
        )

        data_quality_score, missing_data = (
            self._score_data_quality(stock, option)
        )

        # --------------------------------------------------------
        # WEIGHTING
        # --------------------------------------------------------
        #
        # The underlying stock matters most.
        #
        # 45% stock
        # 30% option
        # 15% risk
        # 10% data quality
        #
        # This prevents a giant option premium from automatically
        # making a bad company look attractive.
        # --------------------------------------------------------

        overall_score = (
            stock_score * 0.45
            + option_score * 0.30
            + risk_score * 0.15
            + data_quality_score * 0.10
        )

        reasons = stock_reasons + option_reasons
        warnings = stock_warnings + option_warnings + risk_warnings

        decision = self._determine_decision(
            overall_score=overall_score,
            stock_score=stock_score,
            option_score=option_score,
            risk_score=risk_score,
            data_quality_score=data_quality_score,
            warnings=warnings,
        )

        confidence = self._calculate_confidence(
            overall_score=overall_score,
            data_quality_score=data_quality_score,
            warning_count=len(warnings),
        )

        metrics = {
            "stock": stock,
            "option": option,
        }

        return DecisionResult(
            ticker=ticker,
            decision=decision,
            confidence=confidence,
            overall_score=overall_score,
            stock_score=stock_score,
            option_score=option_score,
            risk_score=risk_score,
            data_quality_score=data_quality_score,
            reasons=reasons,
            warnings=warnings,
            missing_data=missing_data,
            metrics=metrics,
        )

    # ------------------------------------------------------------
    # STOCK SCORE
    # ------------------------------------------------------------

    def _score_stock(
        self,
        stock: dict[str, Any],
    ) -> tuple[float, list[str], list[str]]:

        reasons: list[str] = []
        warnings: list[str] = []

        scores: list[float] = []

        quality = self._number(stock.get("quality_score"))
        growth = self._number(stock.get("growth_score"))
        valuation = self._number(stock.get("valuation_score"))
        health = self._number(
            stock.get("financial_health_score")
        )

        if quality is not None:
            scores.append(self._clamp(quality))
        else:
            warnings.append("Underlying quality score unavailable.")

        if growth is not None:
            scores.append(self._clamp(growth))

            if growth >= 70:
                reasons.append(
                    f"Growth profile is strong ({growth:.0f}/100)."
                )

        else:
            warnings.append("Growth score unavailable.")

        if valuation is not None:
            scores.append(self._clamp(valuation))

            if valuation < 45:
                warnings.append(
                    f"Valuation score is weak ({valuation:.0f}/100)."
                )

        else:
            warnings.append("Valuation score unavailable.")

        if health is not None:
            scores.append(self._clamp(health))

            if health >= 75:
                reasons.append(
                    f"Financial health is strong ({health:.0f}/100)."
                )

            elif health < 50:
                warnings.append(
                    f"Financial health is weak ({health:.0f}/100)."
                )

        else:
            warnings.append(
                "Financial health score unavailable."
            )

        if not scores:
            return 0.0, reasons, warnings

        return (
            sum(scores) / len(scores),
            reasons,
            warnings,
        )

    # ------------------------------------------------------------
    # OPTION SCORE
    # ------------------------------------------------------------

    def _score_option(
        self,
        option: dict[str, Any],
    ) -> tuple[float, list[str], list[str]]:

        reasons: list[str] = []
        warnings: list[str] = []

        score = 50.0

        premium_yield = self._number(
            option.get("premium_yield")
        )

        annualized_yield = self._number(
            option.get("annualized_premium_yield")
        )

        delta = self._number(
            option.get("delta")
        )

        spread = self._number(
            option.get("bid_ask_spread_pct")
        )

        volume = self._number(
            option.get("option_volume")
        )

        open_interest = self._number(
            option.get("open_interest")
        )

        otm = self._number(
            option.get("upside_to_strike_pct")
        )

        iv_rank = self._number(
            option.get("iv_rank")
        )

        # --------------------------------------------------------
        # PREMIUM
        # --------------------------------------------------------

        if premium_yield is not None:

            if premium_yield >= 4:
                score += 12
                reasons.append(
                    f"Strong option premium yield ({premium_yield:.2f}%)."
                )

            elif premium_yield >= 2.5:
                score += 8
                reasons.append(
                    f"Attractive option premium yield ({premium_yield:.2f}%)."
                )

            elif premium_yield >= 1:
                score += 3

            elif premium_yield < 0.5:
                score -= 8
                warnings.append(
                    f"Low premium yield ({premium_yield:.2f}%)."
                )

        else:
            warnings.append("Premium yield unavailable.")

        # --------------------------------------------------------
        # DELTA
        # --------------------------------------------------------

        if delta is not None:

            if 0.20 <= delta <= 0.35:
                score += 8
                reasons.append(
                    f"Delta is within the preferred research range ({delta:.2f})."
                )

            elif delta > 0.40:
                score -= 10
                warnings.append(
                    f"High call delta ({delta:.2f}) increases assignment risk."
                )

            elif delta < 0.15:
                score -= 3

        else:
            warnings.append(
                "Option delta unavailable."
            )

        # --------------------------------------------------------
        # LIQUIDITY
        # --------------------------------------------------------

        if spread is not None:

            if spread <= 3:
                score += 10

            elif spread <= 5:
                score += 5

            elif spread <= 8:
                score -= 5
                warnings.append(
                    f"Bid/ask spread is wide ({spread:.2f}%)."
                )

            else:
                score -= 15
                warnings.append(
                    f"Very wide bid/ask spread ({spread:.2f}%)."
                )

        else:
            warnings.append(
                "Bid/ask spread unavailable."
            )

        if volume is not None:

            if volume >= 1000:
                score += 5

            elif volume < 100:
                score -= 5
                warnings.append(
                    f"Low option volume ({volume:.0f})."
                )

        else:
            warnings.append(
                "Option volume unavailable."
            )

        if open_interest is not None:

            if open_interest >= 2000:
                score += 5

            elif open_interest < 250:
                score -= 5
                warnings.append(
                    f"Low open interest ({open_interest:.0f})."
                )

        else:
            warnings.append(
                "Open interest unavailable."
            )

        # --------------------------------------------------------
        # OTM DISTANCE
        # --------------------------------------------------------

        if otm is not None:

            if 5 <= otm <= 15:
                score += 5
                reasons.append(
                    f"Strike provides {otm:.2f}% upside before assignment."
                )

            elif otm < 3:
                score -= 5
                warnings.append(
                    f"Strike is only {otm:.2f}% above the stock price."
                )

        # --------------------------------------------------------
        # IV
        # --------------------------------------------------------

        if iv_rank is not None:

            if iv_rank >= 60:
                score += 5
                reasons.append(
                    f"IV rank is elevated ({iv_rank:.0f})."
                )

            elif iv_rank < 30:
                score -= 2

        # Annualized yield is informational rather than dominant.
        if annualized_yield is not None:
            if annualized_yield >= 50:
                warnings.append(
                    "Very high annualized premium deserves additional risk review."
                )

        return (
            self._clamp(score),
            reasons,
            warnings,
        )

    # ------------------------------------------------------------
    # RISK SCORE
    # ------------------------------------------------------------

    def _score_risk(
        self,
        stock: dict[str, Any],
        option: dict[str, Any],
    ) -> tuple[float, list[str]]:

        score = 100.0
        warnings: list[str] = []

        health = self._number(
            stock.get("financial_health_score")
        )

        valuation = self._number(
            stock.get("valuation_score")
        )

        spread = self._number(
            option.get("bid_ask_spread_pct")
        )

        delta = self._number(
            option.get("delta")
        )

        earnings_date = option.get(
            "earnings_date"
        ) or stock.get(
            "earnings_date"
        )

        # --------------------------------------------------------
        # COMPANY RISK
        # --------------------------------------------------------

        if health is not None:

            if health < 50:
                score -= 25
                warnings.append(
                    "Underlying financial health is weak."
                )

            elif health < 65:
                score -= 10

        # --------------------------------------------------------
        # VALUATION RISK
        # --------------------------------------------------------

        if valuation is not None:

            if valuation < 40:
                score -= 15
                warnings.append(
                    "Underlying valuation appears expensive."
                )

        # --------------------------------------------------------
        # OPTION LIQUIDITY RISK
        # --------------------------------------------------------

        if spread is not None:

            if spread > 10:
                score -= 20

            elif spread > 5:
                score -= 10

        # --------------------------------------------------------
        # ASSIGNMENT RISK
        # --------------------------------------------------------

        if delta is not None:

            if delta > 0.40:
                score -= 15

            elif delta > 0.35:
                score -= 5

        # --------------------------------------------------------
        # EARNINGS RISK
        # --------------------------------------------------------

        if earnings_date:
            warnings.append(
                "Earnings/event timing must be checked before selling the call."
            )

            score -= 8

        return (
            self._clamp(score),
            warnings,
        )

    # ------------------------------------------------------------
    # DATA QUALITY
    # ------------------------------------------------------------

    def _score_data_quality(
        self,
        stock: dict[str, Any],
        option: dict[str, Any],
    ) -> tuple[float, list[str]]:

        required_stock_fields = [
            "price",
            "market_cap",
            "quality_score",
            "growth_score",
            "valuation_score",
            "financial_health_score",
        ]

        required_option_fields = [
            "strike",
            "expiration",
            "days_to_expiration",
            "premium",
            "bid",
            "ask",
            "option_volume",
            "open_interest",
        ]

        missing: list[str] = []

        present = 0
        total = len(
            required_stock_fields
            + required_option_fields
        )

        for field in required_stock_fields:

            if stock.get(field) is not None:
                present += 1
            else:
                missing.append(
                    f"stock.{field}"
                )

        for field in required_option_fields:

            if option.get(field) is not None:
                present += 1
            else:
                missing.append(
                    f"option.{field}"
                )

        score = (
            present / total * 100
            if total
            else 0
        )

        return (
            self._clamp(score),
            missing,
        )

    # ------------------------------------------------------------
    # DECISION
    # ------------------------------------------------------------

    def _determine_decision(
        self,
        overall_score: float,
        stock_score: float,
        option_score: float,
        risk_score: float,
        data_quality_score: float,
        warnings: list[str],
    ) -> str:

        # Insufficient data always wins.
        if data_quality_score < 60:
            return "INSUFFICIENT DATA"

        # Bad underlying should not be rescued by option premium.
        if stock_score < 45:
            return "AVOID"

        if risk_score < 45:
            return "AVOID"

        if overall_score >= 80:
            return "STRONG CANDIDATE"

        if overall_score >= 70:
            return "CANDIDATE"

        if overall_score >= 60:
            return "WATCH"

        if overall_score >= 50:
            return "SPECULATIVE"

        return "AVOID"

    # ------------------------------------------------------------
    # CONFIDENCE
    # ------------------------------------------------------------

    def _calculate_confidence(
        self,
        overall_score: float,
        data_quality_score: float,
        warning_count: int,
    ) -> float:

        confidence = (
            data_quality_score * 0.60
            + overall_score * 0.40
        )

        confidence -= min(
            warning_count * 2,
            20,
        )

        return self._clamp(confidence)

    # ------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------

    @staticmethod
    def _number(
        value: Any,
    ) -> float | None:

        try:

            if value is None:
                return None

            return float(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _clamp(
        value: float,
        minimum: float = 0.0,
        maximum: float = 100.0,
    ) -> float:

        return max(
            minimum,
            min(
                maximum,
                float(value),
            ),
        )


# Singleton used by the application.
decision_engine = DecisionEngine()


# ================================================================
# HUMAN-READABLE REPORT
# ================================================================

_TERMINAL_WIDTH = 76
_ANSI = {
    "blue": "\033[38;5;39m",
    "green": "\033[38;5;46m",
    "yellow": "\033[38;5;220m",
    "red": "\033[38;5;203m",
    "muted": "\033[38;5;245m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}


def _color_enabled() -> bool:
    """Use colour only for an interactive terminal that has not opted out."""
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def terminal_style(text: str, *styles: str) -> str:
    """Apply optional terminal styling without changing report content."""
    if not _color_enabled() or not styles:
        return text

    return "".join(_ANSI[style] for style in styles) + text + _ANSI["reset"]


def status_style(decision: str) -> tuple[str, str]:
    """Return the visual marker and colour for an existing engine decision."""
    if decision in {"STRONG CANDIDATE", "CANDIDATE"}:
        return "●", "green"
    if decision in {"WATCH", "SPECULATIVE"}:
        return "●", "yellow"
    return "●", "red"


def score_bar(score: float, width: int = 20) -> str:
    """Render a fixed-width score indicator; this has no scoring effect."""
    clamped_score = max(0.0, min(100.0, float(score)))
    filled = round(clamped_score / 100 * width)
    return "█" * filled + "░" * (width - filled)


def terminal_box(title: str, subtitle: str | None = None) -> list[str]:
    """Build the shared neon-terminal header used by scanner reports."""
    lines = [
        terminal_style("╔" + "═" * _TERMINAL_WIDTH + "╗", "blue"),
        terminal_style(
            "║" + f"  {title}".ljust(_TERMINAL_WIDTH) + "║",
            "blue",
        ),
    ]
    if subtitle:
        lines.append(
            terminal_style(
                "║" + f"  {subtitle}".ljust(_TERMINAL_WIDTH) + "║",
                "blue",
            )
        )
    lines.append(terminal_style("╚" + "═" * _TERMINAL_WIDTH + "╝", "blue"))
    return lines


def terminal_section(title: str) -> str:
    return terminal_style(f"┌─ {title}", "blue", "bold")

def build_decision_summary(
    result: DecisionResult,
) -> str:
    marker, colour = status_style(result.decision)
    status = terminal_style(
        f"{marker} {result.decision}",
        colour,
        "bold",
    )
    lines: list[str] = [""]
    lines.extend(
        terminal_box(
            "💰 MEGATRON DECISION ENGINE  //  RESEARCH INTELLIGENCE",
            f"CONTRACT ANALYSIS · {result.ticker} · RESEARCH-ONLY",
        )
    )
    lines.append(f"  STATUS       {status}")
    lines.append(
        "  OVERALL      "
        f"{terminal_style(score_bar(result.overall_score), 'blue')} "
        f"{result.overall_score:05.1f}/100"
    )
    lines.append(f"  CONFIDENCE   {result.confidence:05.1f}%")

    lines.append("")
    lines.append(terminal_section("NEURAL SCOREBOARD"))
    for label, score in (
        ("Stock Quality", result.stock_score),
        ("Option Opportunity", result.option_score),
        ("Risk Score", result.risk_score),
        ("Data Quality", result.data_quality_score),
    ):
        lines.append(
            f"  {label:<20} "
            f"{terminal_style(score_bar(score), 'blue')} {score:05.1f}/100"
        )

    if result.reasons:

        lines.append("")
        lines.append(terminal_section("POSITIVE FACTORS"))

        for reason in result.reasons:
            lines.append(
                f"  • {reason}"
            )

    if result.warnings:

        lines.append("")
        lines.append(terminal_section("RISKS & WARNINGS"))

        for warning in result.warnings:
            lines.append(
                f"  • {warning}"
            )

    if result.missing_data:

        lines.append("")
        lines.append(terminal_section("MISSING DATA"))

        for field in result.missing_data:
            lines.append(
                f"  • {field}"
            )

    lines.append("")
    lines.append(terminal_section("ENGINE VERDICT"))

    verdicts = {
        "STRONG CANDIDATE":
            "Strong research candidate. Review the underlying and option details before making any decision.",

        "CANDIDATE":
            "Potential candidate. Further verification is recommended before considering the position.",

        "WATCH":
            "Interesting setup, but the current risk/reward does not justify immediate action.",

        "SPECULATIVE":
            "Speculative setup. Risk and uncertainty are elevated.",

        "AVOID":
            "The current combination of quality, risk, valuation, or option characteristics does not meet the engine's requirements.",

        "INSUFFICIENT DATA":
            "There is not enough reliable data to produce a trustworthy decision.",
    }

    lines.append(
        f"  {verdicts.get(result.decision, 'Review manually.')}"
    )

    lines.append("")
    lines.append(terminal_style("└" + "─" * _TERMINAL_WIDTH, "blue"))
    lines.append(terminal_style("  🛡  NO TRADE EXECUTED", "red", "bold"))
    lines.append(terminal_style("  Research and decision-support mode only", "muted"))
    lines.append(terminal_style("└" + "─" * _TERMINAL_WIDTH, "blue"))

    return "\n".join(lines)
