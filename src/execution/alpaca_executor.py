from __future__ import annotations

"""Convert AI Hedge Fund decisions into confirmed Alpaca orders.

Only invoked when the user passes --alpaca and then approves every
individual order. Nothing here executes without the confirm callback
returning True.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from src.utils.alpaca_broker import AlpacaBroker, AlpacaError

ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = ROOT / "logs" / "execution_audit.jsonl"

_ACTION_TO_SIDE: dict[str, str] = {
    "buy": "buy",
    "sell": "sell",
    "short": "sell",
    "cover": "buy",
}

_SHORT_ACTIONS = {"short"}

ConfirmFn = Callable[
    [str, str, str, int, float],
    bool,
]


def estimate_notional(
    ticker: str,
    qty: int,
    prices: dict[str, float] | None,
) -> float:
    if not prices:
        return 0.0
    price = prices.get(ticker)
    if not price:
        return 0.0
    return float(price) * int(qty)


def _audit(record: dict[str, Any]) -> None:
    """Append one order event. Never raises into the execution path."""
    try:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"ts": datetime.now(timezone.utc).isoformat(), **record}, default=str)
        with AUDIT_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        os.chmod(AUDIT_PATH, 0o600)
    except OSError as exc:
        print(f"      ! audit log unavailable: {exc}")


def _open_order_for(broker: AlpacaBroker, ticker: str, side: str) -> dict[str, Any] | None:
    """Return an existing open order for the same symbol/side, if any."""
    try:
        open_orders = broker.orders(status="open")
    except (AlpacaError, AttributeError, TypeError):
        return None
    for order in open_orders or []:
        if not isinstance(order, dict):
            continue
        if str(order.get("symbol", "")).upper() == ticker.upper() and str(order.get("side", "")).lower() == side:
            return order
    return None


def execute_hedge_fund_decisions(
    decisions: dict[str, dict[str, Any]],
    broker: AlpacaBroker,
    *,
    confirm: ConfirmFn,
    prices: dict[str, float] | None = None,
    allow_closed_market: bool = False,
) -> list[dict[str, Any]]:
    """Place (or refuse to place) orders for every non-hold decision.

    confirm(ticker, action, side, qty, est_notional) must return True
    for an order to be placed.

    Returns a list of outcome records: one per orderable decision.
    """

    results: list[dict[str, Any]] = []

    if not broker.configured:
        raise AlpacaError(
            "Alpaca not configured. Set ALPACA_API_KEY and "
            "ALPACA_SECRET_KEY plus ALPACA_MODE in ~/ai-stocks/.env"
        )

    from src.utils.live_switch import live_trading_enabled

    if not live_trading_enabled():
        raise AlpacaError(
            "LIVE-KILL-SWITCH: live trading is OFF. "
            "Run `live on` to enable before placing real orders."
        )

    market_open = broker.market_is_open()
    if not market_open and not allow_closed_market:
        raise AlpacaError(
            "US market is closed. No orders placed. "
            "Pass allow_closed_market=True to override."
        )

    print()
    print("=" * 60)
    print(f"ALPACA LIVE EXECUTION PLAN   MODE: {broker.label}")
    print(f"Market open: {market_open}")
    print("=" * 60)

    for ticker, decision in decisions.items():
        action = str(decision.get("action", "hold")).lower()
        qty = int(decision.get("quantity") or 0)
        side = _ACTION_TO_SIDE.get(action)

        if action == "hold" or (action != "hold" and qty <= 0):
            results.append(
                {
                    "ticker": ticker,
                    "action": action,
                    "qty": qty,
                    "status": "skipped_no_qty",
                }
            )
            continue

        notional = estimate_notional(ticker, qty, prices)

        print()
        print(
            f"  {ticker:<6} {action.upper():<5} {qty} sh  "
            f"({'.' if notional else '-'}${notional:,.0f} est)"
        )

        # --- Safety gates ------------------------------------
        try:
            tradable, shortable = broker.asset_is_tradable(ticker)
        except AlpacaError:
            print(f"      ! asset lookup failed — skipping {ticker}")
            results.append(
                {
                    "ticker": ticker,
                    "action": action,
                    "qty": qty,
                    "status": "skipped_asset_check_failed",
                }
            )
            continue

        if not tradable:
            print(f"      ! {ticker} is not tradable on Alpaca — skipping")
            results.append(
                {
                    "ticker": ticker,
                    "action": action,
                    "qty": qty,
                    "status": "skipped_not_tradable",
                }
            )
            continue

        if action in _SHORT_ACTIONS and not shortable:
            print(f"      ! {ticker} is not shortable on Alpaca — skipping")
            results.append(
                {
                    "ticker": ticker,
                    "action": action,
                    "qty": qty,
                    "status": "skipped_not_shortable",
                }
            )
            continue

        if notional > 0:
            try:
                broker.enforce_notional_cap(notional)
            except AlpacaError as exc:
                print(f"      FUND_SAFETY: {exc} — skipping {ticker}")
                results.append(
                    {
                        "ticker": ticker,
                        "action": action,
                        "qty": qty,
                        "status": "skipped_cap",
                    }
                )
                continue

        # --- Duplicate protection ----------------------------
        duplicate = _open_order_for(broker, ticker, side)
        if duplicate is not None:
            print(
                f"      ! open {side} order already exists "
                f"(id={duplicate.get('id')}) — skipping duplicate"
            )
            results.append(
                {
                    "ticker": ticker,
                    "action": action,
                    "qty": qty,
                    "status": "skipped_duplicate_order",
                    "duplicate_of": duplicate.get("id"),
                }
            )
            continue

        # --- Confirmation ------------------------------------
        approved = confirm(ticker, action, side, qty, notional)

        if not approved:
            print(f"      ✗ declined by user")
            results.append(
                {
                    "ticker": ticker,
                    "action": action,
                    "qty": qty,
                    "status": "declined",
                }
            )
            continue

        try:
            order = broker.place_order(
                symbol=ticker,
                qty=qty,
                side=side,
                time_in_force="day",
                client_order_id=f"megatron-{action}-{uuid4().hex[:16]}",
            )
        except AlpacaError:
            print(f"      ✗ order rejected by Alpaca — skipping {ticker}")
            results.append(
                {
                    "ticker": ticker,
                    "action": action,
                    "qty": qty,
                    "status": "order_failed",
                }
            )
            continue

        order_id = order.get("id")
        submitted = order.get("status")
        print(
            f"      ✓ order placed  id={order_id}  status={submitted}"
        )
        results.append(
            {
                "ticker": ticker,
                "action": action,
                "qty": qty,
                "status": "placed",
                "order_id": order_id,
                "order_status": submitted,
            }
        )

    print("=" * 60)

    for result in results:
        _audit({"event": "order", "mode": broker.label, "market_open": market_open, **result})
    _audit(
        {
            "event": "run_complete",
            "mode": broker.label,
            "market_open": market_open,
            "decisions": len(decisions),
            "placed": sum(1 for item in results if item.get("status") == "placed"),
        }
    )

    return results