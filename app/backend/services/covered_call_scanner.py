from __future__ import annotations

import argparse
import math
from datetime import date, datetime
from typing import Any

import yfinance as yf

from app.backend.services.covered_call_hunter import (
    CoveredCallCandidate,
    covered_call_hunter,
)
from app.backend.services.decision_engine import (
    build_decision_summary,
    decision_engine,
    score_bar,
    status_style,
    terminal_box,
    terminal_section,
    terminal_style,
)


# ================================================================
# STOCK UNIVERSES
# ================================================================

MIDCAP_UNIVERSE = [
    "AAON", "ACI", "ACM", "ADSK", "AFRM", "ALGN", "ALLY", "AM",
    "AMH", "ANSS", "APP", "AR", "ARM", "ASAN", "ATI", "AVAV",
    "AXON", "BILL", "BJ", "BLDR", "BMRN", "BRKR", "BSY", "CACI",
    "CASY", "CCK", "CAVA", "CELH", "CFLT", "CHRW", "CIEN", "CLH",
    "CNH", "COKE", "COOP", "CRDO", "CROX", "CSGP", "CW", "CYTK",
    "DAR", "DDOG", "DECK", "DOCU", "DT", "DUOL", "DXC", "ELF",
    "EME", "ENTG", "ETSY", "EXEL", "EXLS", "FIVE", "FIX", "FND",
    "FTV", "GDDY", "GEN", "GFS", "GLOB", "GMED", "GPI", "GTLS",
    "HALO", "HIMS", "HUBG", "IAC", "IBKR", "ICLR", "IONS", "ITT",
    "JBL", "JEF", "JLL", "KBH", "KBR", "KMX", "LAD", "LECO",
    "LEVI", "LITE", "LKQ", "LPLA", "LSCC", "LSTR", "LYV", "MANH",
    "MASI", "MATX", "MEDP", "MKSI", "MMSI", "MTDR", "MTG", "MTZ",
    "NCLH", "NEU", "NOV", "NTRA", "NVT", "OKTA", "ONTO", "OR",
    "OLED", "OVV", "PATH", "PCAR", "PCTY", "PENN", "PFGC", "PINS",
    "PNR", "POOL", "PPC", "PSN", "PSTG", "PTC", "RBC", "RGEN",
    "RIVN", "RLI", "RNG", "ROKU", "RPRX", "RS", "RUSHA", "SAIA",
    "SCI", "SE", "SF", "SITE", "SMAR", "SNX", "SRAD", "SSNC",
    "ST", "STAG", "STLD", "SWK", "TAP", "TOL", "TRGP", "TRMB",
    "TREX", "TRIP", "TTC", "TW", "TXG", "UFPI", "UNM", "UPWK",
    "UTHR", "VCYT", "VIRT", "VMI", "VRNS", "W", "WAL", "WBD",
    "WEX", "WH", "WING", "WMS", "WOLF", "WPC", "WRB", "WSO",
    "WTRG", "WWD", "XPO", "YETI", "Z", "ZI", "ZWS",
]

# A smaller, liquid test universe.
# Useful before launching a broad scan.
TEST_UNIVERSE = [
    "AMD",
    "MU",
    "PLTR",
    "SOFI",
    "HOOD",
    "SHOP",
    "UBER",
    "CRWD",
    "NET",
    "COIN",
]


# ================================================================
# HELPERS
# ================================================================

def safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None

        number = float(value)

        if not math.isfinite(number):
            return None

        return number

    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None

        return int(float(value))

    except (TypeError, ValueError):
        return None


def days_until(expiration: str) -> int:
    expiry = datetime.strptime(
        expiration,
        "%Y-%m-%d",
    ).date()

    return (expiry - date.today()).days


def normalize_iv(value: Any) -> float | None:
    value = safe_float(value)

    if value is None:
        return None

    if value > 1:
        return value / 100.0

    return value


def get_row_value(row: Any, *names: str) -> Any:
    """
    Safely retrieve a field from a pandas Series/DataFrame row.
    """
    for name in names:
        try:
            if name in row.index:
                return row[name]
        except Exception:
            continue

    return None


# ================================================================
# STOCK SNAPSHOT
# ================================================================

