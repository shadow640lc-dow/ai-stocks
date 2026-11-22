#!/usr/bin/env python3
"""
MEGATRON // STOCK INTELLIGENCE

Interactive launcher for the existing AI Hedge Fund engine.

MEGASTOCKS provides:
    - Ticker selection
    - Multi-ticker research
    - Research workflow selection
    - Existing AI analyst selection
    - Existing Ollama selection
    - Existing reasoning mode
    - Existing backtesting
    - Clean interruption handling

The underlying AI Hedge Fund engine is NOT modified here.

No automatic live trading is performed by this launcher.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent


# ============================================================
# TERMINAL COLORS
# ============================================================

def orange(text: str) -> str:
    """MEGASTOCKS primary neon-orange."""
    return f"\033[38;5;208m{text}\033[0m"


def cyan(text: str) -> str:
    return f"\033[96m{text}\033[0m"


def green(text: str) -> str:
    return f"\033[92m{text}\033[0m"


def red(text: str) -> str:
    return f"\033[91m{text}\033[0m"


def yellow(text: str) -> str:
    return f"\033[93m{text}\033[0m"


def white(text: str) -> str:
    return f"\033[97m{text}\033[0m"


def dim(text: str) -> str:
    return f"\033[2m{text}\033[0m"


# ============================================================
# SCREEN
# ============================================================

def clear_screen() -> None:
    os.system("clear")


# ============================================================
# MAIN HEADER
# ============================================================

def show_header() -> None:
    print(orange("╔══════════════════════════════════════════════════════════════╗"))
    print(orange("║                                                              ║"))
    print(orange("║             ⚡ MEGATRON // STOCK INTELLIGENCE               ║"))
    print(orange("║                                                              ║"))
    print(orange("║                 AI MARKET RESEARCH TERMINAL                 ║"))
    print(orange("║                                                              ║"))
    print(orange("╠══════════════════════════════════════════════════════════════╣"))

    print(
        orange("║ ")
        + green("● Market Data       READY")
        + orange("                                     ║")
    )

    print(
        orange("║ ")
        + green("● AI Research       READY")
        + orange("                                     ║")
    )

    print(
        orange("║ ")
        + green("● Risk Engine       READY")
        + orange("                                     ║")
    )

    print(
        orange("║ ")
        + yellow("● Trading           SIMULATION / RESEARCH")
        + orange("              ║")
    )

    print(orange("╚══════════════════════════════════════════════════════════════╝"))
    print()


# ============================================================
# TICKER HELP
# ============================================================

def show_ticker_help() -> None:
    print(orange("┌─ TICKER INPUT"))
    print(orange("│"))
    print(white("│  Enter one ticker:"))
    print(cyan("│      NVDA"))
    print()
    print(white("│  Enter multiple tickers:"))
    print(cyan("│      NVDA AMD PLTR MSFT"))
    print()
    print(white("│  Commas also work:"))
    print(cyan("│      NVDA, AMD, PLTR"))
    print()
    print(white("│  Example market symbols:"))
    print(cyan("│      DXY VIX"))
    print()
    print(orange("└────────────────────────────────────────────────────────────"))
    print()


# ============================================================
# TICKER PARSER
# ============================================================

def parse_tickers(raw: str) -> list[str]:
    """
    Convert user input into individual ticker symbols.

    Examples:

        NVDA
        NVDA AMD PLTR
        NVDA,AMD,PLTR
        NVDA, AMD, PLTR

    Duplicate symbols are removed while preserving order.
    """

    raw = raw.replace(",", " ")

    tokens = raw.split()

    tickers: list[str] = []

    for token in tokens:
        symbol = token.strip().upper()

        if not symbol:
            continue

        if symbol not in tickers:
            tickers.append(symbol)

    return tickers


# ============================================================
# TICKER SELECTION
# ============================================================

def get_tickers() -> list[str] | None:
    show_ticker_help()

    try:
        raw = input(
            cyan("  📈 Ticker(s): ")
        ).strip()

    except (KeyboardInterrupt, EOFError):
        print()
        print()
        print(yellow("  🛑 Ticker entry cancelled."))
        return None

    if not raw:
        print()
        print(red("  ✖ No ticker entered."))
        return None

    tickers = parse_tickers(raw)

    if not tickers:
        print()
        print(red("  ✖ No valid ticker symbols found."))
        return None

    print()
    print(
        orange("  SELECTED TICKER(S): ")
        + white(" ".join(tickers))
    )
    print()

    return tickers


# ============================================================
# RESEARCH MENU
# ============================================================

def show_research_menu() -> None:
    print(orange("┌─ RESEARCH WORKFLOW"))
    print(orange("│"))
    print(cyan("│  [1] ⚡ Full AI Hedge Fund"))
    print(cyan("│  [2] 🤖 AI Hedge Fund + Local Ollama"))
    print(cyan("│  [3] 🔬 Full AI + Show Reasoning"))
    print(cyan("│  [4] 📊 Backtest"))
    print(cyan("│  [5] 🧠 Ollama + Reasoning"))
    print(cyan("│  [8] ⚡ AI Hedge Fund + Alpaca Execution"))
    print(cyan("│  [6] 🔄 Change Ticker(s)"))
    print(cyan("│  [7] 🚪 Exit"))
    print(orange("│"))
    print(orange("└────────────────────────────────────────────────────────────"))
    print()


# ============================================================
# COMMAND BUILDERS
# ============================================================

def build_main_command(
    ticker: str,
    choice: str,
    *,
    alpaca: bool = False,
) -> list[str] | None:
    """
    Build a command for the existing AI Hedge Fund engine.

    IMPORTANT:
    Each ticker is passed individually.

    This prevents:
        --ticker "NFLX TSLA DXY VIX"

    and instead produces:
        --ticker NFLX
        --ticker TSLA
        --ticker DXY
        --ticker VIX

    When alpaca=True the engine runs in --alpaca mode: every trade
    decision must be approved in the terminal before a real order is
    sent to your Alpaca account.
    """

    base = [
        "poetry",
        "run",
        "python",
        "src/main.py",
        "--ticker",
        ticker,
    ]

    if choice == "8":
        choice = "1"

    if choice == "1":
        command = base

    elif choice == "2":
        command = base + [
            "--ollama",
        ]

    elif choice == "3":
        command = base + [
            "--show-reasoning",
        ]

    elif choice == "5":
        command = base + [
            "--ollama",
            "--show-reasoning",
        ]

    else:
        return None

    if alpaca:
        command = command + [
            "--alpaca",
        ]

    return command


def build_backtest_command(
    ticker: str,
) -> list[str]:

    return [
        "poetry",
        "run",
        "python",
        "src/backtester.py",
        "--ticker",
        ticker,
    ]


# ============================================================
# ENGINE LAUNCH
# ============================================================

def run_engine(
    ticker: str,
    command: list[str],
    index: int,
    total: int,
    *,
    live: bool = False,
) -> int:

    print()
    print(orange("╔══════════════════════════════════════════════════════════════╗"))
    print(orange("║             ⚡ MEGATRON // RESEARCH LAUNCH                 ║"))
    print(orange("╚══════════════════════════════════════════════════════════════╝"))
    print()

    print(
        orange("  Ticker:    ")
        + white(ticker)
    )

    print(
        orange("  Progress:  ")
        + white(f"{index}/{total}")
    )

    print(
        orange("  Status:    ")
        + ("⚡ LIVE TRADE QUEUE" if live else green("RESEARCH"))
    )

    if live:
        print(
            orange("  Trading:   ")
            + red("CONFIRMED ALPACA EXECUTION")
        )
        print(
            orange("  Warning:   ")
            + yellow("Every order requires your approval")
        )
    else:
        print(
            orange("  Trading:   ")
            + yellow("SIMULATION / NO AUTO EXECUTION")
        )

    print()

    print(orange("  Command:"))
    print(dim("  " + " ".join(command)))
    print()

    print(
        orange(
            "  MEGATRON is launching the existing research engine..."
        )
    )

    print()

    try:

        return subprocess.call(
            command,
            cwd=ROOT,
        )

    except FileNotFoundError as exc:

        print()
        print(red("  ✖ Could not launch the research engine."))
        print(red(f"  {exc}"))
        print()

        return 1

    except KeyboardInterrupt:

        print()
        print()
        print(yellow("  🛑 Research interrupted by user."))
        print(yellow("  Returning to MEGASTOCKS."))
        print()

        return 130


# ============================================================
# MULTI-TICKER RESEARCH
# ============================================================

def run_research(
    tickers: list[str],
    choice: str,
) -> int:

    results: list[tuple[str, int]] = []

    live_choice = choice == "8"

    total = len(tickers)

    for index, ticker in enumerate(
        tickers,
        start=1,
    ):

        if choice == "4":

            command = build_backtest_command(
                ticker
            )

        else:

            command = build_main_command(
                ticker,
                choice,
                alpaca=live_choice,
            )

        if command is None:

            print()
            print(red("  ✖ Invalid research mode."))
            return 1

        exit_code = run_engine(
            ticker,
            command,
            index,
            total,
            live=live_choice,
        )

        results.append(
            (
                ticker,
                exit_code,
            )
        )

        # ----------------------------------------------------
        # USER INTERRUPTED
        # ----------------------------------------------------

        if exit_code == 130:

            break

        # ----------------------------------------------------
        # NEXT TICKER
        # ----------------------------------------------------

        if (
            total > 1
            and index < total
        ):

            print()
            print(
                orange(
                    "══════════════════════════════════════════════════════════════"
                )
            )

            print(
                orange("  NEXT TICKER: ")
                + white(tickers[index])
            )

            print(
                orange(
                    "══════════════════════════════════════════════════════════════"
                )
            )

            print()

    # ========================================================
    # RUN SUMMARY
    # ========================================================

    print()
    print(orange("╔══════════════════════════════════════════════════════════════╗"))
    print(orange("║              ⚡ MEGATRON // RUN SUMMARY                    ║"))
    print(orange("╚══════════════════════════════════════════════════════════════╝"))
    print()

    for ticker, code in results:

        if code == 0:

            status = green("✓ COMPLETE")

        elif code == 130:

            status = yellow("🛑 STOPPED")

        else:

            status = red(
                f"✖ ENGINE EXIT {code}"
            )

        print(
            orange(f"  {ticker:<10} ")
            + status
        )

    print()

    if any(
        code == 130
        for _, code in results
    ):

        print(
            yellow(
                "  Research run stopped by user."
            )
        )

    else:

        print(
            green(
                "  Research run complete."
            )
        )

    if live_choice:

        print(
            yellow(
                "  Orders were routed to Alpaca only after your "
                "explicit per-order approval."
            )
        )

    else:

        print(
            yellow(
                "  No automatic trade execution was added by MEGASTOCKS."
            )
        )

    print()

    # --------------------------------------------------------
    # IMPORTANT:
    # Don't return failure just because one ticker's engine
    # exited non-zero. The launcher itself completed normally.
    # --------------------------------------------------------

    return 0


# ============================================================
# SAFE INPUT
# ============================================================

def safe_input(prompt: str) -> str | None:
    """
    Input wrapper that handles Ctrl+C cleanly.
    """

    try:

        return input(prompt)

    except (KeyboardInterrupt, EOFError):

        print()
        print()
        print(yellow("  🛑 MEGASTOCKS operation cancelled."))
        return None


# ============================================================
# MAIN APPLICATION
# ============================================================

def main() -> int:

    while True:

        # ----------------------------------------------------
        # SELECT TICKERS
        # ----------------------------------------------------

        clear_screen()

        show_header()

        tickers = get_tickers()

        if tickers is None:

            print()
            print(
                yellow(
                    "  MEGATRON standing by. 👊"
                )
            )

            return 0

        # ----------------------------------------------------
        # WORKFLOW LOOP
        # ----------------------------------------------------

        while True:

            clear_screen()

            show_header()

            print(
                orange("  SELECTED TICKER(S): ")
                + white(" ".join(tickers))
            )

            print()

            show_research_menu()

            choice = safe_input(
                cyan("  Select: ")
            )

            # ------------------------------------------------
            # CTRL+C
            # ------------------------------------------------

            if choice is None:

                print(
                    yellow(
                        "  Returning to shell."
                    )
                )

                return 0

            choice = choice.strip()

            # ------------------------------------------------
            # EXIT
            # ------------------------------------------------

            if choice == "7":

                print()
                print(
                    orange(
                        "╔══════════════════════════════════════════════════════════════╗"
                    )
                )

                print(
                    orange(
                        "║                                                              ║"
                    )
                )

                print(
                    orange(
                        "║              ⚡ MEGATRON // STANDING BY                    ║"
                    )
                )

                print(
                    orange(
                        "║                                                              ║"
                    )
                )

                print(
                    orange(
                        "║              No automatic trade executed.                   ║"
                    )
                )

                print(
                    orange(
                        "║                                                              ║"
                    )
                )

                print(
                    orange(
                        "╚══════════════════════════════════════════════════════════════╝"
                    )
                )

                print()

                return 0

            # ------------------------------------------------
            # CHANGE TICKERS
            # ------------------------------------------------

            if choice == "6":

                clear_screen()

                show_header()

                new_tickers = get_tickers()

                if new_tickers:

                    tickers = new_tickers

                    print(
                        green(
                            "  ✓ Ticker selection updated:"
                        )
                    )

                    print(
                        white(
                            "  "
                            + " ".join(tickers)
                        )
                    )

                    print()

                    pause = safe_input(
                        cyan(
                            "  Press ENTER to continue..."
                        )
                    )

                    if pause is None:

                        return 0

                continue

            # ------------------------------------------------
            # VALIDATE RESEARCH MODE
            # ------------------------------------------------

            if choice not in {
                "1",
                "2",
                "3",
                "4",
                "5",
                "8",
            }:

                print()
                print(
                    red(
                        "  ✖ Invalid selection."
                    )
                )

                print(
                    yellow(
                        "  Choose an option from 1-7."
                    )
                )

                pause = safe_input(
                    cyan(
                        "\n  Press ENTER to continue..."
                    )
                )

                if pause is None:

                    return 0

                continue

            # ------------------------------------------------
            # RUN RESEARCH
            # ------------------------------------------------

            run_research(
                tickers,
                choice,
            )

            # ------------------------------------------------
            # RETURN TO MENU
            # ------------------------------------------------

            pause = safe_input(
                cyan(
                    "\n  Press ENTER to return to MEGASTOCKS..."
                )
            )

            if pause is None:

                return 0

            break


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        raise SystemExit(
            main()
        )

    except KeyboardInterrupt:

        print()
        print()
        print(
            orange(
                "╔══════════════════════════════════════════════════════════════╗"
            )
        )

        print(
            orange(
                "║              🛑 MEGATRON // STOPPED                       ║"
            )
        )

        print(
            orange(
                "╚══════════════════════════════════════════════════════════════╝"
            )
        )

        print()

        print(
            yellow(
                "  Research stopped by user."
            )
        )

        print(
            green(
                "  No automatic trade was executed."
            )
        )

        print()
