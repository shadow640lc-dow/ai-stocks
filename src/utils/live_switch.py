from __future__ import annotations

"""MEGATRON master live-trading kill switch.

A single on/off gate every real-money path checks before executing.

The switch is a plain file at <repo>/.live_trading containing "ON" or
"OFF". The file is the single source of truth so you can flip live
trading instantly (no editing .env, no restart of long-lived processes):

    live on     -> write "ON"  (enable)
    live off    -> write "OFF" (disable)
    live status -> show the current state

Rules:
    - The switch defaults to OFF when the file is missing or unreadable.
    - Every execution layer (Alpaca AIHF, covered calls, Scout webhook,
      Solana swap) checks is_live_trading_enabled() as the FIRST gate.
    - Turning it OFF while a process is mid-run refuses further orders;
      a single already-approved order is not revoked, but nothing new
      gets signed or broadcast.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SWITCH_FILE = ROOT / ".live_trading"

ON_TEXT = "ON"
OFF_TEXT = "OFF"
NORMAL = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"


def _read_state() -> str:
    """Return the raw (stripped, uppercased) switch file contents."""
    try:
        if not SWITCH_FILE.exists():
            return ""
        return SWITCH_FILE.read_text(encoding="utf-8").strip().upper()
    except OSError:
        return ""


def live_trading_enabled() -> bool:
    """True only when the switch file explicitly reads ON."""
    return _read_state() == ON_TEXT


def live_trading_reason() -> str:
    """Human-readable explanation of the current state."""
    state = _read_state()
    if state == ON_TEXT:
        return "live trading is ON (enabled)"
    return f"live trading is OFF (set {SWITCH_FILE} to ON to enable)"


def set_live_trading(enabled: bool) -> None:
    """Flip the kill switch. Missing file => OFF."""
    SWITCH_FILE.parent.mkdir(parents=True, exist_ok=True)
    SWITCH_FILE.write_text(f"{ON_TEXT}\n" if enabled else f"{OFF_TEXT}\n", encoding="utf-8")


def print_switch_status() -> None:
    """Nice terminal status line used by `live status`."""
    on = live_trading_enabled()
    color = GREEN if on else RED
    state = "ON  (live trading ENABLED)" if on else "OFF (live trading DISABLED)"
    print(f"{color}{BOLD}[LIVE] {NORMAL}{state}")
    print(f"  switch file: {SWITCH_FILE}")
    print(f"  reason:      {live_trading_reason()}")