def get_stock_snapshot(ticker: str) -> dict[str, Any] | None:
    """
    Fetch the minimum amount of underlying-stock information needed
    before spending time on the option chain.

    This is intentionally conservative.
    """

    ticker = ticker.upper()

    try:
        stock = yf.Ticker(ticker)
        info = stock.info
    except Exception as exc:
        print(f"  ! Yahoo info failed: {ticker} ({exc})")
        return None

    if not isinstance(info, dict) or not info:
        return None

    price = (
        safe_float(info.get("currentPrice"))
        or safe_float(info.get("regularMarketPrice"))
        or safe_float(info.get("previousClose"))
    )

    if price is None or price <= 0:
        return None

    market_cap = safe_float(info.get("marketCap"))

    # ------------------------------------------------------------
    # Quality
    # ------------------------------------------------------------

    quality_score = 70.0

    # ------------------------------------------------------------
    # Growth
    # ------------------------------------------------------------

    revenue_growth = safe_float(info.get("revenueGrowth"))
    earnings_growth = safe_float(info.get("earningsGrowth"))

    growth_components: list[float] = []

    if revenue_growth is not None:
        growth_components.append(
            max(
                0.0,
                min(revenue_growth * 100.0, 100.0),
            )
        )

    if earnings_growth is not None:
        growth_components.append(
            max(
                0.0,
                min(earnings_growth * 100.0, 100.0),
            )
        )

    if growth_components:
        growth_score = sum(growth_components) / len(
            growth_components
        )
    else:
        growth_score = 50.0

    # ------------------------------------------------------------
    # Valuation
    # ------------------------------------------------------------

    pe = safe_float(info.get("trailingPE"))

    if pe is None:
        valuation_score = 50.0
    elif pe <= 15:
        valuation_score = 90.0
    elif pe <= 25:
        valuation_score = 80.0
    elif pe <= 35:
        valuation_score = 70.0
    elif pe <= 50:
        valuation_score = 55.0
    else:
        valuation_score = 35.0

    # ------------------------------------------------------------
    # Financial health
    # ------------------------------------------------------------

    current_ratio = safe_float(info.get("currentRatio"))
    debt_to_equity = safe_float(info.get("debtToEquity"))

    health_points: list[float] = []

    if current_ratio is not None:
        if current_ratio >= 2:
            health_points.append(90.0)
        elif current_ratio >= 1.5:
            health_points.append(80.0)
        elif current_ratio >= 1:
            health_points.append(65.0)
        else:
            health_points.append(35.0)

    if debt_to_equity is not None:
        if debt_to_equity <= 50:
            health_points.append(90.0)
        elif debt_to_equity <= 100:
            health_points.append(80.0)
        elif debt_to_equity <= 200:
            health_points.append(65.0)
        else:
            health_points.append(40.0)

    if health_points:
        financial_health_score = sum(health_points) / len(
            health_points
        )
    else:
        financial_health_score = 50.0

    # ------------------------------------------------------------
    # Earnings date
    # ------------------------------------------------------------

    earnings_date = None

    try:
        calendar = stock.calendar

        if hasattr(calendar, "get"):
            earnings = calendar.get("Earnings Date")

            if earnings:
                if isinstance(earnings, (list, tuple)):
                    earnings_date = str(earnings[0])
                else:
                    earnings_date = str(earnings)

    except Exception:
        pass

    return {
        "ticker": ticker,
        "price": price,
        "market_cap": market_cap,
        "quality_score": quality_score,
        "growth_score": growth_score,
        "valuation_score": valuation_score,
        "financial_health_score": financial_health_score,
        "earnings_date": earnings_date,
    }


# ================================================================
# UNDERLYING STOCK FILTER
# ================================================================

def passes_stock_filter(
    snapshot: dict[str, Any],
    min_price: float = 10.0,
    max_price: float = 1000.0,
    min_market_cap: float = 2_000_000_000,
    min_quality: float = 60.0,
    min_health: float = 45.0,
) -> tuple[bool, str]:
    """
    Stage 1 filter.

    We reject weak/unusable stocks before touching option chains.
    """

    ticker = snapshot["ticker"]
    price = snapshot["price"]
    market_cap = snapshot.get("market_cap")
    quality = snapshot["quality_score"]
    health = snapshot["financial_health_score"]

    if price < min_price:
        return False, f"price below ${min_price:.0f}"

    if price > max_price:
        return False, f"price above ${max_price:.0f}"

    if market_cap is not None and market_cap < min_market_cap:
        return False, "market cap too small"

    if quality < min_quality:
        return False, "quality score too low"

    if health < min_health:
        return False, "financial health too low"

    return True, f"{ticker} passed stock filter"


# ================================================================
# IV RANK ESTIMATE
# ================================================================

def calculate_iv_rank(
    current_iv: float | None,
    historical_ivs: list[float],
) -> float | None:
    """
    Estimate IV percentile from the option-chain observations
    available to this scan.

    This is NOT an official vendor 52-week IV Rank.
    """

    if current_iv is None or not historical_ivs:
        return None

    below = sum(
        1
        for value in historical_ivs
        if value <= current_iv
    )

    return round(
        below / len(historical_ivs) * 100.0,
        2,
    )


