"""Runtime discovery, compatibility and preflight tests. No network, no cost."""

from __future__ import annotations

import pytest

from src.ai import compatibility, preflight
from src.ai.discovery import build_snapshot, test_inference as run_inference
from src.ai.model_catalog import credential_present
from src.ai.runtime_registry import HttpResult
from src.ai.types import Hardware

HARDWARE = Hardware(cpu_count=8, gpu="GPU: Test GPU", npu="NPU (/dev/accel/accel0)")


def ok(data):
    return HttpResult(True, 200, data, "")


def fail(error="URLError"):
    return HttpResult(False, 0, None, error)


def make_http(routes):
    def http(method, url, payload=None, timeout=1.5):
        for fragment, response in routes.items():
            if fragment in url:
                return response(url, payload) if callable(response) else response
        return fail()
    return http


def ollama_routes(models="default"):
    if models == "default":
        models = [
            {
                "name": "qwen3-coder:30b",
                "size": 18556701472,
                "details": {"parameter_size": "30.5B"},
                "capabilities": ["completion", "tools"],
            }
        ]
    return {
        "/api/version": ok({"version": "0.40.7"}),
        "/api/tags": ok({"models": models}),
        "/api/show": ok(
            {
                "capabilities": ["completion", "tools"],
                "model_info": {"qwen3moe.context_length": 262144},
            }
        ),
    }


def ollama_snapshot(**kwargs):
    return build_snapshot(
        cloud_models=[],
        env={},
        which=lambda name: "/usr/bin/ollama",
        http=make_http(ollama_routes(**kwargs)),
        hardware=HARDWARE,
    )


def fastflow_routes():
    return {
        "52625/v1/models": ok({"data": [{"id": "llama3.2:3b"}]}),
    }


def cloud_specs(json_mode=True):
    return [{"label": "GPT-5.5", "name": "gpt-5.5", "provider": "OpenAI", "json_mode": json_mode}]


def test_ollama_running_with_models():
    snapshot = ollama_snapshot()
    runtime = snapshot.runtime("ollama")
    assert runtime.reachable and runtime.installed and runtime.running
    assert runtime.status() == "READY"
    model = runtime.models[0]
    assert model.name == "qwen3-coder:30b"
    assert "chat" in model.capabilities and "tools" in model.capabilities
    assert model.context_length == 262144
    assert model.parameter_size == "30.5B"
    assert model.size_text().endswith("GB")


def test_ollama_installed_but_stopped():
    snapshot = build_snapshot(
        cloud_models=[],
        env={},
        which=lambda name: "/usr/bin/ollama",
        http=lambda *args, **kwargs: fail("ConnectionRefused"),
        hardware=HARDWARE,
    )
    runtime = snapshot.runtime("ollama")
    assert runtime.installed is True
    assert runtime.running is False
    assert runtime.reachable is False
    assert runtime.status() == "STOPPED"
    assert "did not respond" in runtime.error


def test_ollama_running_with_no_models():
    snapshot = build_snapshot(
        cloud_models=[],
        env={},
        which=lambda name: "/usr/bin/ollama",
        http=make_http(ollama_routes(models=[])),
        hardware=HARDWARE,
    )
    runtime = snapshot.runtime("ollama")
    assert runtime.reachable and runtime.models == []
    assert runtime.status() == "NO MODELS"
    assert "no models" in runtime.detail.lower()


def test_fastflowlm_running_with_model():
    snapshot = build_snapshot(
        cloud_models=[],
        env={},
        which=lambda name: None,
        http=make_http(fastflow_routes()),
        hardware=HARDWARE,
    )
    runtime = snapshot.runtime("fastflowlm")
    assert runtime.reachable is True
    assert runtime.installed is True
    assert [m.name for m in runtime.models] == ["llama3.2:3b"]
    assert runtime.models[0].local is True


def test_runtime_unavailable():
    snapshot = build_snapshot(
        cloud_models=[],
        env={},
        which=lambda name: None,
        http=lambda *args, **kwargs: fail("ConnectionRefused"),
        hardware=HARDWARE,
    )
    for runtime_id in ("ollama", "fastflowlm"):
        runtime = snapshot.runtime(runtime_id)
        assert runtime.reachable is False
        assert runtime.installed is False
        assert runtime.status() in {"NOT INSTALLED", "UNREACHABLE"}


def test_missing_model_is_blocked():
    snapshot = ollama_snapshot()
    result = preflight.check(snapshot, "ollama:not-installed", task_id="analyst_research")
    assert result.ok is False
    assert "not in the current inventory" in result.reasons[0]


def test_invalid_cloud_credentials_blocked():
    snapshot = build_snapshot(
        cloud_models=cloud_specs(),
        env={},
        which=lambda name: None,
        http=lambda *args, **kwargs: fail(),
        hardware=HARDWARE,
    )
    runtime = snapshot.runtime("cloud:OpenAI")
    assert runtime.reachable is False
    assert runtime.models[0].configured is False
    result = preflight.check(snapshot, "cloud:OpenAI:gpt-5.5", task_id="multi_agent")
    assert result.ok is False
    assert "Missing credential" in " ".join(result.reasons)


