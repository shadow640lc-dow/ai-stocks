"""Safety tests for the Alpaca execution path. No broker calls are made."""

import json

import pytest

import src.execution.alpaca_executor as executor
from src.utils.alpaca_broker import AlpacaBroker, AlpacaError


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = json.dumps(self._payload) if self._payload else ""

    def json(self):
        return self._payload


class DuplicateBroker:
    configured = True
    label = "PAPER"
    max_notional = 0.0

    def market_is_open(self):
        return True

    def asset_is_tradable(self, symbol):
        return True, True

    def enforce_notional_cap(self, notional):
        return None

    def orders(self, *, status="open"):
        return [{"id": "dup-1", "symbol": "AMD", "side": "buy", "status": "new"}]

    def place_order(self, **_kwargs):
        raise AssertionError("a duplicate must never reach place_order")


class PlacingBroker(DuplicateBroker):
    def __init__(self):
        self.placed = []

    def orders(self, *, status="open"):
        return []

    def place_order(self, **kwargs):
        self.placed.append(kwargs)
        return {"id": "ord-1", "status": "accepted"}


@pytest.fixture(autouse=True)
def _live_on(monkeypatch):
    monkeypatch.setattr("src.utils.live_switch.live_trading_enabled", lambda: True)


def test_duplicate_open_order_is_skipped_and_audited(tmp_path, monkeypatch):
    audit = tmp_path / "execution_audit.jsonl"
    monkeypatch.setattr(executor, "AUDIT_PATH", audit)

    results = executor.execute_hedge_fund_decisions(
        {"AMD": {"action": "buy", "quantity": 1}},
        DuplicateBroker(),
        confirm=lambda *args: (_ for _ in ()).throw(AssertionError("confirm must not run")),
    )

    assert results[0]["status"] == "skipped_duplicate_order"
    assert results[0]["duplicate_of"] == "dup-1"
    records = [json.loads(line) for line in audit.read_text().splitlines()]
    assert any(record.get("status") == "skipped_duplicate_order" for record in records)
    assert records[-1]["event"] == "run_complete"


def test_order_is_placed_with_client_id_and_audited(tmp_path, monkeypatch):
    audit = tmp_path / "execution_audit.jsonl"
    monkeypatch.setattr(executor, "AUDIT_PATH", audit)
    broker = PlacingBroker()

    results = executor.execute_hedge_fund_decisions(
        {"AMD": {"action": "buy", "quantity": 2}},
        broker,
        confirm=lambda *args: True,
        prices={"AMD": 100.0},
    )

    assert results[0]["status"] == "placed"
    assert broker.placed[0]["client_order_id"].startswith("megatron-buy-")
    records = [json.loads(line) for line in audit.read_text().splitlines()]
    assert any(record.get("status") == "placed" and record.get("order_id") == "ord-1" for record in records)


def test_get_retries_but_post_does_not(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")
    monkeypatch.setattr("src.utils.alpaca_broker.time.sleep", lambda _seconds: None)

    calls = []
    responses = [FakeResponse(429), FakeResponse(200, {"status": "ACTIVE"})]

    def fake_request(method, url, **_kwargs):
        calls.append((method, url))
        return responses.pop(0)

    monkeypatch.setattr("src.utils.alpaca_broker.requests.request", fake_request)

    broker = AlpacaBroker(mode="paper")
    assert broker.account()["status"] == "ACTIVE"
    assert [method for method, _ in calls] == ["GET", "GET"]

    calls.clear()

    def always_429(method, url, **_kwargs):
        calls.append((method, url))
        return FakeResponse(429)

    monkeypatch.setattr("src.utils.alpaca_broker.requests.request", always_429)
    with pytest.raises(AlpacaError):
        broker.place_order(symbol="AMD", qty=1, side="buy")
    assert len(calls) == 1, "order submission must never be retried"


def test_orders_order_and_cancel_hit_expected_endpoints(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")
    seen = []

    def fake_request(method, url, **kwargs):
        seen.append((method, url, kwargs.get("params")))
        if url.endswith("/v2/orders") and method == "GET":
            return FakeResponse(200, [{"id": "ord-1"}])
        if method == "DELETE":
            return FakeResponse(204)
        return FakeResponse(200, {"id": "ord-1", "status": "filled"})

    monkeypatch.setattr("src.utils.alpaca_broker.requests.request", fake_request)
    broker = AlpacaBroker(mode="paper")

    assert broker.orders(status="open", limit=5) == [{"id": "ord-1"}]
    assert broker.order("ord-1")["status"] == "filled"
    broker.cancel_order("ord-1")

    assert seen[0][0] == "GET" and seen[0][1].endswith("/v2/orders")
    assert seen[0][2]["status"] == "open"
    assert seen[1][1].endswith("/v2/orders/ord-1")
    assert seen[2][0] == "DELETE" and seen[2][1].endswith("/v2/orders/ord-1")