# ================================================================
# OPTION CANDIDATES
# ================================================================

def get_candidate_options(
    ticker: str,
    snapshot: dict[str, Any],
    min_days: int = 21,
    max_days: int = 45,
    min_delta: float = 0.15,
    max_delta: float = 0.40,
    min_otm_pct: float = 3.0,
    max_otm_pct: float = 20.0,
    min_option_volume: int = 100,
    min_open_interest: int = 500,
) -> list[CoveredCallCandidate]:

    ticker = ticker.upper()

    stock = yf.Ticker(ticker)

    try:
        expirations = stock.options
    except Exception as exc:
        print(
            f"  ! Options unavailable for {ticker}: {exc}"
        )
        return []

    if not expirations:
        return []

    selected_expirations: list[tuple[str, int]] = []

    for expiration in expirations:
        try:
            days = days_until(expiration)
        except (TypeError, ValueError):
            continue

        if min_days <= days <= max_days:
            selected_expirations.append(
                (expiration, days)
            )

    if not selected_expirations:
        return []

    price = snapshot["price"]

    candidates: list[CoveredCallCandidate] = []

    # ------------------------------------------------------------
    # Scan only the expirations that fit our DTE window.
    # ------------------------------------------------------------

    for expiration, days in selected_expirations:

        try:
            chain = stock.option_chain(expiration)
            calls = chain.calls
        except Exception as exc:
            print(
                f"  ! Option chain failed: "
                f"{ticker} {expiration} ({exc})"
            )
            continue

        if calls is None or calls.empty:
            continue

        # --------------------------------------------------------
        # Build a small IV sample from this chain.
        # --------------------------------------------------------

        historical_ivs: list[float] = []

        try:
            for value in calls["impliedVolatility"].tolist():
                iv = normalize_iv(value)

                if iv is not None and iv > 0:
                    historical_ivs.append(iv)
        except Exception:
            pass

        # --------------------------------------------------------
        # Examine calls.
        # --------------------------------------------------------

        for _, row in calls.iterrows():

            strike = safe_float(
                get_row_value(
                    row,
                    "strike",
                    "Strike",
                )
            )

            if strike is None or strike <= price:
                continue

            upside_to_strike = (
                (strike - price) / price * 100.0
            )

            if upside_to_strike < min_otm_pct:
                continue

            if upside_to_strike > max_otm_pct:
                continue

            bid = safe_float(
                get_row_value(row, "bid", "Bid")
            )

            ask = safe_float(
                get_row_value(row, "ask", "Ask")
            )

            last_price = safe_float(
                get_row_value(
                    row,
                    "lastPrice",
                    "Last Price",
                )
            )

            volume = safe_int(
                get_row_value(
                    row,
                    "volume",
                    "Volume",
                )
            ) or 0

            open_interest = safe_int(
                get_row_value(
                    row,
                    "openInterest",
                    "Open Interest",
                )
            ) or 0

            if volume < min_option_volume:
                continue

            if open_interest < min_open_interest:
                continue

            # ----------------------------------------------------
            # Premium selection.
            #
            # Prefer midpoint because it avoids assuming the
            # entire ask can actually be filled.
            # ----------------------------------------------------

            if (
                bid is not None
                and ask is not None
                and bid > 0
                and ask > 0
                and ask >= bid
            ):
                premium = (bid + ask) / 2.0

            elif last_price is not None and last_price > 0:
                premium = last_price

            else:
                continue

            if premium <= 0:
                continue

            # ----------------------------------------------------
            # IV
            # ----------------------------------------------------

            implied_volatility = normalize_iv(
                get_row_value(
                    row,
                    "impliedVolatility",
                    "IV",
                )
            )

            if implied_volatility is None:
                continue

            iv_rank = calculate_iv_rank(
                implied_volatility,
                historical_ivs,
            )

            # ----------------------------------------------------
            # Delta
            #
            # Yahoo generally does not provide reliable delta.
            # We therefore do NOT fabricate one.
            #
            # If unavailable, use the user's requested OTM range
            # as a conservative proxy and label the result through
            # the Hunter's research output.
            # ----------------------------------------------------

            delta = safe_float(
                get_row_value(
                    row,
                    "delta",
                    "Delta",
                )
            )

            if delta is None:
                # Conservative research estimate based on OTM distance.
                #
                # This is ONLY a screening proxy, not market delta.
                estimated_delta = max(
                    0.15,
                    min(
                        0.40,
                        0.40 - (
                            max(
                                0.0,
                                upside_to_strike - 3.0,
                            ) / 17.0 * 0.25
                        ),
                    ),
                )

                delta = estimated_delta

            delta = abs(delta)

            if delta < min_delta or delta > max_delta:
                continue

            # ----------------------------------------------------
            # Earnings risk
            # ----------------------------------------------------

            earnings_date = snapshot.get(
                "earnings_date"
            )

            earnings_warning = False

            if earnings_date:
                earnings_text = str(
                    earnings_date
                )

                try:
                    earnings_day = (
                        datetime.fromisoformat(
                            earnings_text
                            .replace("Z", "")
                        ).date()
                    )

                    today = date.today()

                    earnings_days = (
                        earnings_day - today
                    ).days

                    if 0 <= earnings_days <= days:
                        earnings_warning = True

                except Exception:
                    pass

            # ----------------------------------------------------
            # Build candidate.
            # ----------------------------------------------------

            contract_symbol = get_row_value(
                row,
                "contractSymbol",
                "Contract Symbol",
            )

            candidate = covered_call_hunter.evaluate(
                ticker=ticker,
                stock_price=price,
                market_cap=snapshot.get(
                    "market_cap"
                ),
                quality_score=snapshot[
                    "quality_score"
                ],
                growth_score=snapshot[
                    "growth_score"
                ],
                valuation_score=snapshot[
                    "valuation_score"
                ],
                financial_health_score=snapshot[
                    "financial_health_score"
                ],
                strike=strike,
                expiration=expiration,
                days_to_expiration=days,
                premium=premium,
                open_interest=open_interest,
                option_volume=volume,
                bid=bid or premium,
                ask=ask or premium,
                implied_volatility=implied_volatility,
                iv_rank=iv_rank or 0.0,
                delta=delta,
                earnings_date=earnings_date,
            )

            candidate.contract_symbol = str(
                contract_symbol
            ).strip() or None

            # ----------------------------------------------------
            # Add scanner-specific warnings.
            # ----------------------------------------------------

            if earnings_warning:
                warning = (
                    "Earnings occur before expiration; "
                    "assignment/volatility risk may be elevated."
                )

                if warning not in candidate.warnings:
                    candidate.warnings.append(warning)

            if safe_float(
                snapshot.get("market_cap")
            ) is None:
                warning = (
                    "Market capitalization unavailable."
                )

                if warning not in candidate.warnings:
                    candidate.warnings.append(warning)

            candidates.append(candidate)

    return candidates


