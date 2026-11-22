"""Empirical structured-output verification for local generation runtimes.

Ollama treats JSON output as an API mode, not a model capability: ``/api/show``
reports ``completion``, ``tools``, ``vision``, ``thinking`` and ``embedding``,
never ``json``. Metadata therefore cannot prove structured-output support.

This module sends a real JSON Schema through Ollama's structured-output
``format`` field for each MEGATRON task profile and validates the returned
object against that schema. Declared capabilities stay separate from the
verified ones so the UI can show both.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import compatibility
from .runtime_registry import HttpResult, http_json
from .types import ModelInfo, RuntimeInfo

ROOT = Path(__file__).resolve().parents[2]
VERIFICATION_FILE = ROOT / ".megatron_cache" / "ai_verification.json"
TASK_PROFILES = list(compatibility.TASK_ORDER)

# Shapes mirror the engine's own output models: AnalystSignal and
# PortfolioDecision. They are representative, not invented research fields.
_SIGNAL = {
    "type": "object",
    "properties": {
        "signal": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 100},
        "reasoning": {"type": "string", "minLength": 1},
    },
    "required": ["signal", "confidence", "reasoning"],
    "additionalProperties": False,
}

_RISK_SIGNAL = {
    "type": "object",
    "properties": {
        "signal": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 100},
        "reasoning": {"type": "string", "minLength": 1},
        "max_position_size": {"type": "number", "minimum": 0, "maximum": 100},
    },
    "required": ["signal", "confidence", "reasoning", "max_position_size"],
    "additionalProperties": False,
}

_DECISION = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string", "enum": ["TEST"]},
        "action": {"type": "string", "enum": ["buy", "sell", "short", "cover", "hold"]},
        "quantity": {"type": "integer", "minimum": 0, "maximum": 100000},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        "reasoning": {"type": "string", "minLength": 1},
    },
    "required": ["ticker", "action", "quantity", "confidence", "reasoning"],
    "additionalProperties": False,
}

_ANALYST_RESEARCH = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string", "enum": ["TEST"]},
        "analyst_signals": {
            "type": "object",
            "properties": {
                "fundamentals": _SIGNAL,
                "technical": _SIGNAL,
                "news_sentiment": _SIGNAL,
            },
            "required": ["fundamentals", "technical", "news_sentiment"],
            "additionalProperties": False,
        },
    },
    "required": ["ticker", "analyst_signals"],
    "additionalProperties": False,
}

SCHEMAS: dict[str, dict] = {
    "multi_agent": _DECISION,
    "analyst_research": _ANALYST_RESEARCH,
    "fundamentals": _SIGNAL,
    "technical": _SIGNAL,
    "news_sentiment": _SIGNAL,
    "portfolio_risk": _RISK_SIGNAL,
    "synthesis": _DECISION,
    "backtesting": _DECISION,
}

PROMPTS: dict[str, str] = {
    "multi_agent": (
        "Capability test. Emit one JSON object for a hypothetical ticker TEST, "
        "with action hold, quantity 0, confidence 50 and a short reasoning."
    ),
    "analyst_research": (
        "Capability test. Emit one JSON object for a hypothetical ticker TEST with "
        "analyst_signals for fundamentals, technical and news_sentiment; each signal "
        "has signal neutral, confidence 50 and a short reasoning."
    ),
    "fundamentals": (
        "Capability test for fundamental analysis. Emit one analyst signal object "
        "with signal neutral, confidence 50 and a short reasoning."
    ),
    "technical": (
        "Capability test for technical analysis. Emit one analyst signal object "
        "with signal neutral, confidence 50 and a short reasoning."
    ),
    "news_sentiment": (
        "Capability test for news and sentiment analysis. Emit one analyst signal "
        "object with signal neutral, confidence 50 and a short reasoning."
    ),
    "portfolio_risk": (
        "Capability test. Emit one risk signal object with signal neutral, confidence "
        "50, max_position_size 5 and a short reasoning."
    ),
    "synthesis": (
        "Capability test for research synthesis. Emit one portfolio decision object "
        "for ticker TEST with action hold, quantity 0, confidence 50 and a short reasoning."
    ),
    "backtesting": (
        "Capability test for backtesting assistance. Emit one portfolio decision object "
        "for ticker TEST with action hold, quantity 0, confidence 50 and a short reasoning."
    ),
}


def validate(instance: object, schema: dict, path: str = "$") -> list[str]:
    """Validate the subset of JSON Schema used above. Returns human errors."""
    errors: list[str] = []
    expected = schema.get("type")

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} is not one of {schema['enum']}")

    if expected == "object":
        if not isinstance(instance, dict):
            return errors or [f"{path}: expected object"]
        required = schema.get("required") or []
        for key in required:
            if key not in instance:
                errors.append(f"{path}.{key}: required field is missing")
        properties = schema.get("properties") or {}
        for key, value in instance.items():
            if key in properties:
                errors.extend(validate(value, properties[key], f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{key}: unexpected field")
    elif expected == "array":
        if not isinstance(instance, list):
            return errors or [f"{path}: expected array"]
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, value in enumerate(instance):
                errors.extend(validate(value, item_schema, f"{path}[{index}]"))
    elif expected == "string":
        if not isinstance(instance, str):
            errors.append(f"{path}: expected string")
        elif isinstance(schema.get("minLength"), int) and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']} characters")
    elif expected == "integer":
        if isinstance(instance, bool) or not isinstance(instance, int):
            errors.append(f"{path}: expected integer")
        else:
            errors.extend(_range(instance, schema, path))
    elif expected == "number":
        if isinstance(instance, bool) or not isinstance(instance, (int, float)):
            errors.append(f"{path}: expected number")
        else:
            errors.extend(_range(instance, schema, path))
    elif expected == "boolean":
        if not isinstance(instance, bool):
            errors.append(f"{path}: expected boolean")
    return errors


def _range(value: float, schema: dict, path: str) -> list[str]:
    errors = []
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    if isinstance(minimum, (int, float)) and value < minimum:
        errors.append(f"{path}: {value} is below the minimum {minimum}")
    if isinstance(maximum, (int, float)) and value > maximum:
        errors.append(f"{path}: {value} is above the maximum {maximum}")
    return errors


@dataclass
class TaskCheck:
    task_id: str
    ok: bool
    detail: str
    latency_ms: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class VerificationReport:
    model_id: str
    model_name: str
    runtime_id: str
    checked_at: float
    tasks: list[TaskCheck]
    passed: bool
    note: str
    verified_capabilities: list[str] = field(default_factory=list)


def verify_model(
    model: ModelInfo,
    runtime: RuntimeInfo,
    *,
    http: Callable[..., HttpResult] = http_json,
    timeout: float = 180.0,
    task_ids: list[str] | None = None,
) -> VerificationReport:
    """Run schema-constrained generation for each task profile and validate it."""
    selected = task_ids or TASK_PROFILES
    checks: list[TaskCheck] = []

    if runtime.kind != "local" or runtime.id != "ollama":
        note = "Structured-output verification currently supports Ollama only; no request was sent."
        checks = [TaskCheck(task, False, note) for task in selected]
        return VerificationReport(model.id, model.name, runtime.id, time.time(), checks, False, note, [])

    if not runtime.reachable:
        note = runtime.error or f"{runtime.name} is not reachable."
        checks = [TaskCheck(task, False, note) for task in selected]
        return VerificationReport(model.id, model.name, runtime.id, time.time(), checks, False, note, [])

    for task_id in selected:
        schema = SCHEMAS[task_id]
        started = time.perf_counter()
        result = http(
            "POST",
            f"{runtime.endpoint}/api/generate",
            {
                "model": model.name,
                "prompt": PROMPTS[task_id],
                "stream": False,
                "format": schema,
                "options": {"temperature": 0, "num_predict": 512},
            },
            timeout,
        )
        latency = int((time.perf_counter() - started) * 1000)

        if not result.ok:
            checks.append(TaskCheck(task_id, False, result.error or "request failed", latency))
            continue
        data = result.data if isinstance(result.data, dict) else {}
        text = data.get("response") if isinstance(data.get("response"), str) else ""
        if not text.strip():
            checks.append(TaskCheck(task_id, False, "empty response", latency))
            continue

        try:
            parsed = json.loads(text)
        except ValueError as exc:
            checks.append(TaskCheck(task_id, False, f"invalid JSON: {exc}", latency))
            continue

        errors = validate(parsed, schema)
        if errors:
            checks.append(TaskCheck(task_id, False, f"schema mismatch ({len(errors)} issue(s))", latency, errors[:4]))
        else:
            checks.append(TaskCheck(task_id, True, "schema valid", latency))

    failures = [check for check in checks if not check.ok]
    passed = not failures
    if passed:
        note = (
            f"Structured JSON verified: {len(checks)}/{len(checks)} task profiles passed "
            "Ollama schema-constrained generation."
        )
        verified = ["json"]
    else:
        names = ", ".join(check.task_id for check in failures[:4])
        more = "" if len(failures) <= 4 else f" (+{len(failures) - 4} more)"
        note = f"Structured output failed {len(failures)}/{len(checks)} task profiles: {names}{more}."
        verified = []

    return VerificationReport(model.id, model.name, runtime.id, time.time(), checks, passed, note, verified)


def save_report(report: VerificationReport, model: ModelInfo, path: Path | None = None) -> None:
    target = path or VERIFICATION_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model_id": report.model_id,
        "model_name": report.model_name,
        "model_size_bytes": model.size_bytes,
        "runtime_id": report.runtime_id,
        "checked_at": report.checked_at,
        "passed": report.passed,
        "note": report.note,
        "verified_capabilities": report.verified_capabilities,
        "tasks": [
            {
                "task_id": check.task_id,
                "ok": check.ok,
                "detail": check.detail,
                "latency_ms": check.latency_ms,
                "errors": check.errors,
            }
            for check in report.tasks
        ],
    }
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_record(model: ModelInfo, path: Path | None = None) -> dict | None:
    target = path or VERIFICATION_FILE
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("model_id") != model.id:
        return None
    if payload.get("model_size_bytes") != model.size_bytes:
        return None
    return payload


def apply_record(model: ModelInfo, record: dict) -> None:
    capabilities = record.get("verified_capabilities") or []
    model.verified_capabilities = frozenset(str(item) for item in capabilities)
    model.verification = record


def describe(report: VerificationReport) -> str:
    return report.note
