"""Analyst and model catalog, loaded from the project's real registry.

The GUI never keeps its own list of analysts. It asks the poetry environment
for ``ANALYST_CONFIG`` and ``LLM_ORDER`` (the same objects the CLI prompts
use) and caches the JSON so later launches are instant.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import config

CACHE_FILE = config.CATALOG_CACHE
CACHE_SCHEMA = 2  # bump when the cached payload shape changes
SOURCES = (config.ROOT / "src" / "utils" / "analysts.py", config.ROOT / "src" / "llm" / "models.py")

# Presentation grouping only; membership comes from the registry above.
SPECIALIST_KEYS = {
    "technical_analyst",
    "fundamentals_analyst",
    "growth_analyst",
    "news_sentiment_analyst",
    "sentiment_analyst",
    "valuation_analyst",
}

_DUMP = """
import json
from src.utils.analysts import ANALYST_CONFIG
from src.llm.models import AVAILABLE_MODELS, OLLAMA_MODELS

print(json.dumps({
    "analysts": [
        {
            "key": key,
            "name": cfg["display_name"],
            "role": cfg["description"],
            "style": cfg["investing_style"],
            "order": cfg["order"],
        }
        for key, cfg in ANALYST_CONFIG.items()
    ],
    "models": [
        {
            "label": model.display_name,
            "name": model.model_name,
            "provider": model.provider.value,
            "json_mode": model.has_json_mode(),
        }
        for model in AVAILABLE_MODELS + OLLAMA_MODELS
    ],
}))
"""


class CatalogError(RuntimeError):
    """The registry could not be read and no cache exists."""


@dataclass(frozen=True)
class Analyst:
    key: str
    name: str
    role: str
    style: str
    order: int

    @property
    def specialist(self) -> bool:
        return self.key in SPECIALIST_KEYS


@dataclass
class Catalog:
    analysts: list[Analyst]
    models: list[dict]
    fresh: bool = True

    def by_name(self) -> dict[str, Analyst]:
        return {a.name.upper(): a for a in self.analysts}

    def keys(self) -> list[str]:
        return [a.key for a in self.analysts]

    def groups(self) -> list[tuple[str, list[Analyst]]]:
        legends = [a for a in self.analysts if not a.specialist]
        specialists = [a for a in self.analysts if a.specialist]
        return [("Investment legends", legends), ("Specialist analysts", specialists)]

    def default_model(self) -> dict | None:
        for model in self.models:
            if model.get("name") == "gpt-4.1":
                return model
        for model in self.models:
            if model.get("provider") != "Ollama":
                return model
        return self.models[0] if self.models else None


def _decode(payload: dict, *, fresh: bool) -> Catalog:
    analysts = [
        Analyst(
            key=str(item["key"]),
            name=str(item["name"]),
            role=str(item.get("role") or ""),
            style=str(item.get("style") or ""),
            order=int(item.get("order") or 0),
        )
        for item in payload.get("analysts", [])
        if item.get("key") and item.get("name")
    ]
    analysts.sort(key=lambda a: a.order)
    models = [
        {
            "label": str(m.get("label") or m.get("name")),
            "name": str(m.get("name")),
            "provider": str(m.get("provider")),
            "json_mode": m.get("json_mode"),
        }
        for m in payload.get("models", [])
        if m.get("name") and m.get("name") != "-"
    ]
    if not analysts:
        raise CatalogError("The analyst registry returned no analysts.")
    return Catalog(analysts=analysts, models=models, fresh=fresh)


def _read_cache() -> Catalog | None:
    try:
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if payload.get("schema") != CACHE_SCHEMA:
            return None
        return _decode(payload, fresh=False)
    except (OSError, ValueError, KeyError, CatalogError):
        return None


def _cache_is_current() -> bool:
    try:
        cache_time = CACHE_FILE.stat().st_mtime
    except OSError:
        return False
    for source in SOURCES:
        try:
            if source.stat().st_mtime > cache_time:
                return False
        except OSError:
            return False
    return True


def load(force: bool = False) -> Catalog:
    """Return the catalog, preferring a fresh registry read over the cache."""
    if not force and _cache_is_current():
        cached = _read_cache()
        if cached is not None:
            return cached

    try:
        proc = subprocess.run(
            config.poetry_prefix() + ["run", "python", "-c", _DUMP],
            cwd=str(config.ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        cached = _read_cache()
        if cached is not None:
            return cached
        raise CatalogError(f"Could not start the registry reader: {exc}") from exc

    if proc.returncode != 0:
        cached = _read_cache()
        if cached is not None:
            return cached
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise CatalogError(detail[-1] if detail else "The registry reader exited with an error.")

    payload = None
    for line in reversed((proc.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if not isinstance(payload, dict):
        cached = _read_cache()
        if cached is not None:
            return cached
        raise CatalogError("The registry reader returned no usable data.")

    catalog = _decode(payload, fresh=True)
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(
            json.dumps(
                {
                    "schema": CACHE_SCHEMA,
                    "written": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "analysts": [a.__dict__ for a in catalog.analysts],
                    "models": catalog.models,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass
    return catalog


def describe(analyst: Analyst) -> str:
    parts = [analyst.role.strip(), analyst.style.strip()]
    return " — ".join(part for part in parts if part)


def path() -> Path:
    return CACHE_FILE