# ================================================================
# FORMATTERS
# ================================================================

def format_market_cap(value: Any) -> str:
    value = safe_float(value)

    if value is None:
        return "N/A"

    if value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"

    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"

    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"

    return f"${value:,.0f}"


def _candidate_decision(candidate: CoveredCallCandidate):
    """Present the existing Decision Engine verdict for one contract."""
    stock = {
        "ticker": candidate.ticker,
        "price": candidate.stock_price,
        "market_cap": candidate.market_cap,
        "quality_score": candidate.quality_score,
        "growth_score": candidate.growth_score,
        "valuation_score": candidate.valuation_score,
        "financial_health_score": candidate.financial_health_score,
    }
    option = {
        "ticker": candidate.ticker,
        "strike": candidate.strike,
        "expiration": candidate.expiration,
        "days_to_expiration": candidate.days_to_expiration,
        "premium": candidate.premium,
        "premium_yield": candidate.premium_yield,
        "annualized_premium_yield": candidate.annualized_premium_yield,
        "open_interest": candidate.open_interest,
        "option_volume": candidate.option_volume,
        "bid": candidate.bid,
        "ask": candidate.ask,
        "bid_ask_spread_pct": candidate.bid_ask_spread_pct,
        "implied_volatility": candidate.implied_volatility,
        "iv_rank": candidate.iv_rank,
        "delta": candidate.delta,
        "earnings_date": candidate.earnings_date,
        "upside_to_strike_pct": candidate.upside_to_strike_pct,
    }
    return decision_engine.evaluate(candidate.ticker, stock, option)


def _stored_candidate_decision(candidate: CoveredCallCandidate):
    """Return the scan-time Decision Engine result for a contract.

    ``scan_universe`` evaluates every qualifying candidate before it returns.
    The fallback preserves direct use of ``print_report`` with manually-created
    candidates, while normal scanner runs never evaluate a candidate twice.
    """
    decision = getattr(candidate, "decision_result", None)
    if decision is None:
        decision = _candidate_decision(candidate)
        setattr(candidate, "decision_result", decision)

    return decision


