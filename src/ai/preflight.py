"""Preflight gate for research runs.

Blocks a run when the selected model is missing, its runtime is down, its
credentials are absent, or the task's required capabilities are not declared.
It never substitutes a different model on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import compatibility
from .types import LIMITED, READY, UNAVAILABLE, Compatibility, ModelInfo, RuntimeInfo, Snapshot


@dataclass
class Preflight:
    ok: bool
    status: str
    model: ModelInfo | None
    runtime: RuntimeInfo | None
    reasons: list[str] = field(default_factory=list)
    compatibility: Compatibility | None = None
    alternatives: list[ModelInfo] = field(default_factory=list)

    def message(self) -> str:
        return "\n".join(self.reasons)


def check(
    snapshot: Snapshot | None,
    model_id: str | None,
    *,
    task_id: str = "analyst_research",
    local_only: bool = False,
) -> Preflight:
    if snapshot is None:
        return Preflight(False, UNAVAILABLE, None, None, ["AI inventory has not loaded yet."])
    if not model_id:
        return Preflight(False, UNAVAILABLE, None, None, ["No model selected."])

    model, runtime = snapshot.model(model_id)
    if model is None or runtime is None:
        return Preflight(
            False,
            UNAVAILABLE,
            None,
            None,
            [f"Model '{model_id}' is not in the current inventory. Refresh AI status or pick an installed model."],
            alternatives=alternatives(snapshot, task_id, local_only),
        )

    blockers: list[str] = []
    if local_only and not model.local:
        blockers.append("Local-only mode is enabled, so cloud models are blocked.")
    if runtime.kind == "local":
        if not runtime.reachable:
            blockers.append(runtime.error or f"{runtime.name} is not reachable.")
        elif not model.installed:
            blockers.append(f"{model.name} is not installed on {runtime.name}.")
    else:
        if not model.configured:
            blockers.append(model.notes[0] if model.notes else "Cloud credential is missing.")

    result = compatibility.evaluate(model, task_id)
    ok = not blockers and result.status in {READY, LIMITED}
    status = result.status if not blockers else UNAVAILABLE
    reasons = blockers + result.reasons
    if status == UNAVAILABLE and not reasons:
        reasons.append("Model is unavailable.")

    return Preflight(
        ok=ok,
        status=status,
        model=model,
        runtime=runtime,
        reasons=reasons,
        compatibility=result,
        alternatives=alternatives(snapshot, task_id, local_only) if not ok else [],
    )


def alternatives(snapshot: Snapshot, task_id: str, local_only: bool = False) -> list[ModelInfo]:
    candidates: list[tuple[int, int, str, ModelInfo]] = []
    for model in snapshot.models(local_only=local_only):
        if not model.available or not model.configured:
            continue
        verdict = compatibility.evaluate(model, task_id)
        if verdict.status not in {READY, LIMITED}:
            continue
        candidates.append((compatibility.rank(verdict.status), 0 if model.local else 1, model.name.lower(), model))
    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in candidates]


def select_auto(snapshot: Snapshot | None, task_id: str, *, local_only: bool = False) -> ModelInfo | None:
    """Explicit automatic selection. Only called when the user enabled it."""
    if snapshot is None:
        return None
    found = alternatives(snapshot, task_id, local_only)
    return found[0] if found else None


def describe_failure(preflight: Preflight) -> str:
    lines = [f"{preflight.status}: {', '.join(preflight.reasons) if preflight.reasons else 'not usable'}"]
    if preflight.alternatives:
        lines.append("Compatible alternatives:")
        for model in preflight.alternatives[:4]:
            verdict = compatibility.evaluate(model, "analyst_research")
            lines.append(f"  · {model.name} ({verdict.status})")
    return "\n".join(lines)
