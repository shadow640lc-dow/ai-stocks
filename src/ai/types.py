"""Data types shared by AI discovery, compatibility and preflight."""

from __future__ import annotations

from dataclasses import dataclass, field

READY = "READY"
LIMITED = "READY WITH LIMITATIONS"
UNSUPPORTED = "NOT SUPPORTED"
UNAVAILABLE = "UNAVAILABLE"

RANK = {READY: 0, LIMITED: 1, UNSUPPORTED: 2, UNAVAILABLE: 3}


@dataclass(frozen=True)
class Hardware:
    cpu_count: int = 0
    gpu: str = ""
    npu: str = ""
    notes: tuple[str, ...] = ()

    def summary(self) -> str:
        parts = []
        if self.cpu_count:
            parts.append(f"{self.cpu_count} CPU threads")
        if self.gpu:
            parts.append(self.gpu)
        if self.npu:
            parts.append(self.npu)
        return " · ".join(parts) or "hardware not reported"


@dataclass
class ModelInfo:
    id: str
    name: str
    runtime_id: str
    provider: str
    local: bool
    installed: bool
    configured: bool = True
    size_bytes: int | None = None
    parameter_size: str = ""
    context_length: int | None = None
    capabilities: frozenset[str] = frozenset()
    capabilities_source: str = "unknown"  # runtime | registry | unknown
    verified_capabilities: frozenset[str] = frozenset()  # empirically tested only
    verification: dict | None = None  # last schema verification record
    available: bool = True
    notes: list[str] = field(default_factory=list)

    def label(self) -> str:
        kind = "LOCAL" if self.local else "CLOUD"
        bits = [kind, self.provider]
        if self.parameter_size:
            bits.append(self.parameter_size)
        return " · ".join(bits)

    def size_text(self) -> str:
        if self.size_bytes is None:
            return "—"
        value = float(self.size_bytes)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024
        return "—"

    def context_text(self) -> str:
        if not self.context_length:
            return "—"
        if self.context_length >= 1000:
            return f"{self.context_length // 1000}k"
        return str(self.context_length)


@dataclass
class RuntimeInfo:
    id: str
    name: str
    kind: str  # local | cloud
    endpoint: str
    installed: bool | None
    running: bool | None
    reachable: bool
    version: str = ""
    models: list[ModelInfo] = field(default_factory=list)
    hardware: Hardware | None = None
    error: str = ""
    detail: str = ""

    def status(self) -> str:
        """Short human state; never claims more than was observed."""
        if self.kind == "cloud":
            if not self.reachable:
                return "NO CREDENTIAL"
            return "CONFIGURED"
        if not self.installed:
            return "NOT INSTALLED"
        if not self.reachable:
            return "STOPPED" if self.running is False else "UNREACHABLE"
        if not self.models:
            return "NO MODELS"
        return "READY"

    def model(self, model_id: str) -> ModelInfo | None:
        return next((m for m in self.models if m.id == model_id), None)


@dataclass
class Snapshot:
    runtimes: list[RuntimeInfo]
    generated_at: float
    hardware: Hardware
    errors: list[str] = field(default_factory=list)

    def models(self, *, local_only: bool = False) -> list[ModelInfo]:
        out: list[ModelInfo] = []
        for runtime in self.runtimes:
            if local_only and runtime.kind != "local":
                continue
            out.extend(runtime.models)
        return out

    def model(self, model_id: str) -> tuple[ModelInfo, RuntimeInfo] | tuple[None, None]:
        for runtime in self.runtimes:
            found = runtime.model(model_id)
            if found is not None:
                return found, runtime
        return None, None

    def runtime(self, runtime_id: str) -> RuntimeInfo | None:
        return next((r for r in self.runtimes if r.id == runtime_id), None)

    def local_models(self) -> list[ModelInfo]:
        return [m for r in self.runtimes if r.kind == "local" for m in r.models]

    def usable_count(self) -> int:
        return sum(1 for m in self.models() if m.available and m.configured)


@dataclass
class Compatibility:
    status: str
    reasons: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class TestResult:
    ok: bool
    detail: str
    latency_ms: int = 0
    structured_ok: bool | None = None  # None = not tested