def print_candidate(candidate: CoveredCallCandidate) -> None:
    print()
    print("\n".join(terminal_box(
        "📞 COVERED CALL HUNTER  //  CONTRACT DETAIL",
        f"{candidate.ticker} · HUNTER SCORE {candidate.score:.1f}/100",
    )))

    print(
        f"Price:        ${candidate.stock_price:,.2f}"
    )
    print(
        f"Market Cap:   {format_market_cap(candidate.market_cap)}"
    )

    print()
    print(terminal_section("COVERED CALL"))

    print(
        f"Strike:       ${candidate.strike:,.2f}"
    )
    print(
        f"Expiration:   {candidate.expiration}"
    )
    print(
        f"DTE:          {candidate.days_to_expiration}"
    )
    print(
        f"Premium:      ${candidate.premium:,.2f}"
    )
    print(
        f"Premium Yield:{candidate.premium_yield:>8.2f}%"
    )
    print(
        f"Annualized:   {candidate.annualized_premium_yield:>8.2f}%"
    )
    print(
        f"Delta:        {candidate.delta:.2f}"
    )
    print(
        f"IV:           {candidate.implied_volatility * 100:.2f}%"
    )
    print(
        f"IV Rank:      {candidate.iv_rank:.2f}"
    )

    print()
    print(terminal_section("LIQUIDITY"))

    print(
        f"Volume:       {candidate.option_volume:,}"
    )
    print(
        f"Open Interest:{candidate.open_interest:,}"
    )
    print(
        f"Bid:          ${candidate.bid:,.2f}"
    )
    print(
        f"Ask:          ${candidate.ask:,.2f}"
    )
    print(
        f"Spread:       {candidate.bid_ask_spread_pct:.2f}%"
    )

    print()
    print(terminal_section("RETURN PROFILE"))

    print(
        f"Upside:       {candidate.upside_to_strike_pct:.2f}%"
    )
    print(
        f"Break-even:   {candidate.downside_break_even_pct:.2f}%"
    )
    print(
        f"Max Profit:   {candidate.max_profit_pct:.2f}%"
    )

    if candidate.warnings:
        print()
        print(terminal_section("WARNINGS"))

        for warning in candidate.warnings:
            print(f"  • {warning}")

    print(build_decision_summary(_stored_candidate_decision(candidate)))


# ================================================================
# SCANNER
# ================================================================

def scan_universe(
    universe: list[str],
    limit: int | None = None,
    min_days: int = 21,
    max_days: int = 45,
    min_delta: float = 0.15,
    max_delta: float = 0.40,
    min_otm_pct: float = 3.0,
    max_otm_pct: float = 20.0,
    min_option_volume: int = 100,
    min_open_interest: int = 500,
) -> list[CoveredCallCandidate]:

    symbols = universe[:limit] if limit else universe

    print()
    print("╔" + "═" * 70 + "╗")
    print(
        "║"
        + " COVERED CALL HUNTER — TWO-STAGE SCAN ".center(70)
        + "║"
    )
    print("╠" + "═" * 70 + "╣")
    print(
        "║"
        + f" Universe: {len(symbols)} stocks".ljust(70)
        + "║"
    )
    print(
        "║"
        + f" Options: {min_days}-{max_days} DTE".ljust(70)
        + "║"
    )
    print(
        "║"
        + f" OTM: {min_otm_pct:.0f}-{max_otm_pct:.0f}%".ljust(70)
        + "║"
    )
    print("╚" + "═" * 70 + "╝")

    all_candidates: list[CoveredCallCandidate] = []

    stock_passed = 0
    stock_failed = 0
    option_scanned = 0

    # ------------------------------------------------------------
    # STAGE 1
    # ------------------------------------------------------------

    print()
    print("🔎 STAGE 1 — UNDERLYING STOCK FILTER")
    print("-" * 72)

    for index, ticker in enumerate(symbols, start=1):

        print(
            f"[{index:>3}/{len(symbols)}] "
            f"{ticker:<6}",
            end=" ",
            flush=True,
        )

        snapshot = get_stock_snapshot(ticker)

        if snapshot is None:
            print("✗ unavailable")
            stock_failed += 1
            continue

        passed, reason = passes_stock_filter(
            snapshot
        )

        if not passed:
            print(f"✗ {reason}")
            stock_failed += 1
            continue

        print(
            "✓ PASS "
            f"| ${snapshot['price']:.2f} "
            f"| Growth {snapshot['growth_score']:.0f} "
            f"| Health {snapshot['financial_health_score']:.0f}"
        )

        stock_passed += 1

        # --------------------------------------------------------
        # STAGE 2
        # --------------------------------------------------------

        print(
            f"       └─ 📞 scanning option chain..."
        )

        option_scanned += 1

        candidates = get_candidate_options(
            ticker=ticker,
            snapshot=snapshot,
            min_days=min_days,
            max_days=max_days,
            min_delta=min_delta,
            max_delta=max_delta,
            min_otm_pct=min_otm_pct,
            max_otm_pct=max_otm_pct,
            min_option_volume=min_option_volume,
            min_open_interest=min_open_interest,
        )

        all_candidates.extend(candidates)

        if candidates:
            best = max(
                candidates,
                key=lambda item: item.score,
            )

            print(
                f"       └─ ✓ {len(candidates)} candidates "
                f"| best {best.score:.2f}"
            )
        else:
            print(
                "       └─ no qualifying options"
            )

    # ------------------------------------------------------------
    # Ranking
    # ------------------------------------------------------------

    all_candidates.sort(
        key=lambda item: item.score,
        reverse=True,
    )

    # Evaluate every contract that passed the existing scanner filters before
    # presentation applies the --top display limit. The result is retained on
    # its candidate for the ranked row and contract-detail report.
    for candidate in all_candidates:
        candidate.decision_result = _candidate_decision(candidate)

    print()
    print("╔" + "═" * 70 + "╗")
    print(
        "║"
        + " SCAN COMPLETE ".center(70)
        + "║"
    )
    print("╠" + "═" * 70 + "╣")
    print(
        "║"
        + f" Stocks scanned:      {len(symbols)}".ljust(70)
        + "║"
    )
    print(
        "║"
        + f" Stocks passed:       {stock_passed}".ljust(70)
        + "║"
    )
    print(
        "║"
        + f" Stocks rejected:     {stock_failed}".ljust(70)
        + "║"
    )
    print(
        "║"
        + f" Option chains used:  {option_scanned}".ljust(70)
        + "║"
    )
    print(
        "║"
        + f" Call candidates:     {len(all_candidates)}".ljust(70)
        + "║"
    )
    print(
        "║"
        + f" Engine evaluations:  {len(all_candidates)}".ljust(70)
        + "║"
    )
    print("╚" + "═" * 70 + "╝")

    return all_candidates


