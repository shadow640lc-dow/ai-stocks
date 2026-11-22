from __future__ import annotations

"""Alpaca execution layer for the MEGATRON tools.

Explicit, confirmed, real order placement.

The module talks to the Alpaca Trading API. Alpaca exposes two families
of keys:

    - Trading API     -> api.alpaca.markets      (this module)
    - Broker API      -> broker-api.alpaca.markets (out of scope here)

Environment variables:
    ALPACA_API_KEY      Alpaca Trading API key id.
    ALPACA_SECRET_KEY   Alpaca Trading API secret.
    ALPACA_MODE         live | paper   (default: live)
    ALPACA_MAX_NOTIONAL Maximum dollar size of one order in $ (safe cap).

Every caller must confirm before placing a real order. This module
never executes on its own.
"""

import os
import time
from typing import Any

import requests

RETRYABLE = {429, 500, 502, 503, 504}


class AlpacaError(RuntimeError):
    """Raised when the Alpaca API rejects a request."""


class AlpacaBroker:
    """Thin, explicit client for the Alpaca Trading API."""

    PAPER_URL = "https://paper-api.alpaca.markets"
    LIVE_URL = "https://api.alpaca.markets"

    def __init__(self, mode: str | None = None) -> None:
        self.api_key = os.getenv("ALPACA_API_KEY", "").strip()
        self.secret_key = os.getenv("ALPACA_SECRET_KEY", "").strip()
        self.mode = (mode or os.getenv("ALPACA_MODE", "live")).strip().lower()
        self.max_notional = self._env_float("ALPACA_MAX_NOTIONAL", 0.0)

        if self.mode not in {"live", "paper"}:
            raise ValueError("ALPACA_MODE must be 'live' or 'paper'")

        self.base_url = (
            self.LIVE_URL if self.mode == "live" else self.PAPER_URL
        )

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        raw = os.getenv(name, "").strip()
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.secret_key)

    @property
    def label(self) -> str:
        return self.mode.upper()

    def _headers(self) -> dict[str, str]:
        if not self.configured:
            raise AlpacaError(
                "Alpaca not configured. Set ALPACA_API_KEY and "
                "ALPACA_SECRET_KEY in the .env file."
            )
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type": "application/json",
        }

    # ================================================================
    # HTTP
    # ================================================================

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        dry_run: bool = False,
        retries: int = 0,
    ) -> Any:
        url = f"{self.base_url}{path}"

        if dry_run:
            return {
                "_dry_run": True,
                "mode": self.mode,
                "method": method,
                "path": path,
                "params": params,
                "payload": payload,
            }

        response = None
        for attempt in range(retries + 1):
            try:
                response = requests.request(
                    method,
                    url,
                    params=params,
                    json=payload,
                    headers=self._headers(),
                    timeout=15,
                )
            except requests.RequestException as exc:
                if attempt < retries:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                raise AlpacaError(f"Alpaca connection failed: {exc}") from exc
            if response.status_code in RETRYABLE and attempt < retries:
                time.sleep(min(2 ** attempt, 8))
                continue
            break

        if response is None:
            raise AlpacaError(f"Alpaca request to {path} produced no response")

        if response.status_code >= 400:
            body = response.text
            try:
                data = response.json()
                message = data.get("message") or data.get("detail") or body
            except ValueError:
                message = body
            raise AlpacaError(
                f"Alpaca {response.status_code} on {path}: {message}"
            )

        if response.status_code == 204 or not response.text:
            return {}

        try:
            return response.json()
        except ValueError:
            return response.text

    # ================================================================
    # ACCOUNT / MARKET STATE
    # ================================================================

    def account(self, *, dry_run: bool = False) -> dict[str, Any]:
        return self._request("GET", "/v2/account", dry_run=dry_run, retries=2)

    def clock(self, *, dry_run: bool = False) -> dict[str, Any]:
        return self._request("GET", "/v2/clock", dry_run=dry_run, retries=2)

    def market_is_open(self, *, dry_run: bool = False) -> bool:
        data = self.clock(dry_run=dry_run)
        return bool(data.get("is_open"))

    def positions(self, *, dry_run: bool = False) -> list[dict[str, Any]]:
        return self._request("GET", "/v2/positions", dry_run=dry_run, retries=2)

    def asset(
        self,
        symbol: str,
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/v2/assets/{symbol}",
            dry_run=dry_run,
            retries=2,
        )

    def asset_is_tradable(
        self,
        symbol: str,
        *,
        dry_run: bool = False,
    ) -> tuple[bool, str]:
        data = self.asset(symbol, dry_run=dry_run)
        if dry_run:
            return True, "dry-run"
        asset_class = data.get("asset_class")
        status = data.get("status")
        tradable = bool(
            data.get("tradable")
            and status in {"active", "tradable"}
        )
        if not tradable:
            return False, (
                f"{symbol} is not tradable on Alpaca "
                f"(status={status}, class={asset_class}, "
                f"tradable={data.get('tradable')})"
            )
        shortable = bool(data.get("shortable"))
        return True, shortable

    def buying_power(self, *, dry_run: bool = False) -> float:
        data = self.account(dry_run=dry_run)
        if dry_run:
            return 0.0
        raw = data.get("buying_power", data.get("cash", 0))
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0

    # ================================================================
    # ORDERS
    # ================================================================

    def place_order(
        self,
        *,
        symbol: str,
        qty: int,
        side: str,
        order_type: str = "market",
        time_in_force: str = "day",
        extend_hours: bool = False,
        limit_price: float | None = None,
        stop_price: float | None = None,
        asset_class: str | None = None,
        client_order_id: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Place a single order. Confirmation is the caller's job."""
        side = side.lower()
        if side not in {"buy", "sell"}:
            raise ValueError(f"side must be buy or sell, got {side!r}")
        if order_type not in {"market", "limit", "stop", "stop_limit"}:
            raise ValueError(f"unsupported order type {order_type!r}")
        qty = int(qty)
        if qty <= 0:
            raise ValueError("qty must be a positive integer")

        payload: dict[str, Any] = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": order_type,
            "time_in_force": time_in_force,
            "extended_hours": bool(extend_hours),
            "position_intent": "replace",
        }
        if client_order_id:
            payload["client_order_id"] = str(client_order_id)[:48]
        if asset_class:
            payload["asset_class"] = asset_class
        else:
            payload["asset_class"] = (
                "option" if self._looks_like_option_symbol(symbol) else "us_equity"
            )
        if limit_price is not None and order_type in {
            "limit",
            "stop_limit",
        }:
            payload["limit_price"] = f"{limit_price:.2f}"
        if stop_price is not None and order_type in {
            "stop",
            "stop_limit",
        }:
            payload["stop_price"] = f"{stop_price:.2f}"

        return self._request(
            "POST",
            "/v2/orders",
            payload=payload,
            dry_run=dry_run,
        )

    def orders(
        self,
        *,
        status: str = "open",
        limit: int = 100,
        dry_run: bool = False,
    ) -> list[dict[str, Any]]:
        """List orders so callers can prevent duplicate submissions."""
        return self._request(
            "GET",
            "/v2/orders",
            params={"status": status, "limit": max(1, min(int(limit), 500)), "direction": "desc"},
            dry_run=dry_run,
            retries=2,
        )

    def order(self, order_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        if not str(order_id).strip():
            raise ValueError("order_id is required")
        return self._request(
            "GET",
            f"/v2/orders/{order_id}",
            dry_run=dry_run,
            retries=2,
        )

    def cancel_order(self, order_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        """Cancel one order. Never retried: cancellation is not idempotent here."""
        if not str(order_id).strip():
            raise ValueError("order_id is required")
        return self._request("DELETE", f"/v2/orders/{order_id}", dry_run=dry_run)

    def close_position(
        self,
        symbol: str,
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        return self._request(
            "DELETE",
            f"/v2/positions/{symbol}",
            dry_run=dry_run,
        )

    # ================================================================
    # SANITY CHECKS
    # ================================================================

    def enforce_notional_cap(
        self,
        approximate_notional_usd: float,
    ) -> None:
        """Refuse to move forward if the cap is exceeded."""
        if self.max_notional <= 0:
            return
        if approximate_notional_usd > self.max_notional:
            raise AlpacaError(
                f"FUND_SAFETY: order estimate ${approximate_notional_usd:,.2f} "
                f"exceeds ALPACA_MAX_NOTIONAL ${self.max_notional:,.2f}. "
                "Refusing to place the order."
            )

    @staticmethod
    def _looks_like_option_symbol(symbol: str) -> bool:
        """OCC option symbols look like AAPL260116C00240000."""
        import re

        return bool(
            re.fullmatch(
                r"[A-Z]{1,6}\d{6}[CP]\d{8}",
                symbol.strip().upper(),
            )
        )