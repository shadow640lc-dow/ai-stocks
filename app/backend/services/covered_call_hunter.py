from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class CoveredCallCandidate:
    ticker: str

    # Underlying
    stock_price: float
    market_cap: float | None

    # Stock quality
    quality_score: float
    growth_score: float
    valuation_score: float
    financial_health_score: float

    # Option
    strike: float | None
    expiration: str | None
    days_to_expiration: int | None
    premium: float | None
    premium_yield: float | None
    annualized_premium_yield: float | None

    # Liquidity
    open_interest: int | None
    option_volume: int | None
    bid: float | None
    ask: float | None
    bid_ask_spread_pct: float | None

    # Risk
    implied_volatility: float | None
    iv_rank: float | None
    delta: float | None
    earnings_date: str | None

    # Strategy metrics
    upside_to_strike_pct: float | None
    downside_break_even_pct: float | None
    max_profit_pct: float | None

    # Final ranking
    score: float
    classification: str
    warnings: list[str]

    # Order-ready contract reference (OCC symbol, e.g. AAPL260116C00240000)
    contract_symbol: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CoveredCallHunter:
    """
    Research-only covered-call screening engine.

    This module does NOT place trades.
    """

    def __init__(
        self,
        min_quality_score: float = 70.0,
        min_option_volume: int = 100,
        min_open_interest: int = 500,
        max_bid_ask_spread_pct: float = 5.0,
        min_days_to_expiration: int = 21,
        max_days_to_expiration: int = 45,
    ):
        self.min_quality_score = min_quality_score
        self.min_option_volume = min_option_volume
        self.min_open_interest = min_open_interest
        self.max_bid_ask_spread_pct = max_bid_ask_spread_pct
        self.min_days_to_expiration = min_days_to_expiration
        self.max_days_to_expiration = max_days_to_expiration

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        if value is None:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _percentage(
        numerator: float | None,
        denominator: float | None,
    ) -> float | None:
        if numerator is None or denominator in (None, 0):
            return None

        return (numerator / denominator) * 100

    @staticmethod
    def _money(value: Any) -> str:
        if value is None:
            return "N/A"

        try:
            value = float(value)
        except (TypeError, ValueError):
            return "N/A"

        if abs(value) >= 1_000_000_000_000:
            return f"${value / 1_000_000_000_000:.2f}T"

        if abs(value) >= 1_000_000_000:
            return f"${value / 1_000_000_000:.2f}B"

        if abs(value) >= 1_000_000:
            return f"${value / 1_000_000:.2f}M"

        if abs(value) >= 1_000:
            return f"${value / 1_000:.2f}K"

        return f"${value:,.2f}"

    @staticmethod
    def _compact_number(value: Any) -> str:
        if value is None:
            return "N/A"

        try:
            value = float(value)
        except (TypeError, ValueError):
            return "N/A"

        if abs(value) >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2f}B"

        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:.2f}M"

        if abs(value) >= 1_000:
            return f"{value / 1_000:.2f}K"

        return f"{value:,.0f}"

    @staticmethod
    def _pct(value: Any, signed: bool = False) -> str:
        if value is None:
            return "N/A"

        try:
            value = float(value)
        except (TypeError, ValueError):
            return "N/A"

        if signed:
            return f"{value:+.2f}%"

        return f"{value:.2f}%"

    @staticmethod
    def _iv_percent(value: Any) -> str:
        if value is None:
            return "N/A"

        try:
            value = float(value)
        except (TypeError, ValueError):
            return "N/A"

        # IV is normally stored as decimal, e.g. 0.42 = 42%.
        if value <= 2:
            value *= 100

        return f"{value:.2f}%"

    def calculate_option_metrics(
        self,
        stock_price: float,
        strike: float,
        premium: float,
        days_to_expiration: int,
    ) -> dict[str, float | None]:

        premium_yield = self._percentage(
            premium,
            stock_price,
        )

        annualized_yield = None

        if premium_yield is not None and days_to_expiration > 0:
            annualized_yield = (
                premium_yield
                * 365
                / days_to_expiration
            )

        upside_to_strike = self._percentage(
            strike - stock_price,
            stock_price,
        )

        break_even = stock_price - premium

        downside_break_even = self._percentage(
            break_even - stock_price,
            stock_price,
        )

        max_profit = self._percentage(
            (strike - stock_price) + premium,
            stock_price,
        )

        return {
            "premium_yield": premium_yield,
            "annualized_premium_yield": annualized_yield,
            "upside_to_strike_pct": upside_to_strike,
            "downside_break_even_pct": downside_break_even,
            "max_profit_pct": max_profit,
        }

    def calculate_liquidity_score(
        self,
        option_volume: int | None,
        open_interest: int | None,
        bid: float | None,
        ask: float | None,
    ) -> float:

        score = 0.0

        if option_volume is not None:
            if option_volume >= 5000:
                score += 35
            elif option_volume >= 1000:
                score += 25
            elif option_volume >= self.min_option_volume:
                score += 15

        if open_interest is not None:
            if open_interest >= 10000:
                score += 35
            elif open_interest >= 2500:
                score += 25
            elif open_interest >= self.min_open_interest:
                score += 15

        if bid is not None and ask is not None and bid > 0:
            midpoint = (bid + ask) / 2

            if midpoint > 0:
                spread_pct = (
                    (ask - bid)
                    / midpoint
                    * 100
                )

                if spread_pct <= 1:
                    score += 30
                elif spread_pct <= 2.5:
                    score += 20
                elif spread_pct <= self.max_bid_ask_spread_pct:
                    score += 10

        return min(score, 100.0)

    def calculate_score(
        self,
        quality_score: float,
        liquidity_score: float,
        premium_yield: float | None,
        iv_rank: float | None,
        upside_to_strike_pct: float | None,
        earnings_date: str | None,
    ) -> tuple[float, list[str]]:

        warnings: list[str] = []

        score = 0.0

        # Underlying quality: 40%
        score += max(
            0.0,
            min(quality_score, 100.0),
        ) * 0.40

        # Option liquidity: 25%
        score += liquidity_score * 0.25

        # Premium: 20%
        if premium_yield is not None:
            premium_score = min(
                premium_yield * 20,
                100,
            )

            score += premium_score * 0.20

        # IV rank: 15%
        if iv_rank is not None:
            score += min(
                max(iv_rank, 0),
                100,
            ) * 0.15

            if iv_rank >= 80:
                warnings.append(
                    "Very high IV may indicate elevated event risk."
                )

        if upside_to_strike_pct is not None:
            if upside_to_strike_pct < 3:
                warnings.append(
                    "Strike provides limited upside before assignment."
                )

        if earnings_date:
            warnings.append(
                "Check earnings timing before selling the call."
            )

        return round(score, 2), warnings

    def classify(
        self,
        score: float,
        warnings: list[str],
        quality_score: float,
        liquidity_score: float,
    ) -> str:

        if quality_score < self.min_quality_score:
            return "AVOID"

        if liquidity_score < 50:
            return "AVOID"

        if score >= 80 and not warnings:
            return "STRONG_CANDIDATE"

        if score >= 65:
            return "RESEARCH"

        return "WATCH"

    def evaluate(
        self,
        *,
        ticker: str,
        stock_price: float,
        market_cap: float | None,
        quality_score: float,
        growth_score: float,
        valuation_score: float,
        financial_health_score: float,
        strike: float | None,
        expiration: str | None,
        days_to_expiration: int | None,
        premium: float | None,
        open_interest: int | None,
        option_volume: int | None,
        bid: float | None,
        ask: float | None,
        implied_volatility: float | None,
        iv_rank: float | None,
        delta: float | None,
        earnings_date: str | None,
    ) -> CoveredCallCandidate:

        option_metrics = {
            "premium_yield": None,
            "annualized_premium_yield": None,
            "upside_to_strike_pct": None,
            "downside_break_even_pct": None,
            "max_profit_pct": None,
        }

        if (
            strike is not None
            and premium is not None
            and days_to_expiration is not None
        ):
            option_metrics = self.calculate_option_metrics(
                stock_price=stock_price,
                strike=strike,
                premium=premium,
                days_to_expiration=days_to_expiration,
            )

        liquidity_score = self.calculate_liquidity_score(
            option_volume=option_volume,
            open_interest=open_interest,
            bid=bid,
            ask=ask,
        )

        score, warnings = self.calculate_score(
            quality_score=quality_score,
            liquidity_score=liquidity_score,
            premium_yield=option_metrics[
                "premium_yield"
            ],
            iv_rank=iv_rank,
            upside_to_strike_pct=option_metrics[
                "upside_to_strike_pct"
            ],
            earnings_date=earnings_date,
        )

        spread_pct = None

        if bid is not None and ask is not None and bid > 0:
            midpoint = (bid + ask) / 2

            if midpoint > 0:
                spread_pct = (
                    (ask - bid)
                    / midpoint
                    * 100
                )

                if spread_pct > self.max_bid_ask_spread_pct:
                    warnings.append(
                        f"Wide bid/ask spread: {spread_pct:.2f}%."
                    )

        classification = self.classify(
            score=score,
            warnings=warnings,
            quality_score=quality_score,
            liquidity_score=liquidity_score,
        )

        return CoveredCallCandidate(
            ticker=ticker.upper(),
            stock_price=stock_price,
            market_cap=market_cap,

            quality_score=quality_score,
            growth_score=growth_score,
            valuation_score=valuation_score,
            financial_health_score=financial_health_score,

            strike=strike,
            expiration=expiration,
            days_to_expiration=days_to_expiration,

            premium=premium,
            premium_yield=option_metrics[
                "premium_yield"
            ],
            annualized_premium_yield=option_metrics[
                "annualized_premium_yield"
            ],

            open_interest=open_interest,
            option_volume=option_volume,
            bid=bid,
            ask=ask,
            bid_ask_spread_pct=spread_pct,

            implied_volatility=implied_volatility,
            iv_rank=iv_rank,
            delta=delta,
            earnings_date=earnings_date,

            upside_to_strike_pct=option_metrics[
                "upside_to_strike_pct"
            ],
            downside_break_even_pct=option_metrics[
                "downside_break_even_pct"
            ],
            max_profit_pct=option_metrics[
                "max_profit_pct"
            ],

            score=score,
            classification=classification,
            warnings=warnings,
        )

    def build_human_summary(
        self,
        candidate: CoveredCallCandidate,
    ) -> str:
        """
        Build the human-readable terminal report.

        Research-only.
        This does not place or simulate trades.
        """

        icons = {
            "STRONG_CANDIDATE": "🟢",
            "RESEARCH": "🟠",
            "WATCH": "🟡",
            "AVOID": "🔴",
        }

        icon = icons.get(
            candidate.classification,
            "🤖",
        )

        lines = [
            "",
            "╭──────────────────────────────────────────────────╮",
            "│              📞 COVERED CALL HUNTER              │",
            "│                OPTIONS INTELLIGENCE              │",
            "├──────────────────────────────────────────────────┤",
            f"│ {candidate.ticker:<8} {icon} "
            f"{candidate.classification:<22} │",
            f"│ Hunter Score: {candidate.score:>6.2f}/100              │",
            "╰──────────────────────────────────────────────────╯",
            "",
            "📊 STOCK SNAPSHOT",
            "────────────────────────────────────────────────────",
            f"  Price             {self._money(candidate.stock_price)}",
            f"  Market Cap        {self._money(candidate.market_cap)}",
            f"  Quality Score     {candidate.quality_score:.1f}/100",
            f"  Growth Score      {candidate.growth_score:.1f}/100",
            f"  Valuation Score   {candidate.valuation_score:.1f}/100",
            f"  Financial Health  "
            f"{candidate.financial_health_score:.1f}/100",
            "",
            "📞 COVERED CALL",
            "────────────────────────────────────────────────────",
            f"  Strike            {self._money(candidate.strike)}",
            f"  Expiration        "
            f"{candidate.expiration or 'N/A'}",
            f"  Days to Expiry    "
            f"{candidate.days_to_expiration or 'N/A'}",
            f"  Premium           "
            f"{self._money(candidate.premium)}",
            f"  Premium Yield     "
            f"{self._pct(candidate.premium_yield)}",
            f"  Annualized Yield  "
            f"{self._pct(candidate.annualized_premium_yield)}",
            f"  Implied Vol.      "
            f"{self._iv_percent(candidate.implied_volatility)}",
            f"  IV Rank           "
            f"{self._pct(candidate.iv_rank)}",
            f"  Delta             "
            f"{candidate.delta:.2f}"
            if candidate.delta is not None
            else "  Delta             N/A",
            "",
            "💧 OPTION LIQUIDITY",
            "────────────────────────────────────────────────────",
            f"  Option Volume     "
            f"{self._compact_number(candidate.option_volume)}",
            f"  Open Interest     "
            f"{self._compact_number(candidate.open_interest)}",
            f"  Bid               "
            f"{self._money(candidate.bid)}",
            f"  Ask               "
            f"{self._money(candidate.ask)}",
            f"  Bid/Ask Spread    "
            f"{self._pct(candidate.bid_ask_spread_pct)}",
            "",
            "🎯 RETURN PROFILE",
            "────────────────────────────────────────────────────",
            f"  Upside to Strike  "
            f"{self._pct(candidate.upside_to_strike_pct)}",
            f"  Break-even        "
            f"{self._pct(candidate.downside_break_even_pct)}",
            f"  Max Profit        "
            f"{self._pct(candidate.max_profit_pct)}",
            "",
            "🏆 HUNTER SCORE",
            "────────────────────────────────────────────────────",
            f"  Overall Score      "
            f"{candidate.score:.2f}/100",
            "",
            "⚠️ RISKS & WARNINGS",
            "────────────────────────────────────────────────────",
        ]

        if candidate.warnings:
            for warning in candidate.warnings:
                lines.append(f"  • {warning}")
        else:
            lines.append(
                "  ✓ No major warnings detected."
            )

        if candidate.earnings_date:
            lines.extend(
                [
                    "",
                    f"  Earnings Date     "
                    f"{candidate.earnings_date}",
                    "  ⚠ Review earnings timing before",
                    "    considering the strategy.",
                ]
            )

        lines.extend(
            [
                "",
                "🧠 HUNTER VERDICT",
                "────────────────────────────────────────────────────",
            ]
        )

        verdicts = {
            "STRONG_CANDIDATE": (
                "This candidate scores well across "
                "underlying quality and option "
                "characteristics. It warrants deeper "
                "research before any investment decision."
            ),
            "RESEARCH": (
                "This candidate has attractive "
                "characteristics, but one or more "
                "factors require additional verification "
                "before it should be considered."
            ),
            "WATCH": (
                "This candidate is worth monitoring, "
                "but the current combination of quality, "
                "liquidity, premium, or risk does not "
                "make it a top candidate."
            ),
            "AVOID": (
                "This candidate does not currently meet "
                "the Hunter's minimum requirements."
            ),
        }

        lines.append(
            verdicts.get(
                candidate.classification,
                "Additional research is required.",
            )
        )

        lines.extend(
            [
                "",
                "📋 NEXT CHECKS",
                "────────────────────────────────────────────────────",
                "  1. Verify the underlying company remains worth owning.",
                "  2. Review the option chain and liquidity.",
                "  3. Check upcoming earnings and major events.",
                "  4. Compare multiple strikes and expirations.",
                "  5. Review downside risk before considering the strategy.",
                "",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "🚫 NO TRADE EXECUTED",
                "Covered Call Hunter research-only mode",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                "",
            ]
        )

        return "\n".join(lines)


covered_call_hunter = CoveredCallHunter()