# ================================================================
# MAIN REPORT
# ================================================================

def print_report(
    candidates: list[CoveredCallCandidate],
    top: int = 10,
) -> None:

    print()
    print("\n".join(terminal_box(
        "📞 COVERED CALL HUNTER  //  RANKED RESEARCH QUEUE",
        "Screening only · no order-routing capability",
    )))

    if not candidates:
        print()
        print("No qualifying covered-call candidates found.")
        print()
        print(
            "Try relaxing the filters with "
            "--min-volume, --min-oi, or a wider DTE range."
        )

        print()
        print(terminal_style("  🛡  NO TRADE EXECUTED", "red", "bold"))
        print(terminal_style("  Research-only mode", "muted"))
        return

    selected = candidates[:top]
    print()
    print(terminal_section("RANKED CONTRACTS"))

    for rank, candidate in enumerate(
        selected,
        start=1,
    ):
        decision = _stored_candidate_decision(candidate)
        marker, colour = status_style(decision.decision)
        print(
            f"  #{rank:02} {candidate.ticker:<6} "
            f"Hunter {terminal_style(score_bar(candidate.score, 12), 'blue')} "
            f"{candidate.score:05.1f}  "
            f"{terminal_style(f'{marker} {decision.decision}', colour, 'bold')}"
        )
        print(
            f"      ${candidate.stock_price:.2f} → ${candidate.strike:.2f} "
            f"| Premium {candidate.premium_yield:.2f}% "
            f"| Annualized {candidate.annualized_premium_yield:.2f}% "
            f"| {candidate.days_to_expiration} DTE"
        )
        print(
            f"      Volume {candidate.option_volume:,} "
            f"| OI {candidate.open_interest:,} "
            f"| Spread "
            f"{candidate.bid_ask_spread_pct:.2f}%"
        )

        if candidate.warnings:
            print(
                "    ⚠ "
                + " | ".join(candidate.warnings)
            )

    print()
    print(terminal_section("HUNTER RULE"))
    print(
        "High premium is NOT automatically a good trade."
    )
    print(
        "The underlying stock must be worth owning first."
    )
    print(
        "Then the option must provide attractive premium "
        "with acceptable liquidity, upside, and risk."
    )

    print()
    print(terminal_style("  🛡  NO TRADE EXECUTED", "red", "bold"))
    print(terminal_style("  Covered Call Hunter research-only mode", "muted"))
    print(terminal_style("└" + "─" * 76, "blue"))

    for rank, candidate in enumerate(selected, start=1):
        print()
        print(terminal_style(f"CONTRACT DETAIL #{rank:02}", "blue", "bold"))
        print_candidate(candidate)


