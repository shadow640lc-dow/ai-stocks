"""Match models to MEGATRON research tasks.

Requirements are explicit product policy, not model claims: every research
task needs chat completion, prefers native structured/JSON output, and has a
minimum context window. Model capabilities are only used when the runtime or
the project registry actually declared them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import (
    LIMITED,
    READY,
    UNSUPPORTED,
    UNAVAILABLE,
    Compatibility,
    ModelInfo,
)

TASK_ORDER = [
    "multi_agent",
    "analyst_research",
    "fundamentals",
    "technical",
    "news_sentiment",
    "portfolio_risk",
    "synthesis",
    "backtesting",
]


@dataclass(frozen=True)
class TaskSpec:
    id: str
    label: str
    min_context: int
    needs: frozenset[str] = frozenset({"chat"})
    prefers: frozenset[str] = frozenset({"json"})
    note: str = ""


TASKS: dict[str, TaskSpec] = {
    "multi_agent": TaskSpec("multi_agent", "Multi-agent hedge fund run", 8192, note="many analyst prompts plus portfolio synthesis"),
    "analyst_research": TaskSpec("analyst_research", "AI analyst research", 8192),
    "fundamentals": TaskSpec("fundamentals", "Fundamental analysis", 8192),
    "technical": TaskSpec("technical", "Technical analysis", 4096),
    "news_sentiment": TaskSpec("news_sentiment", "News & sentiment analysis", 4096),
    "portfolio_risk": TaskSpec("portfolio_risk", "Portfolio risk analysis", 8192),
    "synthesis": TaskSpec("synthesis", "Research synthesis / fund decisions", 8192),
    "backtesting": TaskSpec("backtesting", "Backtesting assistance", 4096),
}


def task(task_id: str) -> TaskSpec:
    return TASKS.get(task_id) or TASKS["analyst_research"]


def evaluate(model: ModelInfo, task_id: str = "analyst_research") -> Compatibility:
    spec = task(task_id)
    reasons: list[str] = []
    missing: list[str] = []
    notes: list[str] = []
    declared = set(model.capabilities)
    verified = set(model.verified_capabilities)
    effective = declared | verified

    if model.local and not model.installed:
        return Compatibility(UNAVAILABLE, ["Not installed on this runtime."], ["model installed"])
    if not model.configured:
        return Compatibility(UNAVAILABLE, ["No credential configured for this provider."], ["credentials"])
    if not model.available:
        return Compatibility(UNAVAILABLE, [model.notes[0] if model.notes else "Runtime reports this model as unavailable."], ["availability"])

    known = model.capabilities_source in {"runtime", "registry"}
    if known:
        absent = spec.needs - effective
        if absent:
            missing.extend(sorted(absent))
            reasons.append(f"Runtime metadata does not declare: {', '.join(sorted(absent))}.")
            return Compatibility(UNSUPPORTED, reasons, missing)

    if model.context_length:
        if model.context_length < spec.min_context:
            return Compatibility(
                UNSUPPORTED,
                [f"Context window {model.context_text()} is below the {spec.min_context // 1000}k needed for this task."],
                ["context window"],
            )
    else:
        reasons.append("Context window is not reported by the runtime; long prompts may truncate.")
        missing.append("declared context window")

    if "json" not in effective:
        if model.capabilities_source == "registry":
            reasons.append("MEGATRON routes this model through prompt-based JSON parsing (no native JSON mode).")
        elif model.capabilities_source == "runtime":
            reasons.append("Runtime does not declare structured/JSON output; MEGATRON will still request JSON and surface any parse failure.")
        else:
            reasons.append("Structured/JSON support is undeclared.")
        missing.append("declared JSON support")
        record = model.verification if isinstance(model.verification, dict) else None
        if record and record.get("note"):
            reasons.append(str(record["note"]))
    elif "json" not in declared:
        notes.append(
            "JSON output is empirically verified by schema-constrained generation; "
            "the runtime metadata still does not declare it, so declared and verified "
            "capabilities are shown separately."
        )

    if model.notes:
        reasons.extend(model.notes)

    status = LIMITED if reasons else READY
    return Compatibility(status, reasons, missing, notes)


def rank(status: str) -> int:
    return {READY: 0, LIMITED: 1, UNSUPPORTED: 2, UNAVAILABLE: 3}.get(status, 4)
