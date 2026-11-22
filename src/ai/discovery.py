"""Aggregate runtime discovery into one snapshot plus explicit inference tests."""

from __future__ import annotations

import os
import shutil
import time
from typing import Callable

from . import verification
from .model_catalog import cloud_specs
from .runtime_registry import (
    HttpResult,
    cloud_runtime,
    detect_hardware,
    discover_fastflow,
    discover_ollama,
    http_json,
)
from .types import Hardware, ModelInfo, RuntimeInfo, Snapshot, TestResult

LAST_TEST: dict[str, TestResult] = {}


def build_snapshot(
    *,
    cloud_models: list[dict] | None = None,
    env: dict[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    http: Callable[..., HttpResult] = http_json,
    hardware: Hardware | None = None,
) -> Snapshot:
    """Discover every supported runtime. Never raises for a dead service."""
    values = os.environ if env is None else env
    board = hardware or detect_hardware(which=which)
    errors: list[str] = []

    runtimes = [
        discover_ollama(env=values, which=which, http=http, hardware=board),
        discover_fastflow(env=values, which=which, http=http, hardware=board),
    ]

    specs = cloud_models if cloud_models is not None else cloud_specs()
    grouped: dict[str, list[dict]] = {}
    for spec in specs:
        provider = str(spec.get("provider") or "").strip()
        name = str(spec.get("name") or "").strip()
        if provider and name:
            grouped.setdefault(provider, []).append(spec)
    for provider, provider_specs in sorted(grouped.items()):
        runtimes.append(cloud_runtime(provider, provider_specs, env=values, hardware=board))

    for runtime in runtimes:
        if runtime.error:
            errors.append(f"{runtime.name}: {runtime.error}")

    snapshot = Snapshot(runtimes=runtimes, generated_at=time.time(), hardware=board, errors=errors)
    if http is http_json:  # never mix the real cache into injected test transports
        for model in snapshot.local_models():
            record = verification.load_record(model)
            if record is not None:
                verification.apply_record(model, record)
    return snapshot


def _runtime_for(snapshot: Snapshot, model: ModelInfo) -> RuntimeInfo | None:
    return snapshot.runtime(model.runtime_id)


def _payload_text(data: object) -> str:
    if isinstance(data, dict):
        for key in ("response", "text", "content"):
            value = data.get(key)
            if isinstance(value, str):
                return value
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                return message["content"]
    return ""


def test_inference(
    snapshot: Snapshot,
    model_id: str,
    *,
    http: Callable[..., HttpResult] = http_json,
) -> TestResult:
    """Actually run one tiny generation. Cloud providers are not contacted."""
    model, runtime = snapshot.model(model_id)
    if model is None or runtime is None:
        return TestResult(False, "Model is not in the current inventory.")

    if runtime.kind == "cloud":
        if not model.configured:
            return TestResult(False, "No credential configured; no request sent.")
        return TestResult(False, "Cloud inference is not tested here to avoid external cost. Credentials are present.")

    if not runtime.reachable:
        return TestResult(False, runtime.error or f"{runtime.name} is not reachable.")

    started = time.perf_counter()
    if runtime.id == "ollama":
        result = http(
            "POST",
            f"{runtime.endpoint}/api/generate",
            {
                "model": model.name,
                "prompt": 'Reply with only this JSON: {"status":"ok"}',
                "stream": False,
                "format": "json",
                "options": {"num_predict": 24, "temperature": 0},
            },
            120,
        )
        text = _payload_text(result.data)
    elif runtime.id == "fastflowlm":
        result = http(
            "POST",
            f"{runtime.endpoint}/chat/completions",
            {
                "model": model.name,
                "messages": [{"role": "user", "content": 'Reply with only {"status":"ok"}.'}],
                "max_tokens": 24,
                "temperature": 0,
            },
            120,
        )
        text = _payload_text(result.data)
    else:
        return TestResult(False, f"No inference probe for runtime {runtime.name}.")

    latency = int((time.perf_counter() - started) * 1000)
    if not result.ok:
        detail = result.error or "Inference request failed."
        outcome = TestResult(False, detail, latency)
        LAST_TEST[model.id] = outcome
        return outcome

    cleaned = text.strip().strip("`").replace("json\n", "", 1).strip()
    structured: bool | None = None
    if cleaned:
        try:
            import json

            parsed = json.loads(cleaned)
            structured = isinstance(parsed, dict) and str(parsed.get("status", "")).lower() == "ok"
        except ValueError:
            structured = False
    ok = bool(text.strip())
    outcome = TestResult(
        ok,
        f"Inference returned {len(text.strip())} characters in {latency} ms"
        + ("" if structured is None else f" · JSON parse {'ok' if structured else 'failed'}"),
        latency,
        structured,
    )
    LAST_TEST[model.id] = outcome
    return outcome


def summary_line(snapshot: Snapshot) -> str:
    local = [r for r in snapshot.runtimes if r.kind == "local"]
    running = [r for r in local if r.reachable]
    installed_models = sum(len(r.models) for r in running)
    parts = [f"{len(running)}/{len(local)} local runtimes reachable", f"{installed_models} local model(s)"]
    cloud = [r for r in snapshot.runtimes if r.kind == "cloud"]
    if cloud:
        parts.append(f"{sum(1 for r in cloud if r.reachable)}/{len(cloud)} cloud provider(s) configured")
    return " · ".join(parts)
