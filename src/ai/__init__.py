"""MEGATRON AI runtime discovery and readiness.

Stdlib-only on purpose: the desktop GUI imports these modules without the
poetry environment (no langchain/requests), and nothing here touches trading
execution.
"""

from .types import (
    Compatibility,
    Hardware,
    ModelInfo,
    RuntimeInfo,
    Snapshot,
    TestResult,
)

__all__ = [
    "Compatibility",
    "Hardware",
    "ModelInfo",
    "RuntimeInfo",
    "Snapshot",
    "TestResult",
]