def test_incompatible_capabilities_are_explained():
    from src.ai.types import ModelInfo

    embedding_only = ModelInfo(
        id="test:embed",
        name="embed-model",
        runtime_id="test",
        provider="Test",
        local=True,
        installed=True,
        capabilities=frozenset({"embedding"}),
        capabilities_source="runtime",
    )
    verdict = compatibility.evaluate(embedding_only, "fundamentals")
    assert verdict.status == "NOT SUPPORTED"
    assert "chat" in verdict.missing

    tiny = ModelInfo(
        id="test:tiny",
        name="tiny",
        runtime_id="test",
        provider="Test",
        local=True,
        installed=True,
        context_length=2048,
        capabilities=frozenset({"chat"}),
        capabilities_source="runtime",
    )
    verdict = compatibility.evaluate(tiny, "multi_agent")
    assert verdict.status == "NOT SUPPORTED"
    assert "context window" in " ".join(verdict.reasons).lower()


def test_multiple_runtimes_are_reported():
    routes = {**ollama_routes(), **fastflow_routes()}
    snapshot = build_snapshot(
        cloud_models=[],
        env={},
        which=lambda name: "/usr/bin/ollama" if name == "ollama" else None,
        http=make_http(routes),
        hardware=HARDWARE,
    )
    assert snapshot.runtime("ollama").reachable
    assert snapshot.runtime("fastflowlm").reachable
    assert len(snapshot.local_models()) == 2


def test_local_only_blocks_cloud():
    snapshot = build_snapshot(
        cloud_models=cloud_specs(),
        env={"OPENAI_API_KEY": "test-key"},
        which=lambda name: "/usr/bin/ollama",
        http=make_http(ollama_routes()),
        hardware=HARDWARE,
    )
    result = preflight.check(snapshot, "cloud:OpenAI:gpt-5.5", task_id="multi_agent", local_only=True)
    assert result.ok is False
    assert "Local-only" in result.reasons[0]


def test_remote_model_configured_but_limited_without_context_metadata():
    snapshot = build_snapshot(
        cloud_models=cloud_specs(json_mode=True),
        env={"OPENAI_API_KEY": "test-key"},
        which=lambda name: None,
        http=lambda *args, **kwargs: fail(),
        hardware=HARDWARE,
    )
    model, _runtime = snapshot.model("cloud:OpenAI:gpt-5.5")
    assert model.configured is True
    verdict = compatibility.evaluate(model, "multi_agent")
    assert verdict.status == "READY WITH LIMITATIONS"
    assert any("Context window" in reason for reason in verdict.reasons)
    result = preflight.check(snapshot, model.id, task_id="multi_agent")
    assert result.ok is True


def test_model_disappearing_between_checks():
    snapshot = ollama_snapshot()
    assert preflight.check(snapshot, "ollama:qwen3-coder:30b").ok is True
    empty = build_snapshot(
        cloud_models=[],
        env={},
        which=lambda name: "/usr/bin/ollama",
        http=make_http(ollama_routes(models=[])),
        hardware=HARDWARE,
    )
    result = preflight.check(empty, "ollama:qwen3-coder:30b")
    assert result.ok is False
    assert result.status == "UNAVAILABLE"


def test_auto_selection_is_explicit_and_prefers_local():
    routes = {**ollama_routes(), "/api/version": ok({"version": "0.40.7"})}
    snapshot = build_snapshot(
        cloud_models=cloud_specs(),
        env={"OPENAI_API_KEY": "test-key"},
        which=lambda name: "/usr/bin/ollama",
        http=make_http(routes),
        hardware=HARDWARE,
    )
    chosen = preflight.select_auto(snapshot, "analyst_research")
    assert chosen is not None and chosen.local is True
    assert preflight.select_auto(None, "analyst_research") is None


def test_inference_probe_parses_json_and_records_failure():
    routes = {
        "/api/generate": ok({"response": '{"status": "ok"}'}),
        "/api/version": ok({"version": "0.40.7"}),
        "/api/tags": ok({"models": [{"name": "qwen3-coder:30b"}]}),
        "/api/show": ok({"capabilities": ["completion"]}),
    }
    snapshot = build_snapshot(
        cloud_models=[],
        env={},
        which=lambda name: "/usr/bin/ollama",
        http=make_http(routes),
        hardware=HARDWARE,
    )
    result = run_inference(snapshot, "ollama:qwen3-coder:30b", http=make_http(routes))
    assert result.ok is True
    assert result.structured_ok is True

    offline = build_snapshot(
        cloud_models=[],
        env={},
        which=lambda name: "/usr/bin/ollama",
        http=lambda *args, **kwargs: fail("ConnectionRefused"),
        hardware=HARDWARE,
    )
    assert run_inference(offline, "ollama:qwen3-coder:30b", http=lambda *a, **k: fail()).ok is False


def test_credential_detection_does_not_require_values_printed():
    assert credential_present("OpenAI", {"OPENAI_API_KEY": "x"}) is True
    assert credential_present("OpenAI", {}) is False
    assert credential_present("Kimi", {"KIMI_API_KEY": "x"}) is True
