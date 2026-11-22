#!/usr/bin/env python3
"""MEGATRON live-trading kill switch.

Usage:
    live            -> show status
    live on         -> enable live trading (writes ON)
    live off        -> disable live trading (writes OFF)

Every real-money path (megastocks --alpaca, megacalls --alpaca,
Scout webhook execution, megacrypto Solana swap) refuses to execute
until the switch reads ON.
"""
from __future__ import annotations

import sys

from src.utils.live_switch import (
    SWITCH_FILE,
    live_trading_enabled,
    print_switch_status,
    set_live_trading,
)

CYAN = "\033[36m"
GREEN = "\033[32m"
RED = "\033[31m"
NORMAL = "\033[0m"
BOLD = "\033[1m"


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]

    if not args:
        print_switch_status()
        return 0 if live_trading_enabled() else 1

    action = args[0].strip().lower()

    if action == "on":
        set_live_trading(True)
        print(f"{GREEN}{BOLD}LIVE TRADING: ON{NORMAL}")
        print("  All live paths are now allowed to execute (with confirmation).")
        print(f"  Switch: {RED}{SWITCH_FILE}{NORMAL}")
        return 0

    if action == "off":
        set_live_trading(False)
        print(f"{RED}{BOLD}LIVE TRADING: OFF{NORMAL}")
        print("  All live paths will now refuse to execute.")
        return 0

    if action == "status":
        print_switch_status()
        return 0 if live_trading_enabled() else 1

    print(f"  ✖ Unknown action: {action!r}. Use: on | off | status", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())