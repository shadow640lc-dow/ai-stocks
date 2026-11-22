"""Offline tests for empirical structured-output verification."""

from __future__ import annotations

import json

from src.ai import compatibility, preflight, verification
from src.ai.runtime_registry import HttpResult
from src.ai.types import ModelInfo, RuntimeInfo, Snapshot

SIGNAL = {"signal": "neutral", "confidence": 50, "reasoning": "capability test"}
RISK = {**SIGNAL, "max_position_size": 5}
DECISION = {
    "ticker": "TEST",
    "action": "hold",
    "quantity": 0,
    "confidence": 50,
    "reasoning": "capability test",
}
ANALYST_RESEARCH = {
    "ticker": "TEST",
    "analyst_signals": {
        "fundamentals": SIGNAL,
        "technical": SIGNAL,
        "news_sentiment": SIGNAL,
    },
}
VALID = {
    "multi_agent": DECISION,
    "analyst_research": ANALYST_RESEARCH,
    "fundamentals": SIGNAL,
    "technical": SIGNAL,
    "news_sentiment": SIGNAL,
    "portfolio_risk": RISK,
    "synthesis": DECISION,
    "backtesting": DECISION,
}


def make_model(**kwargs) -> ModelInfo:
    defaults = dict(
        id="ollama:test-model",
        name="test-model",
        runtime_id="ollama",
        provider="Ollama",
        local=True,
        installed=True,
        configured=True,
        size_bytes=1234,
        parameter_size="8B",
        context_length=32768,
        capabilities=frozenset({"chat"}),
        capabilities_source="runtime",
    )
    defaults.update(kwargs)
    return ModelInfo(**defaults)


def make_runtime(**kwargs) -> RuntimeInfo:
    defaults = dict(
        id="ollama",
        name="Ollama",
        kind="local",
        endpoint="http://localhost:11434",
        installed=True,
        running=True,
        reachable=True,
    )
    defaults.update(kwargs)
    return RuntimeInfo(**defaults)


def fake_http(overrides: dict[str, object] | None = None):
    overrides = overrides or {}
    calls: list[dict] = []

    def _http(method, url, payload=None, timeout=None):
        calls.append(payload or {})
        prompt = (payload or {}).get("prompt", "")
        task_id = next((key for key, value in verification.PROMPTS.items() if value == prompt), "")
        if task_id in overrides:
            value = overrides[task_id]
            return HttpResult(True, 200, {"response": value})
        return HttpResult(True, 200, {"response": json.dumps(VALID[task_id])})

    _http.calls = calls
    return _http


def test_validate_accepts_shapes_and_rejects_mismatches() -> None:
    assert verification.validate(SIGNAL, verification.SCHEMAS["fundamentals"]) == []
    errors = verification.validate({"signal": "sideways", "confidence": 150}, verification.SCHEMAS["technical"])
    assert any("not one of" in error for error in errors)
    assert any("above the maximum" in error for error in errors)
    assert any("reasoning" in error for error in errors)

    extra = {**SIGNAL, "unexpected": True}
    assert any("unexpected field" in error for error in verification.validate(extra, verification.SCHEMAS["technical"]))

    analyst = {**ANALYST_RESEARCH, "analyst_signals": {"fundamentals": SIGNAL}}
    missing = verification.validate(analyst, verification.SCHEMAS["analyst_research"])
    assert any("technical" in error for error in missing)


def test_all_profiles_pass_and_promote_to_ready(tmp_path) -> None:
    model = make_model()
    runtime = make_runtime()
    http = fake_http()

    report = verification.verify_model(model, runtime, http=http)
    assert report.passed is True
    assert report.verified_capabilities == ["json"]
    assert len(report.tasks) == 8
    assert all(check.ok for check in report.tasks)
    assert len(http.calls) == 8
    assert all("format" in call and isinstance(call["format"], dict) for call in http.calls)

    path = tmp_path / "ai_verification.json"
    verification.save_report(report, model, path=path)
    record = verification.load_record(model, path=path)
    assert record is not None
    verification.apply_record(model, record)

    assert model.capabilities == frozenset({"chat"})  # declared metadata is untouched
    assert model.verified_capabilities == frozenset({"json"})
    verdict = compatibility.evaluate(model, "analyst_research")
    assert verdict.status == compatibility.READY
    assert any("empirically verified" in note for note in verdict.notes)

    snapshot = Snapshot([runtime], 0.0, hardware=__import__("src.ai.types", fromlist=["Hardware"]).Hardware())
    runtime.models.append(model)
    gate = preflight.check(snapshot, model.id, task_id="multi_agent")
    assert gate.ok is True
    assert gate.status == compatibility.READY


def test_one_failing_profile_keeps_limitations_and_names_failure() -> None:
    model = make_model()
    report = verification.verify_model(
        model,
        make_runtime(),
        http=fake_http({"backtesting": json.dumps({"ticker": "TEST"})}),
    )
    assert report.passed is False
    assert report.verified_capabilities == []
    failed = [check for check in report.tasks if not check.ok]
    assert [check.task_id for check in failed] == ["backtesting"]
    assert "backtesting" in report.note

    record = {
        "model_id": report.model_id,
        "model_size_bytes": model.size_bytes,
        "passed": report.passed,
        "note": report.note,
        "verified_capabilities": [],
        "tasks": [
            {"task_id": check.task_id, "ok": check.ok, "detail": check.detail, "errors": check.errors}
            for check in report.tasks
        ],
    }
    verification.apply_record(model, record)
    verdict = compatibility.evaluate(model, "backtesting")
    assert verdict.status == compatibility.LIMITED
    assert any("backtesting" in reason for reason in verdict.reasons)


def test_invalid_json_and_http_errors_fail_profile() -> None:
    model = make_model()
    report = verification.verify_model(
        model,
        make_runtime(),
        http=fake_http({"technical": "not json"}),
    )
    technical = next(check for check in report.tasks if check.task_id == "technical")
    assert technical.ok is False
    assert "invalid JSON" in technical.detail

    def refused(*args, **kwargs):
        return HttpResult(False, 0, None, "ConnectionRefused")

    report = verification.verify_model(model, make_runtime(), http=refused, task_ids=["technical"])
    assert report.passed is False
    assert "ConnectionRefused" in report.tasks[0].detail


def test_cache_is_bound_to_model_identity(tmp_path) -> None:
    model = make_model()
    report = verification.verify_model(model, make_runtime(), http=fake_http())
    path = tmp_path / "ai_verification.json"
    verification.save_report(report, model, path=path)
    assert verification.load_record(model, path=path) is not None
    assert verification.load_record(make_model(size_bytes=9999), path=path) is None
    assert verification.load_record(make_model(id="ollama:other"), path=path) is None


def test_non_ollama_runtime_sends_no_request() -> None:
    calls = []

    def http(*args, **kwargs):
        calls.append(args)

    report = verification.verify_model(
        make_model(runtime_id="fastflowlm", provider="FastFlowLM"),
        make_runtime(id="fastflowlm"),
        http=http,
    )
    assert report.passed is False
    assert calls == []
    assert "Ollama only" in report.note
