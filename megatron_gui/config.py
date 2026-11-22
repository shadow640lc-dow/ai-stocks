"""Paths, env/keys, kill switch and command builders.

The GUI never reimplements the engines: it builds the same argv the
terminal launchers use, so every safety gate in the engines still runs.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CRYPTO_DIR = ROOT / "crypto_arb"
SCANNER = CRYPTO_DIR / "solana_arb_scanner.py"
LIVE_EXECUTOR = CRYPTO_DIR / "solana_live_executor.py"
CRYPTO_CONFIG = CRYPTO_DIR / "megacrypto_config.json"
PAPER_LOG = CRYPTO_DIR / "paper_trades.csv"

# Same file src/utils/live_switch.py resolves, so the GUI and the engines
# always agree on the master gate.
SWITCH_FILE = ROOT / ".live_trading"
CATALOG_CACHE = ROOT / ".megatron_cache" / "catalog.json"

ENV_FILES = (ROOT / ".env", CRYPTO_DIR / ".env")

CRYPTO_DEFAULTS: dict = {
    "wallet_address": "",
    "max_trade_usdc": 25.0,
    "daily_loss_limit_usdc": 5.0,
    "min_net_edge_pct": 0.20,
    "strong_edge_pct": 0.50,
    "max_price_impact_pct": 1.00,
    "slippage_bps": 50,
    "auto_trade": False,
    "live_trading": False,
}


# ----------------------------------------------------------------------
# Environment
# ----------------------------------------------------------------------

def read_env() -> dict[str, str]:
    """Parse the project .env files without needing python-dotenv."""
    values: dict[str, str] = {}
    for path in ENV_FILES:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                continue
            values[key] = value.strip().strip('"').strip("'")
    return values


def setting(key: str, default: str = "") -> str:
    return os.environ.get(key) or read_env().get(key, default)


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def ollama_base_url() -> str:
    url = os.environ.get("OLLAMA_BASE_URL") or read_env().get("OLLAMA_BASE_URL") or "http://localhost:11434"
    return url.rstrip("/")


def unload_ollama_model(name: str) -> bool:
    """Request that Ollama evict a model immediately (keep_alive = 0)."""
    if not name:
        return False
    payload = json.dumps({"model": name, "prompt": "", "stream": False, "keep_alive": 0}).encode("utf-8")
    request = Request(
        f"{ollama_base_url()}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=4) as response:
            return 200 <= int(getattr(response, "status", 200)) < 300
    except (OSError, URLError, ValueError):
        return False


# ----------------------------------------------------------------------
# Kill switch
# ----------------------------------------------------------------------

def switch_on() -> bool:
    try:
        return SWITCH_FILE.read_text(encoding="utf-8").strip().upper() == "ON"
    except OSError:
        return False


def set_switch(on: bool) -> None:
    SWITCH_FILE.parent.mkdir(parents=True, exist_ok=True)
    SWITCH_FILE.write_text("ON\n" if on else "OFF\n", encoding="utf-8")


# ----------------------------------------------------------------------
# Crypto config
# ----------------------------------------------------------------------

def load_crypto_config() -> dict:
    cfg = dict(CRYPTO_DEFAULTS)
    try:
        data = json.loads(CRYPTO_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return cfg
    if isinstance(data, dict):
        cfg.update({k: data[k] for k in CRYPTO_DEFAULTS if k in data})
    return cfg


def save_crypto_config(cfg: dict) -> None:
    CRYPTO_DIR.mkdir(parents=True, exist_ok=True)
    CRYPTO_CONFIG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    try:
        CRYPTO_CONFIG.chmod(0o600)
    except OSError:
        pass


# ----------------------------------------------------------------------
# Readiness
# ----------------------------------------------------------------------

def readiness() -> dict:
    env = read_env()
    crypto = load_crypto_config()
    wallet = env.get("SOLANA_WALLET_ADDRESS") or str(crypto.get("wallet_address") or "")
    return {
        "alpaca": bool(env.get("ALPACA_API_KEY") and env.get("ALPACA_SECRET_KEY")),
        "alpaca_mode": (env.get("ALPACA_MODE") or "paper").lower(),
        "alpaca_cap": env.get("ALPACA_MAX_NOTIONAL", ""),
        "solana_wallet": wallet,
        "jupiter": bool(env.get("JUPITER_API_KEY")),
        "solana_key": bool(env.get("SOLANA_PRIVATE_KEY")),
        "live_execution": truthy(env.get("MEGATRON_LIVE_EXECUTION")),
        "live_switch": switch_on(),
        "poetry": shutil.which("poetry") is not None,
        "scanner": SCANNER.exists(),
        "executor": LIVE_EXECUTOR.exists(),
        "max_trade_usdc": float(crypto.get("max_trade_usdc") or 25.0),
    }


# ----------------------------------------------------------------------
# Input helpers
# ----------------------------------------------------------------------

def parse_tickers(raw: str) -> list[str]:
    tokens = raw.replace(",", " ").split()
    out: list[str] = []
    for token in tokens:
        symbol = token.strip().upper()
        if symbol and symbol not in out:
            out.append(symbol)
    return out


# ----------------------------------------------------------------------
# Command builders
# ----------------------------------------------------------------------

def poetry_prefix() -> list[str]:
    exe = shutil.which("poetry")
    return [exe] if exe else ["poetry"]


STOCK_MODES = {
    "full": ("Full AI hedge fund", []),
    "ollama": ("Local Ollama stack", ["--ollama"]),
    "reasoning": ("Full AI + reasoning", ["--show-reasoning"]),
    "ollama_reasoning": ("Ollama + reasoning", ["--ollama", "--show-reasoning"]),
    "backtest": ("Backtester", []),
    "live": ("AI hedge fund + Alpaca", ["--alpaca"]),
}


def stocks_argv(
    ticker: str,
    mode: str,
    *,
    analysts: list[str] | None = None,
    model: str = "",
    ollama: bool = False,
) -> list[str]:
    script = "src/backtester.py" if mode == "backtest" else "src/main.py"
    flags = list(STOCK_MODES.get(mode, ("", []))[1])
    if ollama and "--ollama" not in flags:
        flags.append("--ollama")
    cmd = poetry_prefix() + ["run", "python", script, "--ticker", ticker, *flags]
    picks = [key for key in (analysts or []) if key]
    if picks:
        cmd += ["--analysts", ",".join(picks)]
    if model:
        cmd += ["--model", model]
    return cmd


CALL_STYLES = {
    "conservative": {
        "label": "Conservative / liquid",
        "tickers": ["--top", "10", "--min-volume", "100", "--min-oi", "500"],
    },
    "wider": {
        "label": "Wider candidate search",
        "tickers": ["--top", "15", "--min-volume", "50", "--min-oi", "250"],
    },
    "test": {
        "label": "Test universe",
        "tickers": ["--universe", "test", "--limit", "3", "--top", "5"],
    },
}


def calls_argv(
    tickers: list[str],
    style: str,
    *,
    alpaca: bool = False,
    contracts: int = 1,
    max_cap: float = 0.0,
) -> list[str]:
    spec = CALL_STYLES.get(style, CALL_STYLES["conservative"])
    cmd = poetry_prefix() + ["run", "python", "-m", "app.backend.services.covered_call_scanner"]
    if style != "test":
        cmd += list(tickers)
    cmd += spec["tickers"]
    if alpaca:
        cmd += ["--alpaca", "--contracts", str(int(contracts))]
        if max_cap > 0:
            cmd += ["--max-cap", f"{max_cap:g}"]
    return cmd


def arb_argv(*, once: bool, live: bool, interval: float = 10.0) -> list[str]:
    cmd = [sys.executable, str(SCANNER)]
    if once:
        cmd.append("--once")
    else:
        cmd += ["--interval", f"{interval:g}"]
    if live:
        cmd.append("--live")
    return cmd


def _executor_base() -> list[str]:
    """The executor needs solders/phase3 deps, so run it in the poetry env."""
    return poetry_prefix() + ["run", "python", str(LIVE_EXECUTOR.relative_to(ROOT))]


def gate_argv() -> list[str]:
    return _executor_base() + ["--gates"]


def swap_argv(direction: str, amount: float) -> list[str]:
    cmd = _executor_base() + ["--swap", "--direction", direction]
    if direction == "BUY":
        cmd += ["--usdc", f"{amount:g}"]
    else:
        cmd += ["--sol", f"{amount:g}"]
    return cmd + ["--confirm"]
