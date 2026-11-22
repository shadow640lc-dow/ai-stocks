#!/usr/bin/env python3
"""
MEGATRON // COVERED CALL HUNTER

Interactive launcher for the existing covered-call scanner.

Features:
- Neon-purple terminal interface
- Single or multiple ticker input
- Conservative/liquid scan
- Wider candidate scan
- Test-universe scan
- Existing scanner remains responsible for research
- NO order execution
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


# ============================================================
# MEGATRON CONFIG
# ============================================================

ROOT = Path(__file__).resolve().parent


# ============================================================
# TERMINAL COLORS
# ============================================================

def purple(text: str) -> str:
    """Neon purple / magenta."""
    return f"\033[38;5;213m{text}\033[0m"


def purple_dark(text: str) -> str:
    """Darker purple."""
    return f"\033[38;5;129m{text}\033[0m"


def cyan(text: str) -> str:
    """Cyan."""
    return f"\033[96m{text}\033[0m"


def green(text: str) -> str:
    """Green."""
    return f"\033[92m{text}\033[0m"


def yellow(text: str) -> str:
    """Yellow."""
    return f"\033[93m{text}\033[0m"


def red(text: str) -> str:
    """Red."""
    return f"\033[91m{text}\033[0m"


def white(text: str) -> str:
    """White."""
    return f"\033[97m{text}\033[0m"


def dim(text: str) -> str:
    """Dim terminal text."""
    return f"\033[2m{text}\033[0m"


def reset() -> str:
    return "\033[0m"


# ============================================================
# UI HELPERS
# ============================================================

def clear_screen() -> None:
    os.system("clear")


def safe_input(prompt: str) -> str | None:
    """
    Input wrapper that handles Ctrl+C and EOF cleanly.

    Returns None when the user cancels.
    """

    try:
        return input(prompt)

    except (KeyboardInterrupt, EOFError):
        print()
        print(yellow("  🛑 MEGACALLS operation cancelled."))
        return None


def print_banner() -> None:
    """Main MEGACALLS banner."""

    print()
    print(purple("╔══════════════════════════════════════════════════════════════╗"))
    print(purple("║                                                              ║"))
    print(purple("║          📞 MEGATRON // COVERED CALL HUNTER                 ║"))
    print(purple("║                                                              ║"))
    print(purple("║             AI OPTIONS RESEARCH TERMINAL                    ║"))
    print(purple("║                                                              ║"))
    print(purple("╠══════════════════════════════════════════════════════════════╣"))
    print(purple("║ ") + white("Research • Screening • Candidate Discovery") +
          purple("              ║"))
    print(purple("║ ") + dim("No automatic order execution") +
          purple("                         ║"))
    print(purple("╚══════════════════════════════════════════════════════════════╝"))
    print()


def print_status() -> None:
    """System status panel."""

    print(purple("┌─ SYSTEM STATUS"))
    print(purple("│"))
    print(green("│  ● Market / Option Data     READY"))
    print(green("│  ● Covered Call Scanner     READY"))
    print(green("│  ● Candidate Ranking        READY"))
    print(cyan("│  ● Research Mode            ACTIVE"))
    print(yellow("│  🛡 Order Execution          DISABLED"))
    print(purple("│"))
    print(purple("└────────────────────────────────────────────────────────────"))
    print()


def print_scan_modes() -> None:
    """Display available scanner modes."""

    print(purple("┌─ 📞 COVERED CALL SCAN MODES"))
    print(purple("│"))
    print(cyan("│  [1] ") + white("Conservative / Liquid"))
    print(dim("│       Higher liquidity requirements"))
    print()
    print(cyan("│  [2] ") + white("Wider Candidate Search"))
    print(dim("│       Broader option candidate pool"))
    print()
    print(cyan("│  [3] ") + white("Test Universe"))
    print(dim("│       Scanner test universe"))
    print()
    print(cyan("│  [4] ") + white("Change Ticker(s)"))
    print()
    print(cyan("│  [5] ") + white("⚡ Scan + Alpaca Execution"))
    print(dim("│       Confirmed covered-call orders on Alpaca"))
    print()
    print(cyan("│  [6] ") + white("Exit"))
    print()
    print(purple("└────────────────────────────────────────────────────────────"))
    print()


def print_ticker_help() -> None:
    """Explain ticker input."""

    print(purple("┌─ TICKER INPUT"))
    print(purple("│"))
    print(white("│  Enter one ticker:"))
    print(cyan("│      NVDA"))
    print()
    print(white("│  Or scan multiple tickers:"))
    print(cyan("│      NVDA AMD PLTR MSFT"))
    print()
    print(white("│  Commas also work:"))
    print(cyan("│      NVDA, AMD, PLTR"))
    print()
    print(purple("└────────────────────────────────────────────────────────────"))
    print()


# ============================================================
# SCANNER COMMAND
# ============================================================

def build_command(tickers: list[str], choice: str, *, alpaca: bool = False) -> list[str] | None:
    """
    Build the command for the existing covered-call scanner.

    This function DOES NOT execute anything.

    When alpaca=True the scanner appends --alpaca so that after the
    research output it offers a confirmed covered-call execution.
    """

    if choice == "1":
        base = [
            "poetry",
            "run",
            "python",
            "-m",
            "app.backend.services.covered_call_scanner",
            *tickers,
            "--top",
            "10",
            "--min-volume",
            "100",
            "--min-oi",
            "500",
        ]

    elif choice == "2":
        base = [
            "poetry",
            "run",
            "python",
            "-m",
            "app.backend.services.covered_call_scanner",
            *tickers,
            "--top",
            "15",
            "--min-volume",
            "50",
            "--min-oi",
            "250",
        ]

    elif choice == "3":
        base = [
            "poetry",
            "run",
            "python",
            "-m",
            "app.backend.services.covered_call_scanner",
            "--universe",
            "test",
            "--limit",
            "3",
            "--top",
            "5",
        ]

    else:
        return None

    if alpaca:
        base = base + ["--alpaca"]

    return base


# ============================================================
# RUN SCANNER
# ============================================================

def run_scanner(args: list[str], *, live: bool = False) -> int:
    """Launch the existing covered-call scanner."""

    print()
    print(purple("╔══════════════════════════════════════════════════════════════╗"))
    print(purple("║             📞 MEGATRON // SCAN LAUNCH                     ║"))
    print(purple("╚══════════════════════════════════════════════════════════════╝"))
    print()

    print(cyan("  Engine:   ") + white("Covered Call Hunter"))
    if live:
        print(cyan("  Status:   ") + red("CONFIRMED ALPACA EXECUTION QUEUED"))
        print(cyan("  Trading:  ") + yellow("EXECUTION ON APPROVAL ONLY"))
    else:
        print(cyan("  Status:   ") + green("RESEARCH MODE"))
        print(cyan("  Trading:  ") + yellow("DISABLED"))
    print()

    print(purple("  Command:"))
    print(dim("  " + " ".join(args)))
    print()

    print(purple("  Launching scanner..."))
    print()

    try:
        return subprocess.call(args, cwd=ROOT)

    except FileNotFoundError as exc:
        print()
        print(red("  ✖ Unable to launch scanner."))
        print(red(f"  {exc}"))
        print()
        return 1

    except KeyboardInterrupt:
        print()
        print(yellow("  🛑 Scanner interrupted by user."))
        print()
        return 130


# ============================================================
# TICKER INPUT
# ============================================================

def get_tickers() -> list[str] | None:
    """Get and validate ticker input."""

    print_ticker_help()

    raw = safe_input(
        cyan("  📈 Ticker(s): ")
    )

    if raw is None:
        return None

    raw = raw.strip().upper()

    if not raw:
        print()
        print(red("  ✖ No ticker entered."))
        return None

    # Support commas and spaces.
    tickers = raw.replace(",", " ").split()

    # Remove duplicates while preserving order.
    unique_tickers: list[str] = []

    for ticker in tickers:
        if ticker not in unique_tickers:
            unique_tickers.append(ticker)

    if not unique_tickers:
        print()
        print(red("  ✖ No valid ticker input found."))
        return None

    print()
    print(purple("  Selected ticker(s): ") +
          white(", ".join(unique_tickers)))
    print()

    return unique_tickers


# ============================================================
# MAIN MENU
# ============================================================

def main_menu(tickers: list[str]) -> str:
    """Display the main scan menu."""

    print(purple("╔══════════════════════════════════════════════════════════════╗"))
    print(purple("║                 📞 MEGACALLS CONTROL                         ║"))
    print(purple("╚══════════════════════════════════════════════════════════════╝"))
    print()

    print(cyan("  Selected: ") + white(", ".join(tickers)))
    print()

    print_scan_modes()

    choice = safe_input(
        cyan("  Select: ")
    )

    if choice is None:
        return "6"

    return choice.strip()


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    clear_screen()

    print_banner()
    print_status()

    tickers = get_tickers()

    if not tickers:
        print()
        print(yellow("  MEGACALLS standing by. 👊"))
        return 1

    while True:

        clear_screen()

        print_banner()

        print(
            purple("  SELECTED TICKER(S): ")
            + white(", ".join(tickers))
        )
        print()

        choice = main_menu(tickers)

        # ----------------------------------------------------
        # CHANGE TICKER
        # ----------------------------------------------------

        if choice == "4":

            clear_screen()

            print_banner()

            new_tickers = get_tickers()

            if new_tickers:
                tickers = new_tickers
                print(
                    green("  ✓ Updated ticker selection: ")
                    + white(", ".join(tickers))
                )

            if safe_input(
                cyan("\n  Press ENTER to continue...")
            ) is None:
                return 0

            continue

        # ----------------------------------------------------
        # EXIT
        # ----------------------------------------------------

        if choice == "6":

            print()
            print(purple("╔══════════════════════════════════════════════════════════════╗"))
            print(purple("║                                                              ║"))
            print(purple("║          📞 MEGACALLS // STANDING BY                        ║"))
            print(purple("║                                                              ║"))
            print(purple("║          No orders were executed.                            ║"))
            print(purple("║                                                              ║"))
            print(purple("╚══════════════════════════════════════════════════════════════╝"))
            print()

            return 0

        # ----------------------------------------------------
        # BUILD SCANNER COMMAND
        # ----------------------------------------------------

        live = choice == "5"

        if live:
            mode_pick = safe_input(
                cyan("\n  Conservative(1) or Wider(2) scan for execution? ")
            )

            if mode_pick is None:
                return 0

            scan_choice = (
                "1" if mode_pick.strip() == "1" else "2"
            )
            args = build_command(tickers, scan_choice, alpaca=True)

        else:
            args = build_command(tickers, choice)

        if args is None:
            print()
            print(red("  ✖ Invalid selection."))
            print(yellow("  Choose 1, 2, 3, 4, 5, or 6."))
            if safe_input(
                cyan("\n  Press ENTER to continue...")
            ) is None:
                return 0

            continue

        # ----------------------------------------------------
        # RUN EXISTING ENGINE
        # ----------------------------------------------------

        result = run_scanner(args, live=live)

        print()

        if result == 0:
            print(green("  ✓ MEGACALLS scan completed."))

        elif result == 130:
            print(yellow("  🛑 MEGACALLS scan stopped by user."))

        else:
            print(red(f"  ⚠ Scanner exited with code {result}."))

        print()

        if live:

            print(purple("  Execution was offered only with explicit approval."))

        else:

            print(purple("  Research complete. No automatic trade execution."))
        print()

        if safe_input(
            cyan("  Press ENTER to return to MEGACALLS...")
        ) is None:
            return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    raise SystemExit(main())
