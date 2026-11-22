"""Runtime adapters: Ollama, FastFlowLM and configured cloud providers.

Every probe is read-only. A missing binary, a stopped service and a model-less
service are reported as different states; an installed CLI is never treated
as a working runtime.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .model_catalog import credential_env, credential_present
from .types import Hardware, ModelInfo, RuntimeInfo

TIMEOUT = 1.5


@dataclass
class HttpResult:
    ok: bool
    status: int = 0
    data: Any = None
    error: str = ""


def http_json(method: str, url: str, payload: dict | None = None, timeout: float = TIMEOUT) -> HttpResult:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            if not raw:
                return HttpResult(True, response.status, {})
            try:
                return HttpResult(True, response.status, json.loads(raw))
            except ValueError:
                return HttpResult(True, response.status, raw.decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return HttpResult(False, exc.code, None, f"HTTP {exc.code}")
    except Exception as exc:  # URLError, timeouts, connection refused
        return HttpResult(False, 0, None, type(exc).__name__)


def detect_hardware(*, run: Callable[..., Any] = subprocess.run, which: Callable[[str], str | None] = shutil.which) -> Hardware:
    cpu = os.cpu_count() or 0
    gpu = ""
    if which("nvidia-smi"):
        try:
            result = run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            name = (result.stdout or "").strip().splitlines()
            if name:
                gpu = f"GPU: {name[0][:60]}"
        except Exception:
            gpu = ""
    if not gpu and Path("/dev/kfd").exists():
        gpu = "AMD GPU (/dev/kfd)"
    npu = ""
    if Path("/dev/accel/accel0").exists():
        npu = "NPU (/dev/accel/accel0)"
    return Hardware(cpu_count=cpu, gpu=gpu, npu=npu)


def _capabilities(values: Any) -> frozenset[str]:
    mapping = {"completion": "chat", "chat": "chat", "tools": "tools", "vision": "vision", "thinking": "thinking", "json": "json"}
    found = set()
    for value in values or []:
        mapped = mapping.get(str(value).lower())
        if mapped:
            found.add(mapped)
    return frozenset(found)


def _context_length(show: dict, details: dict) -> int | None:
    model_info = show.get("model_info") if isinstance(show.get("model_info"), dict) else {}
    for key, value in model_info.items():
        if str(key).endswith(".context_length") and isinstance(value, (int, float)) and value > 0:
            return int(value)
    for value in (details.get("context_length"), show.get("context_length")):
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    return None


def _ollama_model(base: str, item: dict, http: Callable[..., HttpResult]) -> ModelInfo:
    name = str(item.get("name") or item.get("model") or "").strip()
    details = item.get("details") if isinstance(item.get("details"), dict) else {}
    show = http("POST", f"{base}/api/show", {"model": name}, 2.0)
    payload = show.data if show.ok and isinstance(show.data, dict) else {}
    capabilities = set(_capabilities(item.get("capabilities")))
    capabilities |= set(_capabilities(payload.get("capabilities")))
    source = "runtime" if capabilities or payload else "unknown"
    notes: list[str] = []
    if not show.ok:
        notes.append("Model details unavailable; capabilities are undeclared.")
    return ModelInfo(
        id=f"ollama:{name}",
        name=name,
        runtime_id="ollama",
        provider="Ollama",
        local=True,
        installed=True,
        configured=True,
        size_bytes=int(item["size"]) if isinstance(item.get("size"), (int, float)) else None,
        parameter_size=str(details.get("parameter_size") or ""),
        context_length=_context_length(payload, details),
        capabilities=frozenset(capabilities),
        capabilities_source=source,
        available=True,
        notes=notes,
    )


def discover_ollama(
    *,
    env: dict[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    http: Callable[..., HttpResult] = http_json,
    hardware: Hardware | None = None,
) -> RuntimeInfo:
    values = os.environ if env is None else env
    base = (values.get("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
    installed = bool(which("ollama"))
    version = http("GET", f"{base}/api/version", None, TIMEOUT)
    tags = http("GET", f"{base}/api/tags", None, 2.0)
    reachable = bool(version.ok or tags.ok)
    models: list[ModelInfo] = []

    if reachable and tags.ok and isinstance(tags.data, dict):
        items = tags.data.get("models") or []
        if items:
            with ThreadPoolExecutor(max_workers=6) as pool:
                models = list(pool.map(lambda item: _ollama_model(base, item, http), items))

    error = ""
    detail = ""
    if not installed and not reachable:
        error = "Ollama CLI not found on PATH and the API is unreachable."
    elif installed and not reachable:
        error = f"Installed, but {base} did not respond. Start it with `ollama serve`."
    elif reachable and not models:
        detail = "Running, but no models are downloaded."

    return RuntimeInfo(
        id="ollama",
        name="Ollama",
        kind="local",
        endpoint=base,
        installed=installed,
        running=True if reachable else (False if installed else None),
        reachable=reachable,
        version=str((version.data or {}).get("version") or "") if isinstance(version.data, dict) else "",
        models=models,
        hardware=hardware,
        error=error,
        detail=detail,
    )


def discover_fastflow(
    *,
    env: dict[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    http: Callable[..., HttpResult] = http_json,
    hardware: Hardware | None = None,
) -> RuntimeInfo:
    values = os.environ if env is None else env
    base = (values.get("FASTFLOWLM_BASE_URL") or "http://127.0.0.1:52625/v1").rstrip("/")
    binary = which("fastflowlm") or which("flm")
    models_res = http("GET", f"{base}/models", None, TIMEOUT)
    reachable = bool(models_res.ok)
    models: list[ModelInfo] = []

    if reachable and isinstance(models_res.data, dict):
        for item in models_res.data.get("data") or []:
            name = str(item.get("id") or item.get("model") or "").strip()
            if not name:
                continue
            models.append(
                ModelInfo(
                    id=f"fastflowlm:{name}",
                    name=name,
                    runtime_id="fastflowlm",
                    provider="FastFlowLM",
                    local=True,
                    installed=True,
                    configured=True,
                    capabilities_source="unknown",
                    notes=["FastFlowLM exposes no capability metadata; compatibility is inferred only from the model name."],
                )
            )

    installed: bool | None = True if (binary or reachable) else False
    error = ""
    detail = ""
    if not binary and not reachable:
        error = "FastFlowLM is not installed and no local endpoint responded."
    elif not binary and reachable:
        detail = "A FastFlowLM-compatible endpoint is running without the CLI on PATH."
    elif binary and not reachable:
        error = f"Installed, but {base} did not respond."

    return RuntimeInfo(
        id="fastflowlm",
        name="FastFlowLM",
        kind="local",
        endpoint=base,
        installed=installed,
        running=True if reachable else (False if binary else None),
        reachable=reachable,
        models=models,
        hardware=hardware,
        error=error,
        detail=detail,
    )


def cloud_runtime(provider: str, specs: list[dict], *, env: dict[str, str] | None = None, hardware: Hardware | None = None) -> RuntimeInfo:
    values = os.environ if env is None else env
    configured = credential_present(provider, values)
    models: list[ModelInfo] = []
    for spec in specs:
        json_mode = spec.get("json_mode")
        capabilities = {"chat"}
        notes: list[str] = []
        if json_mode is True:
            capabilities.add("json")
        elif json_mode is False:
            notes.append("Project registry uses prompt-based JSON parsing for this model.")
        else:
            notes.append("Structured-output support is undeclared in the project registry.")
        models.append(
            ModelInfo(
                id=f"cloud:{provider}:{spec['name']}",
                name=spec["name"],
                runtime_id=f"cloud:{provider}",
                provider=provider,
                local=False,
                installed=False,
                configured=configured,
                capabilities=frozenset(capabilities),
                capabilities_source="registry" if json_mode is not None else "unknown",
                available=configured,
                notes=notes if configured else [f"Missing credential: {', '.join(credential_env(provider)) or 'provider key'}"],
            )
        )
    keys = ", ".join(credential_env(provider)) or "provider credentials"
    return RuntimeInfo(
        id=f"cloud:{provider}",
        name=provider,
        kind="cloud",
        endpoint="provider API",
        installed=None,
        running=None,
        reachable=configured,
        models=models,
        hardware=hardware,
        error="" if configured else f"No credential configured ({keys}).",
        detail="" if configured else "",
    )
