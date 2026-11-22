"""Cloud model registry and credential checks.

The local project registry (src/llm/api_models.json) stays the source of
truth for cloud model names. Nothing here contacts a provider or spends
money.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

PROVIDER_KEYS: dict[str, tuple[str, ...]] = {
    "OpenAI": ("OPENAI_API_KEY",),
    "Anthropic": ("ANTHROPIC_API_KEY",),
    "Google": ("GOOGLE_API_KEY",),
    "DeepSeek": ("DEEPSEEK_API_KEY",),
    "Groq": ("GROQ_API_KEY",),
    "xAI": ("XAI_API_KEY",),
    "OpenRouter": ("OPENROUTER_API_KEY",),
    "Kimi": ("MOONSHOT_API_KEY", "KIMI_API_KEY"),
    "Alibaba": ("DASHSCOPE_API_KEY",),
    "Mistral": ("MISTRAL_API_KEY",),
    "Azure OpenAI": ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT_NAME"),
    "GigaChat": ("GIGACHAT_CREDENTIALS", "GIGACHAT_API_KEY"),
}

REGISTRY_PATH = Path(__file__).resolve().parents[1] / "llm" / "api_models.json"


def credential_env(provider: str) -> tuple[str, ...]:
    return PROVIDER_KEYS.get(provider, ())


def credential_present(provider: str, env: dict[str, str] | None = None) -> bool:
    values = os.environ if env is None else env
    keys = credential_env(provider)
    if not keys:
        return False
    found = [key for key in keys if values.get(key)]
    if provider == "Azure OpenAI":
        return len(found) == len(keys)
    return bool(found)


def cloud_specs(registry_path: Path | str | None = None) -> list[dict]:
    """Model registry entries in the shape discovery consumes."""
    path = Path(registry_path) if registry_path else REGISTRY_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    specs = []
    for item in payload if isinstance(payload, list) else []:
        name = str(item.get("model_name") or "").strip()
        provider = str(item.get("provider") or "").strip()
        if not name or not provider:
            continue
        specs.append(
            {
                "label": str(item.get("display_name") or name),
                "name": name,
                "provider": provider,
                "json_mode": None,
            }
        )
    return specs


def env_for_provider(provider: str) -> str:
    keys = credential_env(provider)
    return keys[0] if keys else "provider credentials"
