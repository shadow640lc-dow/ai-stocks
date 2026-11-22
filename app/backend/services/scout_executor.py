from __future__ import annotations

"""Opt-in, env-gated execution for AI Scout alert webhooks.

This path is OFF unless SCOUT_EXECUTION_ENABLED=true AND the alert
carries the matching SCOUT_EXECUTION_SECRET. Every gate below must
pass or execution is refused with a clear reason.
"""

import logging
import os

from app.backend.models.scout import ScoutAlert
from src.utils.alpaca_broker import AlpacaBroker, AlpacaError

logger = logging.getLogger(__name__)

_ACTION_TO_SIDE = {
    "buy": "buy",
    "sell": "sell",
    "short": "sell",
    "cover": "buy",
}

_EXECUTABLE_ACTIONS = {"buy", "sell", "short", "cover"}


def _env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() == "true"


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def maybe_execute_scout_order(
    alert: ScoutAlert,
    result: dict,
) -> dict:
    """Attempt a uniform, capped Alpaca order for a Scout alert.

    Returns an "execution" dict that is safe to embed in the webhook
    response. Never raises on refusal paths.
    """

    execution: dict = {
        "requested": bool(alert.execute),
        "approved": False,
        "status": "NOT_ATTEMPTED",
        "reason": "",
    }

    gates: list[str] = []

    if not alert.execute:
        execution["status"] = "NOT_REQUESTED"
        execution["reason"] = "alert did not request execution"
        return execution

    if not _env_bool("SCOUT_EXECUTION_ENABLED"):
        execution["status"] = "REFUSED"
        execution["reason"] = (
            "SCOUT_EXECUTION_ENABLED is not set to true"
        )
        return execution

    from src.utils.live_switch import live_trading_enabled

    if not live_trading_enabled():
        execution["status"] = "REFUSED"
        execution["reason"] = (
            "LIVE-KILL-SWITCH: live trading is OFF "
            "(run `live on` to enable)"
        )
        return execution

    expected_secret = os.getenv("SCOUT_EXECUTION_SECRET", "").strip()
    if not expected_secret:
        execution["status"] = "REFUSED"
        execution["reason"] = "SCOUT_EXECUTION_SECRET is not configured"
        return execution

    if not alert.secret or alert.secret != expected_secret:
        execution["status"] = "REFUSED"
        execution["reason"] = "execution secret mismatch"
        return execution

    action = str(alert.action or "").lower()
    if action not in _EXECUTABLE_ACTIONS:
        execution["status"] = "REFUSED"
        execution["reason"] = f"action {action!r} is not executable"
        return execution

    if int(alert.qty or 0) <= 0:
        execution["status"] = "REFUSED"
        execution["reason"] = "qty must be a positive integer"
        return execution

    classification = str(result.get("classification", "WATCH")).upper()
    if classification not in {"HIGH_INTEREST", "INVESTIGATE"}:
        execution["status"] = "REFUSED"
        execution["reason"] = (
            f"classification {classification} is below the execution bar"
        )
        return execution

    validation_status = ""
    try:
        validation_status = str(
            result.get("alert_validation", {}).get("status", "")
        ).upper()
    except (AttributeError, ValueError):
        validation_status = ""
    if validation_status in {"PRICE_MISMATCH", "ALERT_DISCREPANCY"}:
        execution["status"] = "REFUSED"
        execution["reason"] = f"alert data conflicted ({validation_status})"
        return execution

    ticker = str(alert.ticker).upper().strip()
    qty = int(alert.qty)
    side = _ACTION_TO_SIDE[action]

    try:
        market_data = result.get("market_data") or {}
        price = market_data.get("price")
        notional = float(price) * qty if price else 0.0

        broker = AlpacaBroker()

        gates.append(f"mode={broker.label}")

        if not broker.configured:
            execution["status"] = "REFUSED"
            execution["reason"] = "Alpaca keys are not configured"
            return execution

        if not broker.market_is_open():
            execution["status"] = "REFUSED"
            execution["reason"] = "US market is closed"
            return execution

        max_notional = broker.max_notional
        if max_notional > 0 and notional > max_notional:
            execution["status"] = "REFUSED"
            execution["reason"] = (
                f"notional ${notional:,.0f} exceeds "
                f"ALPACA_MAX_NOTIONAL ${max_notional:,.0f}"
            )
            return execution

        tradable, shortable = broker.asset_is_tradable(ticker)
        if not tradable:
            execution["status"] = "REFUSED"
            execution["reason"] = f"{ticker} is not tradable"
            return execution
        if action == "short" and not shortable:
            execution["status"] = "REFUSED"
            execution["reason"] = f"{ticker} is not shortable"
            return execution

        order = broker.place_order(
            symbol=ticker,
            qty=qty,
            side=side,
            time_in_force="day",
        )

        execution.update(
            {
                "approved": True,
                "status": "ORDER_SUBMITTED",
                "reason": "all gates passed",
                "ticker": ticker,
                "action": action,
                "side": side,
                "qty": qty,
                "est_notional": notional,
                "gates": gates,
                "order": {
                    "id": order.get("id"),
                    "status": order.get("status"),
                    "filled_qty": order.get("filled_qty"),
                    "avg_fill_price": order.get("avg_fill_price"),
                },
            }
        )
        return execution

    except AlpacaError as exc:
        execution["status"] = "ERROR"
        execution["reason"] = f"Alpaca call failed: {exc}"
        return execution
    except Exception as exc:
        logger.exception("Scout execution failed")
        execution["status"] = "ERROR"
        execution["reason"] = f"unexpected failure: {exc}"
        return execution