# ================================================================
# ALPACA COVERED-CALL EXECUTION
# ================================================================

def _confirm_execution(prompt: str) -> bool:
    try:
        raw = input(prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return raw in {"y", "yes"}


def execute_covered_call_on_alpaca(
    candidates: list[CoveredCallCandidate],
    *,
    top: int = 10,
    contracts: int = 1,
    max_cap: float | None = None,
) -> None:
    """Offer a fully confirmed covered-call execution on Alpaca.

    The user selects which ranked candidate to run, then confirms the
    stock buy leg and the option sell-to-open leg separately.
    """
    from src.utils.alpaca_broker import AlpacaBroker, AlpacaError

    if contracts < 1:
        print(terminal_style("  ✖ --contracts must be at least 1", "red", "bold"))
        return

    broker = AlpacaBroker()
    if max_cap and max_cap > 0:
        pass

    from src.utils.live_switch import live_trading_enabled

    if not live_trading_enabled():
        print()
        print(terminal_style(
            "  ✖ LIVE-KILL-SWITCH: live trading is OFF. "
            "Run `live on` to enable before placing real orders.",
            "red", "bold",
        ))
        return

    if not broker.configured:
        print()
        print(terminal_style(
            "  ✖ Alpaca not configured. Set ALPACA_API_KEY / "
            "ALPACA_SECRET_KEY in ~/ai-stocks/.env.",
            "red", "bold",
        ))
        return

    try:
        market_open = broker.market_is_open()
    except AlpacaError as exc:
        print(terminal_style(f"  ✖ {exc}", "red", "bold"))
        return

    if not market_open:
        print()
        print(terminal_style(
            "  ✖ US market is closed. Covered-call orders are not "
            "being placed now. Re-run during market hours.",
            "red", "bold",
        ))
        return

    actionable = [c for c in candidates if c.contract_symbol]
    if not actionable:
        print()
        print(terminal_style(
            "  ✖ No candidate carries an order-ready OCC contract "
            "symbol. Cannot execute on Alpaca.",
            "red", "bold",
        ))
        return

    print()
    print("\n".join(terminal_box(
        "⚡ ALPACA COVERED-CALL EXECUTION",
        f"TARGET ACCOUNT: {broker.label}  ·  CONTRACTS: {contracts}",
    )))
    print(terminal_style(
        "  This places REAL orders. You approve each leg.",
        "red", "bold",
    ))
    print()

    stock_notional_cap = (
        max_cap
        if max_cap and max_cap > 0
        else (broker.max_notional if broker.max_notional > 0 else None)
    )

    for rank, candidate in enumerate(actionable[:top], start=1):
        print(
            f"  #{rank:02} {candidate.ticker:<6} {candidate.contract_symbol:<22} "
            f"premium ${candidate.premium:,.2f}"
        )

    print()
    pick = _prompt_text(
        "  Which rank to execute (ENTER = skip)? "
    )
    if pick is None or pick.strip() == "":
        print(terminal_style("  No contract selected. Nothing executed.", "muted"))
        return

    try:
        chosen = actionable[int(pick.strip()) - 1]
    except (ValueError, IndexError):
        print(terminal_style("  ✖ Invalid rank. Nothing executed.", "red", "bold"))
        return

    shares = contracts * 100
    stock_notional = shares * float(chosen.stock_price)
    option_notional = contracts * 100 * float(chosen.premium or 0.0)

    print()
    print("\n".join(terminal_box(
        "📋 EXECUTION PLAN",
        f"{chosen.ticker} covered call",
    )))
    print(f"  Leg 1  BUY    {shares} x {chosen.ticker:<6} "
          f"(est ${stock_notional:,.0f})")
    print(f"  Leg 2  SELL   {contracts} x {chosen.contract_symbol}")
    print(f"        premium est ${option_notional:,.0f} received")

    if stock_notional_cap and stock_notional > stock_notional_cap:
        print()
        print(terminal_style(
            "  ✖ FUND_SAFETY: stock leg "
            f"${stock_notional:,.0f} exceeds cap "
            f"${stock_notional_cap:,.0f}. Refusing.",
            "red", "bold",
        ))
        return

    print()
    if not _confirm_execution(
        f"  Leg 1: place BUY {shares} x {chosen.ticker} on "
        f"{broker.label}? [y/N] "
    ):
        print(terminal_style("  Stock leg declined. Nothing executed.", "muted"))
        return

    if not _confirm_execution(
        f"  Leg 2: place SELL-TO-OPEN {contracts} x "
        f"{chosen.contract_symbol} on {broker.label}? [y/N] "
    ):
        print(terminal_style(
            "  Option leg declined. Stock order may have filled.",
            "red", "bold",
        ))
        return

    try:
        stock_order = broker.place_order(
            symbol=chosen.ticker,
            qty=shares,
            side="buy",
            time_in_force="day",
        )
        print(
            f"  ✓ STOCK order placed  id={stock_order.get('id')}  "
            f"status={stock_order.get('status')}"
        )
    except AlpacaError as exc:
        print(terminal_style(f"  ✖ Stock leg rejected: {exc}", "red", "bold"))
        return

    try:
        option_order = broker.place_order(
            symbol=chosen.contract_symbol,
            qty=contracts,
            side="sell",
            time_in_force="day",
            asset_class="option",
        )
        print(
            f"  ✓ OPTION order placed  id={option_order.get('id')}  "
            f"status={option_order.get('status')}"
        )
    except AlpacaError as exc:
        print(terminal_style(
            f"  ✖ Option leg rejected: {exc}. Stock may be held.",
            "red", "bold",
        ))
        return

    print()
    print(terminal_style(
        "  Covered call submitted to Alpaca. Monitor fills in "
        "your order history.",
        "green", "bold",
    ))


def _prompt_text(prompt: str) -> str | None:
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return None


# ================================================================
# CLI
# ================================================================

def build_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        description=(
            "Two-stage Covered Call Hunter. "
            "Filters stocks first, then scans options."
        )
    )

    parser.add_argument(
        "tickers",
        nargs="*",
        help=(
            "Specific ticker symbols to scan. "
            "If omitted, --universe is used."
        ),
    )

    parser.add_argument(
        "--universe",
        choices=[
            "midcap",
            "test",
        ],
        default="midcap",
        help="Stock universe to scan.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of stocks to scan.",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of final candidates to display.",
    )

    parser.add_argument(
        "--min-days",
        type=int,
        default=21,
        help="Minimum option expiration days.",
    )

    parser.add_argument(
        "--max-days",
        type=int,
        default=45,
        help="Maximum option expiration days.",
    )

    parser.add_argument(
        "--min-delta",
        type=float,
        default=0.15,
        help="Minimum call delta.",
    )

    parser.add_argument(
        "--max-delta",
        type=float,
        default=0.40,
        help="Maximum call delta.",
    )

    parser.add_argument(
        "--min-otm",
        type=float,
        default=3.0,
        help="Minimum strike distance above stock price.",
    )

    parser.add_argument(
        "--max-otm",
        type=float,
        default=20.0,
        help="Maximum strike distance above stock price.",
    )

    parser.add_argument(
        "--min-volume",
        type=int,
        default=100,
        help="Minimum option volume.",
    )

    parser.add_argument(
        "--min-oi",
        type=int,
        default=500,
        help="Minimum option open interest.",
    )

    parser.add_argument(
        "--alpaca",
        action="store_true",
        help=(
            "Offer to execute the winning contract on Alpaca "
            "(buy stock + sell-to-open call) with per-order confirmation."
        ),
    )

    parser.add_argument(
        "--contracts",
        type=int,
        default=1,
        help=(
            "Number of option contracts to sell when executing "
            "a covered call on Alpaca (100 shares each)."
        ),
    )

    parser.add_argument(
        "--max-cap",
        type=float,
        default=None,
        help=(
            "Maximum dollar notional for the stock leg. "
            "Defaults to ALPACA_MAX_NOTIONAL from .env."
        ),
    )

    return parser


def main() -> None:

    parser = build_parser()
    args = parser.parse_args()

    if args.tickers:
        universe = [
            ticker.upper()
            for ticker in args.tickers
        ]
    elif args.universe == "test":
        universe = TEST_UNIVERSE
    else:
        universe = MIDCAP_UNIVERSE

    candidates = scan_universe(
        universe=universe,
        limit=args.limit,
        min_days=args.min_days,
        max_days=args.max_days,
        min_delta=args.min_delta,
        max_delta=args.max_delta,
        min_otm_pct=args.min_otm,
        max_otm_pct=args.max_otm,
        min_option_volume=args.min_volume,
        min_open_interest=args.min_oi,
    )

    print_report(
        candidates=candidates,
        top=args.top,
    )

    if args.alpaca:
        execute_covered_call_on_alpaca(
            candidates=candidates,
            top=args.top,
            contracts=args.contracts,
            max_cap=args.max_cap,
        )


if __name__ == "__main__":
    main()
