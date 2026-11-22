#!/usr/bin/env python3

"""
MEGATRON // SOLANA CROSS-VENUE ARBITRAGE ENGINE

LIVE MARKET DATA: YES
LIVE TRADING: GATED
WALLET: NOT CONNECTED
REAL TRANSACTIONS: DISABLED

Research / paper-mode only.

The scanner:
    USDC -> SOL   BUY
    SOL  -> USDC  SELL

It uses fresh Jupiter executable quotes and calculates the
actual round-trip result.

IMPORTANT:
    This program does NOT:
    - connect to a wallet
    - create transactions
    - sign transactions
    - broadcast transactions
    - move real funds
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import time
import uuid

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# ================================================================
# SAFETY
# ================================================================

LIVE_TRADING_ENABLED = False
WALLET_CONNECTED = False
REAL_TRANSACTIONS_ENABLED = False


# ================================================================
# DEFAULT SETTINGS
# ================================================================

DEFAULT_SCAN_INTERVAL = 5.0
DEFAULT_TIMEOUT = 10.0

# Jupiter rate-limit protection
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 2.0

# Small delay between Jupiter requests.
# This helps reduce HTTP 429 responses.
DEFAULT_REQUEST_DELAY = 1.0

# PHASE 2B // request-manager protection.
# After a 429, all subsequent Jupiter requests observe a cooldown.
DEFAULT_429_COOLDOWN_SECONDS = 8.0

# PHASE 2B // only verify the strongest BUY candidates.
# With three venues this reduces the SELL-request fan-out from
# 6 requests to 4 while still checking the top two BUY routes.
DEFAULT_MAX_BUY_CANDIDATES = 2

# PHASE 2C // request timing state.
JUPITER_LAST_REQUEST_TIME = 0.0
JUPITER_COOLDOWN_UNTIL = 0.0

# Research sizes only.
DEFAULT_USDC_AMOUNT = 10.00

DEFAULT_SIZES = [
    10.0,
    25.0,
    50.0,
    100.0,
    500.0,
]

DEFAULT_SLIPPAGE_BPS = 50

DEFAULT_MAX_PRICE_IMPACT_PCT = 1.00

DEFAULT_MIN_NET_EDGE_PCT = 0.20
DEFAULT_STRONG_EDGE_PCT = 0.50

DEFAULT_COST_RESERVE_USDC = 0.02

# Live-trading safety gate (execution is intentionally unavailable in this scanner).
DEFAULT_MAX_TRADE_USDC = 25.0
DEFAULT_MAX_DAILY_LOSS_USDC = 5.0

DEFAULT_VENUES = [
    "Raydium",
    "Orca V2",
    "Meteora DLMM",
]


# ================================================================
# JUPITER
# ================================================================

JUPITER_QUOTE_URL = (
    "https://api.jup.ag/swap/v1/quote"
)

SOL_MINT = (
    "So11111111111111111111111111111111111111112"
)

USDC_MINT = (
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
)


# ================================================================
# FILES
# ================================================================

BASE_DIR = Path(__file__).resolve().parent

ENV_FILE = BASE_DIR / ".env"

QUOTE_LOG = BASE_DIR / "live_quotes.csv"

OPPORTUNITY_LOG = (
    BASE_DIR / "arbitrage_opportunities.csv"
)


# ================================================================
# RUNTIME
# ================================================================

RUNNING = True

# ================================================================
# PHASE 2B // JUPITER REQUEST MANAGER
# ================================================================

# These are monotonic timestamps, not wall-clock timestamps.
# They exist only to coordinate requests inside this process.
LAST_JUPITER_REQUEST_AT = 0.0
JUPITER_COOLDOWN_UNTIL = 0.0


def wait_for_jupiter_slot(request_delay: float) -> None:
    """Wait until the next Jupiter request is allowed.

    This is the single request-spacing gate for the scanner.
    It is interruptible so Ctrl+C can stop the engine immediately.
    """
    global RUNNING, JUPITER_LAST_REQUEST_TIME, JUPITER_COOLDOWN_UNTIL
    global LAST_JUPITER_REQUEST_AT
    global JUPITER_COOLDOWN_UNTIL

    while RUNNING:
        now = time.monotonic()
        next_allowed = max(
            LAST_JUPITER_REQUEST_AT + max(0.0, request_delay),
            JUPITER_COOLDOWN_UNTIL,
        )
        remaining = next_allowed - now

        if remaining <= 0:
            return

        time.sleep(min(0.1, remaining))

    raise InterruptedError(
        "MEGATRON scan stopped by user."
    )


def mark_jupiter_request() -> None:
    """Record the moment an HTTP request is about to be sent."""
    global LAST_JUPITER_REQUEST_AT
    LAST_JUPITER_REQUEST_AT = time.monotonic()


def set_jupiter_cooldown(seconds: float) -> None:
    """Extend the global Jupiter cooldown without shortening it."""
    global JUPITER_COOLDOWN_UNTIL
    JUPITER_COOLDOWN_UNTIL = max(
        JUPITER_COOLDOWN_UNTIL,
        time.monotonic() + max(0.0, seconds),
    )


# ================================================================
# MEGATRON // NEON ORANGE TERMINAL THEME
# ================================================================
RESET = "\033[0m"
BOLD = "\033[1m"
ORANGE = "\033[38;5;208m"
BRIGHT_ORANGE = "\033[38;5;214m"
GREEN = "\033[38;5;118m"
RED = "\033[38;5;196m"
YELLOW = "\033[38;5;226m"
CYAN = "\033[38;5;51m"
WHITE = "\033[97m"
GRAY = "\033[38;5;245m"

def ui(text: object, color: str = WHITE, bold: bool = False) -> str:
    return f"{BOLD if bold else ''}{color}{text}{RESET}"

def edge_ui(value: float) -> str:
    return ui(f"{value:+.4f}%", GREEN if value >= 0 else RED, True)

def money_ui(value: float) -> str:
    return ui(f"${value:+.6f}", GREEN if value >= 0 else RED, True)



def stop_engine(signum, frame) -> None:
    global RUNNING

    RUNNING = False

    print()
    print("🛑 STOP REQUEST RECEIVED")


signal.signal(signal.SIGINT, stop_engine)


# ================================================================
# DATA MODELS
# ================================================================

@dataclass
class VenueQuote:
    venue: str
    direction: str
    quote_id: str

    input_mint: str
    output_mint: str

    input_amount: int
    output_amount: int

    price_impact_pct: float

    route_labels: list[str]

    timestamp: str

    raw: dict

    @property
    def input_decimals(self) -> int:
        if self.input_mint == USDC_MINT:
            return 6

        return 9

    @property
    def output_decimals(self) -> int:
        if self.output_mint == USDC_MINT:
            return 6

        return 9

    @property
    def input_human(self) -> float:
        return self.input_amount / (
            10 ** self.input_decimals
        )

    @property
    def output_human(self) -> float:
        return self.output_amount / (
            10 ** self.output_decimals
        )


@dataclass
class ArbitrageOpportunity:
    opportunity_id: str

    buy_venue: str
    sell_venue: str

    buy_quote: VenueQuote
    sell_quote: VenueQuote

    starting_usdc: float
    sol_received: float
    ending_usdc: float

    gross_profit_usdc: float
    gross_edge_pct: float

    cost_reserve_usdc: float

    net_profit_usdc: float
    net_edge_pct: float

    timestamp: str


# ================================================================
# ENVIRONMENT
# ================================================================

def load_dotenv_file() -> None:
    """
    Load simple KEY=VALUE entries from .env.

    Existing shell variables always win.
    """

    if not ENV_FILE.exists():
        return

    for raw_line in ENV_FILE.read_text(
        encoding="utf-8"
    ).splitlines():

        line = raw_line.strip()

        if (
            not line
            or line.startswith("#")
            or "=" not in line
        ):
            continue

        key, value = line.split("=", 1)

        key = key.strip()
        value = value.strip()

        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]

        os.environ.setdefault(key, value)


def load_api_key() -> str:
    load_dotenv_file()

    key = os.environ.get(
        "JUPITER_API_KEY",
        "",
    ).strip()

    if not key:
        raise RuntimeError(
            "JUPITER_API_KEY is missing. "
            f"Create {ENV_FILE} with "
            "JUPITER_API_KEY=YOUR_KEY"
        )

    return key


# ================================================================
# HTTP / JUPITER RATE LIMIT PROTECTION
# ================================================================

def http_get_json(
    url: str,
    api_key: str,
    timeout: float,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    request_delay: float = DEFAULT_REQUEST_DELAY,
) -> dict:

    global RUNNING

    last_error: Exception | None = None

    for attempt in range(max_retries + 1):

        # Stop immediately if the user requested shutdown.
        if not RUNNING:
            raise InterruptedError(
                "MEGATRON scan stopped by user."
            )

        # PHASE 2B: one centralized spacing/cooldown gate.
        wait_for_jupiter_slot(request_delay)
        mark_jupiter_request()

        request = Request(
            url,
            headers={
                "x-api-key": api_key,
                "User-Agent": (
                    "MEGATRON-Solana-Arbitrage-Research/4.0"
                ),
                "Accept": "application/json",
            },
            method="GET",
        )

        try:

            with urlopen(
                request,
                timeout=timeout,
            ) as response:

                body = (
                    response
                    .read()
                    .decode("utf-8")
                )

                if response.status != 200:
                    raise RuntimeError(
                        f"HTTP {response.status}: "
                        f"{body[:300]}"
                    )

                try:
                    return json.loads(body)

                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        "Invalid JSON returned by Jupiter."
                    ) from exc

        except HTTPError as exc:

            last_error = exc

            try:
                body = (
                    exc
                    .read()
                    .decode("utf-8")
                )
            except Exception:
                body = ""

            detail = (
                body[:400]
                .replace("\n", " ")
            )

            # ----------------------------------------------------
            # HTTP 429
            # ----------------------------------------------------

            if exc.code == 429:

                if attempt < max_retries:

                    delay = (
                        backoff_seconds
                        * (2 ** attempt)
                    )

                    # Honor Retry-After when Jupiter supplies it,
                    # but never use a shorter cooldown than our
                    # configured Phase 2B safety floor.
                    retry_after = 0.0
                    try:
                        retry_after = float(
                            exc.headers.get("Retry-After", "0")
                        )
                    except (AttributeError, TypeError, ValueError):
                        retry_after = 0.0

                    cooldown = max(
                        delay,
                        retry_after,
                        DEFAULT_429_COOLDOWN_SECONDS,
                    )
                    set_jupiter_cooldown(cooldown)

                    print(
                        f"│   ⚠ Jupiter rate limit (429). "
                        f"Retry {attempt + 1}/"
                        f"{max_retries} "
                        f"in {cooldown:g}s..."
                    )

                    # Do not sleep here. The centralized request
                    # manager owns all waiting, so every future
                    # request observes the same cooldown.
                    continue

                raise RuntimeError(
                    "HTTP 429 rate limited by Jupiter "
                    f"after {max_retries} retries."
                ) from exc

            raise RuntimeError(
                f"Jupiter HTTP {exc.code}: "
                f"{exc.reason}"
                + (
                    f" | {detail}"
                    if detail
                    else ""
                )
            ) from exc

        except URLError as exc:

            if not RUNNING:
                raise InterruptedError(
                    "MEGATRON scan stopped by user."
                )

            raise RuntimeError(
                f"Connection error: {exc.reason}"
            ) from exc

        except TimeoutError as exc:

            if not RUNNING:
                raise InterruptedError(
                    "MEGATRON scan stopped by user."
                )

            raise RuntimeError(
                "Jupiter request timed out."
            ) from exc

    raise RuntimeError(
        "Jupiter request failed."
        + (
            f" | {last_error}"
            if last_error
            else ""
        )
    )


# ================================================================
# JUPITER QUOTES
# ================================================================

def get_quote(
    venue: str,
    direction: str,
    amount: int,
    slippage_bps: int,
    timeout: float,
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    request_delay: float = DEFAULT_REQUEST_DELAY,
) -> VenueQuote:

    api_key = load_api_key()

    if direction == "BUY":

        input_mint = USDC_MINT
        output_mint = SOL_MINT

    elif direction == "SELL":

        input_mint = SOL_MINT
        output_mint = USDC_MINT

    else:
        raise ValueError(
            f"Unknown direction: {direction}"
        )

    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": str(slippage_bps),
        "dexes": venue,
        "restrictIntermediateTokens": "true",
    }

    url = (
        JUPITER_QUOTE_URL
        + "?"
        + urlencode(params)
    )

    data = http_get_json(
        url=url,
        api_key=api_key,
        timeout=timeout,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
        request_delay=request_delay,
    )

    if data.get("error"):
        raise RuntimeError(
            str(data["error"])
        )

    if "outAmount" not in data:
        raise RuntimeError(
            f"No {direction.lower()} quote "
            f"available for {venue}."
        )

    route_labels: list[str] = []

    for route in data.get(
        "routePlan",
        [],
    ):

        swap_info = route.get(
            "swapInfo",
            {}
        )

        label = swap_info.get("label")

        if label:
            route_labels.append(
                str(label)
            )

    return VenueQuote(
        venue=venue,
        direction=direction,
        quote_id=str(uuid.uuid4())[:8],
        input_mint=input_mint,
        output_mint=output_mint,
        input_amount=int(
            data["inAmount"]
        ),
        output_amount=int(
            data["outAmount"]
        ),
        price_impact_pct=float(
            data.get(
                "priceImpactPct"
            )
            or 0.0
        ),
        route_labels=route_labels,
        timestamp=datetime.now(
            timezone.utc
        ).isoformat(),
        raw=data,
    )


# ================================================================
# LOGGING
# ================================================================

def initialize_logs() -> None:

    if not QUOTE_LOG.exists():

        with QUOTE_LOG.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as handle:

            writer = csv.writer(handle)

            writer.writerow([
                "timestamp",
                "venue",
                "direction",
                "quote_id",
                "input_amount",
                "output_amount",
                "price_impact_pct",
                "route",
            ])

    if not OPPORTUNITY_LOG.exists():

        with OPPORTUNITY_LOG.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as handle:

            writer = csv.writer(handle)

            writer.writerow([
                "timestamp",
                "opportunity_id",
                "buy_venue",
                "sell_venue",
                "starting_usdc",
                "sol_received",
                "ending_usdc",
                "gross_profit_usdc",
                "gross_edge_pct",
                "cost_reserve_usdc",
                "net_profit_usdc",
                "net_edge_pct",
                "buy_impact_pct",
                "sell_impact_pct",
                "buy_route",
                "sell_route",
            ])


def log_quote(
    quote: VenueQuote,
) -> None:

    with QUOTE_LOG.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.writer(handle)

        writer.writerow([
            quote.timestamp,
            quote.venue,
            quote.direction,
            quote.quote_id,
            quote.input_human,
            quote.output_human,
            f"{quote.price_impact_pct:.6f}",
            "|".join(
                quote.route_labels
            ),
        ])


def log_opportunity(
    opportunity: ArbitrageOpportunity,
) -> None:

    with OPPORTUNITY_LOG.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.writer(handle)

        writer.writerow([
            opportunity.timestamp,
            opportunity.opportunity_id,
            opportunity.buy_venue,
            opportunity.sell_venue,
            f"{opportunity.starting_usdc:.6f}",
            f"{opportunity.sol_received:.9f}",
            f"{opportunity.ending_usdc:.6f}",
            f"{opportunity.gross_profit_usdc:.6f}",
            f"{opportunity.gross_edge_pct:.6f}",
            f"{opportunity.cost_reserve_usdc:.6f}",
            f"{opportunity.net_profit_usdc:.6f}",
            f"{opportunity.net_edge_pct:.6f}",
            f"{opportunity.buy_quote.price_impact_pct:.6f}",
            f"{opportunity.sell_quote.price_impact_pct:.6f}",
            "|".join(
                opportunity.buy_quote.route_labels
            ),
            "|".join(
                opportunity.sell_quote.route_labels
            ),
        ])


# ================================================================
# ARBITRAGE CALCULATION
# ================================================================

def calculate_opportunity(
    buy_quote: VenueQuote,
    sell_quote: VenueQuote,
    cost_reserve_usdc: float,
) -> ArbitrageOpportunity | None:

    if buy_quote.direction != "BUY":
        return None

    if sell_quote.direction != "SELL":
        return None

    if buy_quote.output_amount <= 0:
        return None

    if sell_quote.input_amount <= 0:
        return None

    # The SELL must consume exactly the SOL received
    # from the BUY quote.
    if (
        sell_quote.input_amount
        != buy_quote.output_amount
    ):
        return None

    starting_usdc = (
        buy_quote.input_human
    )

    sol_received = (
        buy_quote.output_human
    )

    ending_usdc = (
        sell_quote.output_human
    )

    if starting_usdc <= 0:
        return None

    gross_profit_usdc = (
        ending_usdc
        - starting_usdc
    )

    gross_edge_pct = (
        gross_profit_usdc
        / starting_usdc
    ) * 100

    net_profit_usdc = (
        gross_profit_usdc
        - cost_reserve_usdc
    )

    net_edge_pct = (
        net_profit_usdc
        / starting_usdc
    ) * 100

    return ArbitrageOpportunity(
        opportunity_id=str(
            uuid.uuid4()
        )[:8],

        buy_venue=buy_quote.venue,
        sell_venue=sell_quote.venue,

        buy_quote=buy_quote,
        sell_quote=sell_quote,

        starting_usdc=starting_usdc,
        sol_received=sol_received,
        ending_usdc=ending_usdc,

        gross_profit_usdc=gross_profit_usdc,
        gross_edge_pct=gross_edge_pct,

        cost_reserve_usdc=cost_reserve_usdc,

        net_profit_usdc=net_profit_usdc,
        net_edge_pct=net_edge_pct,

        timestamp=datetime.now(
            timezone.utc
        ).isoformat(),
    )


# ================================================================
# DECISION ENGINE
# ================================================================

def get_decision(
    opportunity: ArbitrageOpportunity,
    min_edge_pct: float,
    strong_edge_pct: float,
    max_price_impact_pct: float,
) -> tuple[str, str]:

    if (
        opportunity
        .buy_quote
        .price_impact_pct
        > max_price_impact_pct
    ):

        return (
            "REJECT",
            "Buy-side price impact is above "
            "the configured limit.",
        )

    if (
        opportunity
        .sell_quote
        .price_impact_pct
        > max_price_impact_pct
    ):

        return (
            "REJECT",
            "Sell-side price impact is above "
            "the configured limit.",
        )

    if (
        opportunity.net_edge_pct
        >= strong_edge_pct
    ):

        return (
            "STRONG PAPER EDGE",
            "Round-trip net edge exceeds "
            "the strong-edge threshold.",
        )

    if (
        opportunity.net_edge_pct
        >= min_edge_pct
    ):

        return (
            "PAPER WATCH",
            "Positive round-trip net edge detected.",
        )

    return (
        "NO EDGE",
        "Round-trip net edge is below "
        "the minimum threshold.",
    )


# ================================================================
# DISPLAY
# ================================================================

def display_venue_quote(quote: VenueQuote) -> None:
    direction_color = GREEN if quote.direction == "BUY" else RED
    print(
        f"│ {ui(quote.direction, direction_color, True):<4} "
        f"{ui(quote.venue, BRIGHT_ORANGE, True):<16} "
        f"in={quote.input_human:>12.6f} "
        f"out={quote.output_human:>12.9f} "
        f"impact={quote.price_impact_pct:.4f}%"
    )
    if quote.route_labels:
        print("│      " + ui("route: ", CYAN) + ui(", ".join(quote.route_labels), CYAN))


def display_opportunity(
    opportunity: ArbitrageOpportunity,
    min_edge_pct: float,
    strong_edge_pct: float,
    max_price_impact_pct: float,
) -> None:
    decision, reason = get_decision(
        opportunity, min_edge_pct, strong_edge_pct, max_price_impact_pct
    )
    print()
    print(ui("╭────────────────────────────────────────────────────────────────╮", ORANGE, True))
    print(ui("│  🔥  MEGATRON // ROUND-TRIP OPPORTUNITY                        │", BRIGHT_ORANGE, True))
    print(ui("╰────────────────────────────────────────────────────────────────╯", ORANGE, True))
    print(f"│ {ui('ID', CYAN, True):<20}{ui(opportunity.opportunity_id, BRIGHT_ORANGE, True)}")
    print(f"│ {ui('BUY SOL', CYAN, True):<20}{ui(opportunity.buy_venue, GREEN, True)}")
    print(f"│ {ui('SELL SOL', CYAN, True):<20}{ui(opportunity.sell_venue, RED, True)}")
    print("│")
    print(f"│ {ui('START USDC', CYAN, True):<20}${opportunity.starting_usdc:,.6f}")
    print(f"│ {ui('SOL RECEIVED', CYAN, True):<20}{opportunity.sol_received:.9f}")
    print(f"│ {ui('END USDC', CYAN, True):<20}${opportunity.ending_usdc:,.6f}")
    print("│")
    print(f"│ {ui('GROSS PROFIT', CYAN, True):<20}{money_ui(opportunity.gross_profit_usdc)}")
    print(f"│ {ui('GROSS EDGE', CYAN, True):<20}{edge_ui(opportunity.gross_edge_pct)}")
    print(f"│ {ui('COST RESERVE', CYAN, True):<20}${opportunity.cost_reserve_usdc:.6f}")
    print(f"│ {ui('NET PROFIT', CYAN, True):<20}{money_ui(opportunity.net_profit_usdc)}")
    print(f"│ {ui('NET EDGE', CYAN, True):<20}{edge_ui(opportunity.net_edge_pct)}")
    print("│")
    print(f"│ {ui('BUY IMPACT', CYAN, True):<20}{opportunity.buy_quote.price_impact_pct:.4f}%")
    print(f"│ {ui('SELL IMPACT', CYAN, True):<20}{opportunity.sell_quote.price_impact_pct:.4f}%")
    print("│")
    print(f"│ {ui('BUY ROUTE', CYAN, True):<20}{ui(', '.join(opportunity.buy_quote.route_labels) or 'N/A', WHITE)}")
    print(f"│ {ui('SELL ROUTE', CYAN, True):<20}{ui(', '.join(opportunity.sell_quote.route_labels) or 'N/A', WHITE)}")
    print("│")
    if decision == "STRONG PAPER EDGE":
        print(ui("│ 🚨 VERDICT: STRONG PAPER EDGE", GREEN, True))
    elif decision == "PAPER WATCH":
        print(ui("│ 🟡 VERDICT: PAPER WATCH", YELLOW, True))
    elif decision == "REJECT":
        print(ui("│ 🔴 VERDICT: REJECT", RED, True))
    else:
        print(ui("│ ⚪ VERDICT: NO EDGE", GRAY, True))
    print(f"│ {reason}")
    print("│")
    print(ui("└─ 🛡 NO LIVE TRADE EXECUTED", GRAY, True))


# BUY QUOTES
# ================================================================

def scan_buy_quotes(
    venues: list[str],
    starting_usdc: float,
    slippage_bps: int,
    timeout: float,
    max_retries: int,
    backoff_seconds: float,
    request_delay: float,
) -> list[VenueQuote]:

    global RUNNING

    amount = int(
        round(
            starting_usdc * 1_000_000
        )
    )

    quotes: list[VenueQuote] = []

    print()
    print(
        "┌─ 📡 LIVE BUY QUOTES "
        "// USDC → SOL"
    )

    for venue in venues:

        # Stop before making another network request.
        # Phase 2B request spacing is centralized in http_get_json().
        if not RUNNING:
            break

        try:

            quote = get_quote(
                venue=venue,
                direction="BUY",
                amount=amount,
                slippage_bps=slippage_bps,
                timeout=timeout,
                max_retries=max_retries,
                backoff_seconds=backoff_seconds,
                request_delay=request_delay,
            )

            if not RUNNING:
                break

            quotes.append(quote)

            log_quote(quote)

            display_venue_quote(
                quote
            )

        except InterruptedError:
            break

        except Exception as exc:

            if not RUNNING:
                break

            print(
                f"│ BUY  {venue:<16} "
                f"UNAVAILABLE ({exc})"
            )

    print(
        "└────────────────────────────"
    )

    return quotes


# ================================================================
# SELL QUOTE
# ================================================================

def scan_sell_quote(
    venue: str,
    sol_amount: int,
    slippage_bps: int,
    timeout: float,
    max_retries: int,
    backoff_seconds: float,
    request_delay: float,
) -> VenueQuote:

    return get_quote(
        venue=venue,
        direction="SELL",
        amount=sol_amount,
        slippage_bps=slippage_bps,
        timeout=timeout,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
        request_delay=request_delay,
    )


# ================================================================
# FIND BEST OPPORTUNITY
# ================================================================

def find_best_opportunity(
    buy_quotes: list[VenueQuote],
    venues: list[str],
    slippage_bps: int,
    timeout: float,
    cost_reserve_usdc: float,
    max_price_impact_pct: float,
    max_retries: int,
    backoff_seconds: float,
    request_delay: float,
) -> tuple[
    ArbitrageOpportunity | None,
    list[VenueQuote],
]:

    best: ArbitrageOpportunity | None = None
    sell_quotes: list[VenueQuote] = []

    # ------------------------------------------------------------
    # PHASE 2C // RANK + CAP BUY CANDIDATES
    # ------------------------------------------------------------
    candidates = [
        quote
        for quote in buy_quotes
        if (
            quote.output_amount > 0
            and quote.price_impact_pct <= max_price_impact_pct
        )
    ]

    candidates.sort(
        key=lambda quote: quote.output_amount,
        reverse=True,
    )

    total_candidates = len(candidates)
    candidates = candidates[:DEFAULT_MAX_BUY_CANDIDATES]

    if not candidates:
        return None, sell_quotes

    print()
    print(
        f"│ 🧠 PHASE 2C // "
        f"{total_candidates} BUY candidates ranked"
    )
    print(
        f"│    VERIFYING TOP "
        f"{len(candidates)}/{total_candidates} BUY candidates"
    )

    # ------------------------------------------------------------
    # PHASE 2C // SELL CACHE
    #
    # A SELL quote is deterministic for an exact:
    #   venue + SOL amount + slippage
    #
    # If two BUY routes produce the same SOL amount, reuse the
    # verified SELL quote instead of making another Jupiter call.
    # Cache lifetime is one find_best_opportunity() pass only, so
    # quotes cannot leak across scan cycles.
    # ------------------------------------------------------------
    sell_cache: dict[
        tuple[str, int, int],
        VenueQuote,
    ] = {}

    for buy_quote in candidates:

        if not RUNNING:
            break

        for sell_venue in venues:

            if not RUNNING:
                break

            if sell_venue == buy_quote.venue:
                continue

            cache_key = (
                sell_venue,
                buy_quote.output_amount,
                slippage_bps,
            )

            sell_quote = sell_cache.get(cache_key)

            if sell_quote is not None:
                print(
                    f"│   ⚡ SELL CACHE HIT  "
                    f"{sell_venue:<16} "
                    f"SOL={buy_quote.output_human:.9f}"
                )
            else:
                try:
                    sell_quote = scan_sell_quote(
                        venue=sell_venue,
                        sol_amount=buy_quote.output_amount,
                        slippage_bps=slippage_bps,
                        timeout=timeout,
                        max_retries=max_retries,
                        backoff_seconds=backoff_seconds,
                        request_delay=request_delay,
                    )

                    if not RUNNING:
                        break

                    sell_cache[cache_key] = sell_quote

                    sell_quotes.append(sell_quote)
                    log_quote(sell_quote)

                except InterruptedError:
                    break

                except Exception as exc:

                    if not RUNNING:
                        break

                    print(
                        f"│ SELL "
                        f"{sell_venue:<16} "
                        f"for BUY "
                        f"{buy_quote.venue:<12} "
                        f"UNAVAILABLE "
                        f"({exc})"
                    )
                    continue

            if not RUNNING:
                break

            # ----------------------------------------------------
            # Reject unsafe SELL price impact immediately.
            # ----------------------------------------------------
            if (
                sell_quote.price_impact_pct
                > max_price_impact_pct
            ):
                print(
                    f"│ SELL {sell_venue:<16} "
                    f"REJECTED "
                    f"(price impact "
                    f"{sell_quote.price_impact_pct:.4f}% "
                    f"> {max_price_impact_pct:.4f}%)"
                )
                continue

            opportunity = calculate_opportunity(
                buy_quote=buy_quote,
                sell_quote=sell_quote,
                cost_reserve_usdc=cost_reserve_usdc,
            )

            if opportunity is None:
                continue

            # ----------------------------------------------------
            # Keep the best verified round-trip opportunity.
            # ----------------------------------------------------
            if (
                best is None
                or opportunity.net_edge_pct
                > best.net_edge_pct
            ):
                best = opportunity

    if not RUNNING:
        return None, sell_quotes

    return best, sell_quotes


# ================================================================
# RESEARCH SIZE PARSER
# ================================================================

def parse_research_sizes(
    raw: str,
) -> list[float]:

    sizes: list[float] = []

    for item in raw.split(","):

        item = item.strip()

        if not item:
            continue

        try:
            value = float(item)

        except ValueError as exc:

            raise SystemExit(
                f"Invalid research size "
                f"{item!r}. "
                "Use values like "
                "10,25,50."
            ) from exc

        if value <= 0:

            raise SystemExit(
                "All research sizes must "
                "be greater than 0."
            )

        sizes.append(value)

    if not sizes:

        raise SystemExit(
            "At least one research size "
            "is required."
        )

    return list(
        dict.fromkeys(sizes)
    )


# ================================================================
# ARGUMENTS
# ================================================================

def parse_args() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "MEGATRON live Solana "
            "cross-venue arbitrage "
            "scanner. "
            "Research/paper mode only."
        )
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help=(
            "Run exactly one scan "
            "and exit."
        ),
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_SCAN_INTERVAL,
        help=(
            "Seconds between scans."
        ),
    )

    parser.add_argument(
        "--usdc",
        type=float,
        default=DEFAULT_USDC_AMOUNT,
        help=(
            "Custom single research size."
        ),
    )

    parser.add_argument(
        "--sizes",
        type=str,
        default=",".join(
            f"{x:g}"
            for x in DEFAULT_SIZES
        ),
        help=(
            "Comma-separated research "
            "sizes."
        ),
    )

    parser.add_argument(
        "--slippage-bps",
        type=int,
        default=DEFAULT_SLIPPAGE_BPS,
        help=(
            "Jupiter slippage in bps."
        ),
    )

    parser.add_argument(
        "--min-edge",
        type=float,
        default=DEFAULT_MIN_NET_EDGE_PCT,
        help=(
            "Minimum net edge percentage."
        ),
    )

    parser.add_argument(
        "--strong-edge",
        type=float,
        default=DEFAULT_STRONG_EDGE_PCT,
        help=(
            "Strong edge percentage."
        ),
    )

    parser.add_argument(
        "--max-impact",
        type=float,
        default=DEFAULT_MAX_PRICE_IMPACT_PCT,
        help=(
            "Maximum price impact."
        ),
    )

    parser.add_argument(
        "--cost-reserve",
        type=float,
        default=DEFAULT_COST_RESERVE_USDC,
        help=(
            "Research cost reserve."
        ),
    )

    parser.add_argument(
        "--venues",
        type=str,
        default=",".join(
            DEFAULT_VENUES
        ),
        help=(
            "Comma-separated Jupiter "
            "venue labels."
        ),
    )

    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Show live-trade eligibility checks. Does NOT execute transactions."
        ),
    )

    parser.add_argument(
        "--max-trade-usdc",
        type=float,
        default=DEFAULT_MAX_TRADE_USDC,
        help="Maximum candidate size for the safety gate.",
    )

    parser.add_argument(
        "--max-daily-loss-usdc",
        type=float,
        default=DEFAULT_MAX_DAILY_LOSS_USDC,
        help="Daily loss limit used by the safety gate.",
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=(
            "HTTP timeout in seconds."
        ),
    )

    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help=(
            "Maximum Jupiter 429 retries."
        ),
    )

    parser.add_argument(
        "--backoff",
        type=float,
        default=DEFAULT_BACKOFF_SECONDS,
        help=(
            "Initial 429 backoff seconds."
        ),
    )

    parser.add_argument(
        "--request-delay",
        type=float,
        default=DEFAULT_REQUEST_DELAY,
        help=(
            "Delay between Jupiter "
            "requests."
        ),
    )

    return parser.parse_args()


# ================================================================
# TRADE SAFETY GATE
# ================================================================

def evaluate_trade_gate(
    opportunity: ArbitrageOpportunity,
    min_edge_pct: float,
    max_price_impact_pct: float,
    max_trade_usdc: float,
    max_daily_loss_usdc: float,
) -> tuple[bool, list[str]]:
    """Evaluate whether an opportunity is eligible for a future executor.

    This function never signs, broadcasts, or submits a transaction.
    """
    reasons: list[str] = []
    if opportunity.net_edge_pct < min_edge_pct:
        reasons.append(f"net edge {opportunity.net_edge_pct:+.4f}% < {min_edge_pct:.4f}% minimum")
    if opportunity.buy_quote.price_impact_pct > max_price_impact_pct:
        reasons.append("buy price impact exceeds limit")
    if opportunity.sell_quote.price_impact_pct > max_price_impact_pct:
        reasons.append("sell price impact exceeds limit")
    if opportunity.starting_usdc > max_trade_usdc:
        reasons.append(f"size ${opportunity.starting_usdc:.2f} > ${max_trade_usdc:.2f} max")
    if opportunity.net_profit_usdc < -max_daily_loss_usdc:
        reasons.append("candidate loss exceeds daily-loss guard")
    return not reasons, reasons


# ================================================================
# MAIN
# ================================================================

def main() -> None:

    global RUNNING

    args = parse_args()

    if args.usdc <= 0:
        raise SystemExit(
            "--usdc must be greater than 0."
        )

    if args.interval <= 0:
        raise SystemExit(
            "--interval must be greater than 0."
        )

    if not (
        0
        <= args.slippage_bps
        <= 10_000
    ):
        raise SystemExit(
            "--slippage-bps must be "
            "between 0 and 10000."
        )

    if args.max_retries < 0:
        raise SystemExit(
            "--max-retries cannot "
            "be negative."
        )

    if args.backoff < 0:
        raise SystemExit(
            "--backoff cannot "
            "be negative."
        )

    if args.request_delay < 0:
        raise SystemExit(
            "--request-delay cannot "
            "be negative."
        )

    if args.max_trade_usdc <= 0:
        raise SystemExit("--max-trade-usdc must be greater than 0.")

    if args.max_daily_loss_usdc <= 0:
        raise SystemExit("--max-daily-loss-usdc must be greater than 0.")

    venues = [
        venue.strip()
        for venue in args.venues.split(",")
        if venue.strip()
    ]

    if len(venues) < 2:
        raise SystemExit(
            "At least two venues "
            "are required."
        )

    # If --usdc was explicitly supplied,
    # scan only that amount.
    usdc_explicit = any(
        arg == "--usdc"
        or arg.startswith("--usdc=")
        for arg in os.sys.argv[1:]
    )

    if usdc_explicit:

        research_sizes = [
            args.usdc
        ]

    else:

        research_sizes = (
            parse_research_sizes(
                args.sizes
            )
        )

    print()

    print(ui("╔" + "═" * 66 + "╗", ORANGE, True))

    print(ui(
        "║" + " MEGATRON // SOLANA ARBITRAGE ENGINE ".center(66) + "║",
        BRIGHT_ORANGE, True
    ))

    print(ui(
        "║" + " LIVE QUOTES / PAPER RESEARCH ".center(66) + "║",
        ORANGE, True
    ))

    print(ui("╠" + "═" * 66 + "╣", ORANGE, True))

    print(
        "║ 🟢 JUPITER DATA          LIVE"
        .ljust(67)
        + "║"
    )

    print(
        "║ 🟢 CROSS-VENUE SCAN      LIVE"
        .ljust(67)
        + "║"
    )

    print(
        ("║ 🟠 LIVE MODE             GATED" if args.live else "║ 🛡 LIVE TRADING          OFF")
        .ljust(67)
        + "║"
    )

    print(
        "║ 🛡 WALLET                NOT CONNECTED"
        .ljust(67)
        + "║"
    )

    print(
        "║ 🛡 REAL TRANSACTIONS     DISABLED"
        .ljust(67)
        + "║"
    )

    print(ui("╚" + "═" * 66 + "╝", ORANGE, True))

    print()

    if len(research_sizes) == 1:

        print(
            f"Research size:      "
            f"${research_sizes[0]:.2f} USDC"
        )

    else:

        print(
            "Research sizes:     "
            + ", ".join(
                f"${size:.2f}"
                for size in research_sizes
            )
            + " USDC"
        )

    print(
        f"Venues:             "
        f"{', '.join(venues)}"
    )

    print(
        f"Slippage setting:   "
        f"{args.slippage_bps} bps"
    )

    print(
        f"Cost reserve:       "
        f"${args.cost_reserve:.4f}"
    )

    print(
        f"Minimum net edge:   "
        f"{args.min_edge:.4f}%"
    )

    print(
        f"Strong edge:        "
        f"{args.strong_edge:.4f}%"
    )

    print(
        f"Max price impact:   "
        f"{args.max_impact:.4f}%"
    )

    print(
        f"Request delay:      "
        f"{args.request_delay:.2f}s"
    )

    print(
        f"429 cooldown:       "
        f"{DEFAULT_429_COOLDOWN_SECONDS:.2f}s"
    )

    print(
        f"Max BUY candidates: "
        f"{DEFAULT_MAX_BUY_CANDIDATES}"
    )

    print(
        f"429 retries:        "
        f"{args.max_retries}"
    )

    try:

        load_api_key()

    except Exception as exc:

        print()
        print(
            f"❌ API ERROR: {exc}"
        )

        return

    initialize_logs()

    scan_number = 0
    opportunities_found = 0

    try:

        while RUNNING:

            scan_number += 1

            print()

            print(
                "═" * 66
            )

            print(
                f"SCAN #{scan_number} "
                f"{datetime.now().strftime('%H:%M:%S')}"
            )

            print(
                "═" * 66
            )

            cycle_results: list[
                tuple[
                    float,
                    ArbitrageOpportunity | None
                ]
            ] = []

            for size_index, starting_usdc in enumerate(
                research_sizes,
                start=1,
            ):
                # ----------------------------------------------------
                # HARD STOP CHECK
                # ----------------------------------------------------
                if not RUNNING:
                    break

                print()
                print(
                    f"┌─ 💰 RESEARCH SIZE "
                    f"{size_index}/"
                    f"{len(research_sizes)} "
                    f"// ${starting_usdc:.2f} USDC"
                )

                # ----------------------------------------------------
                # BUY QUOTES
                # ----------------------------------------------------
                buy_quotes = scan_buy_quotes(
                    venues=venues,
                    starting_usdc=starting_usdc,
                    slippage_bps=args.slippage_bps,
                    timeout=args.timeout,
                    max_retries=args.max_retries,
                    backoff_seconds=args.backoff,
                    request_delay=args.request_delay,
                )

                # ----------------------------------------------------
                # HARD STOP AFTER NETWORK ACTIVITY
                #
                # If Ctrl+C was pressed while Jupiter was working,
                # discard this research size completely.
                # ----------------------------------------------------
                if not RUNNING:
                    break

                if len(buy_quotes) < 2:
                    print()
                    print(
                        "⚠ DATA INCOMPLETE — "
                        "not enough live BUY "
                        f"quotes for ${starting_usdc:.2f}."
                    )
                    print(
                        "│ No NO-EDGE conclusion "
                        "made from incomplete data."
                    )
                    print(
                        "└────────────────────────"
                        "────────────────────"
                    )

                    cycle_results.append(
                        (
                            starting_usdc,
                            None,
                        )
                    )

                    continue

                print()
                print(
                    "┌─ 🔄 ROUND-TRIP "
                    "SELL QUOTES"
                )

                try:
                    opportunity, _ = find_best_opportunity(
                        buy_quotes=buy_quotes,
                        venues=venues,
                        slippage_bps=args.slippage_bps,
                        timeout=args.timeout,
                        cost_reserve_usdc=args.cost_reserve,
                        max_price_impact_pct=args.max_impact,
                        max_retries=args.max_retries,
                        backoff_seconds=args.backoff,
                        request_delay=args.request_delay,
                    )
                except InterruptedError:
                    RUNNING = False
                    break

                print(
                    "└────────────────────────"
                    "────────────────────"
                )

                # ----------------------------------------------------
                # HARD STOP AFTER SELL QUOTES
                #
                # Never allow a partial round-trip to become a
                # displayed opportunity.
                # ----------------------------------------------------
                if not RUNNING:
                    break

                cycle_results.append(
                    (
                        starting_usdc,
                        opportunity,
                    )
                )

                if opportunity is not None:
                    opportunities_found += 1

                    display_opportunity(
                        opportunity=opportunity,
                        min_edge_pct=args.min_edge,
                        strong_edge_pct=args.strong_edge,
                        max_price_impact_pct=args.max_impact,
                    )

                    log_opportunity(opportunity)

                    if args.live:
                        gate_ok, gate_reasons = evaluate_trade_gate(
                            opportunity=opportunity,
                            min_edge_pct=args.min_edge,
                            max_price_impact_pct=args.max_impact,
                            max_trade_usdc=args.max_trade_usdc,
                            max_daily_loss_usdc=args.max_daily_loss_usdc,
                        )

                        print()
                        print(
                            ui(
                                "┌─ 🟡 LIVE TRADE GATE",
                                YELLOW,
                                True,
                            )
                        )
                        print(
                            ui(
                                f"│ SIZE LIMIT "
                                f"${args.max_trade_usdc:.2f}",
                                YELLOW,
                            )
                        )
                        print(
                            ui(
                                f"│ DAILY LOSS LIMIT "
                                f"${args.max_daily_loss_usdc:.2f}",
                                YELLOW,
                            )
                        )

                        if gate_ok:
                            print(
                                ui(
                                    "│ 🟢 ELIGIBLE: "
                                    "ALL SAFETY CHECKS PASSED",
                                    GREEN,
                                    True,
                                )
                            )
                            print(
                                ui(
                                    "│ 🛡 EXECUTION BLOCKED: "
                                    "NO WALLET / TRANSACTION ENGINE",
                                    GRAY,
                                    True,
                                )
                            )
                        else:
                            print(
                                ui(
                                    "│ 🔴 BLOCKED",
                                    RED,
                                    True,
                                )
                            )

                            for reason in gate_reasons:
                                print(
                                    ui(
                                        f"│   • {reason}",
                                        RED,
                                    )
                                )

                        print(
                            ui(
                                "└─ 🛡 NO REAL TRANSACTION EXECUTED",
                                GRAY,
                                True,
                            )
                        )

                else:
                    print()
                    print(
                        f"🟡 No valid round-trip "
                        f"opportunity for "
                        f"${starting_usdc:.2f}."
                    )

                print()
                print(
                    f"└─ 🧪 SIZE RESULT "
                    f"${starting_usdc:.2f} "
                    f"// RESEARCH ONLY"
                )

            # ----------------------------------------------------
            # INTERRUPTED SCAN
            #
            # IMPORTANT:
            # Do not generate a multi-size summary from partial
            # research after Ctrl+C.
            # ----------------------------------------------------
            if not RUNNING:
                print()
                print(
                    "┌─ 🛑 SCAN ABORTED"
                )
                print(
                    "│ Partial research results discarded"
                )
                print(
                    "│ No partial opportunity reported"
                )
                print(
                    "│ No trade decision generated"
                )
                print(
                    "│ No real transaction executed"
                )
                print(
                    "└────────────────────────"
                    "────────────────────"
                )
                continue

            # ----------------------------------------------------
            # MULTI-SIZE SUMMARY
            # ----------------------------------------------------

            valid_results = [
                (
                    size,
                    opportunity,
                )
                for size, opportunity
                in cycle_results
                if opportunity is not None
            ]

            print()

            print(
                "┌─ 🏆 MEGATRON // "
                "MULTI-SIZE SUMMARY"
            )

            if not valid_results:

                print(
                    "│ No valid round-trip "
                    "results this scan."
                )

            else:

                ranked = sorted(
                    valid_results,
                    key=lambda item:
                        item[1].net_edge_pct,
                    reverse=True,
                )

                for rank, (
                    size,
                    opportunity,
                ) in enumerate(
                    ranked,
                    start=1,
                ):

                    print(
                        f"│ #{rank} "
                        f"${size:>9,.2f} "
                        f"{opportunity.buy_venue:<16} "
                        f"→ "
                        f"{opportunity.sell_venue:<16} "
                        f"net="
                        f"{opportunity.net_edge_pct:+.4f}% "
                        f"profit="
                        f"${opportunity.net_profit_usdc:+.6f}"
                    )

                best_size, best_opportunity = (
                    ranked[0]
                )

                print("│")

                print(
                    f"│ 🥇 BEST SIZE        "
                    f"${best_size:,.2f}"
                )

                print(
                    f"│ 🥇 BEST NET EDGE    "
                    f"{best_opportunity.net_edge_pct:+.4f}%"
                )

                print(
                    f"│ 🥇 BEST NET PROFIT  "
                    f"${best_opportunity.net_profit_usdc:+.6f}"
                )

                print(
                    f"│ 🥇 ROUTE            "
                    f"{best_opportunity.buy_venue} "
                    f"→ "
                    f"{best_opportunity.sell_venue}"
                )

            print(
                "└────────────────────────"
                "────────────────────"
            )

            # ----------------------------------------------------
            # SAFETY
            # ----------------------------------------------------

            print()

            print(
                "┌─ 🛡 SAFETY STATUS"
            )

            print(
                "│ LIVE TRADING      GATED" if args.live else "│ LIVE TRADING      OFF"
            )

            print(
                "│ WALLET            NOT CONNECTED"
            )

            print(
                "│ TRANSACTIONS      DISABLED"
            )

            print(
                "│ FINAL DECISION    YOU"
            )

            print(
                "└────────────────────────────"
            )

            if args.once:
                break

            if RUNNING:

                print()

                print(
                    f"Next scan in "
                    f"{args.interval:g} seconds..."
                )

                time.sleep(
                    args.interval
                )

    except KeyboardInterrupt:

        pass

    finally:

        print()

        print(
            "╔"
            + "═" * 66
            + "╗"
        )

        print(
            "║"
            + " MEGATRON ENGINE STOPPED "
            .center(66)
            + "║"
        )

        print(
            "╠"
            + "═" * 66
            + "╣"
        )

        print(
            f"║ SCANS              "
            f"{scan_number}"
            .ljust(67)
            + "║"
        )

        print(
            f"║ OPPORTUNITIES      "
            f"{opportunities_found}"
            .ljust(67)
            + "║"
        )

        print(
            ("║ 🟠 LIVE TRADING     GATED" if args.live else "║ 🛡 LIVE TRADING     OFF")
            .ljust(67)
            + "║"
        )

        print(
            "║ 🛡 WALLET           NOT CONNECTED"
            .ljust(67)
            + "║"
        )

        print(
            "║ 🛡 TRANSACTIONS     DISABLED"
            .ljust(67)
            + "║"
        )

        print(
            "╚"
            + "═" * 66
            + "╝"
        )

        print()

        print(
            f"Quote history:       "
            f"{QUOTE_LOG}"
        )

        print(
            f"Opportunity history: "
            f"{OPPORTUNITY_LOG}"
        )

        print(
            "No real transactions executed. Transaction execution is not implemented in this scanner."
        )


# ================================================================
# ENTRY POINT
# ================================================================

if __name__ == "__main__":
    main()
