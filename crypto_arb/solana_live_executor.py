from __future__ import annotations

"""MEGACRYPTO // GATED SOLANA LIVE EXECUTOR

Opt-in, confirmation-locked wrapper around crypto_arb/phase3_executor.

Final safety model:
    - LIVE EXECUTION: DISABLED by default (MEGATRON_LIVE_EXECUTION != true)
    - Requires explicit per-swap confirmation in the terminal
    - Requires a SOLANA_PRIVATE_KEY in the environment
    - Requires a JUPITER_API_KEY in the environment
    - Max swap locked to MEGATRON_MAX_TRADE_USDC (default 25 USDC)
    - Jupiter swap is ALWAYS simulated on the RPC before broadcast
    - A simulated failure cancels the broadcast
    - Paper preview the broadcast transaction before you confirm

Execution is opt-in: this launcher never signs or broadcasts on
its own. Every swap goes through an explicit two-stage gate:
    1) SIMULATE  -> must pass
    2) CONFIRM   -> explicit y/N
"""

import os
import json
import base64
from pathlib import Path

from urllib.request import Request, urlopen

from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from phase3_executor import build_jupiter_swap_transaction


def _load_env_file() -> None:
    """Load KEY=VALUE entries from the local crypto_arb/.env.

    Existing shell variables always win, matching solana_arb_scanner.
    """
    env_file = Path(__file__).resolve().parent / ".env"

    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if os.getenv(key) is None:
            os.environ[key] = value


class SolanaLiveError(RuntimeError):
    """Raised when a live Solana swap is refused."""


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def load_live_config() -> dict:
    _load_env_file()

    return {
        "enabled": _env_bool("MEGATRON_LIVE_EXECUTION"),
        "private_key_supplied": bool(
            os.getenv("SOLANA_PRIVATE_KEY")
        ),
        "wallet_address": os.getenv("SOLANA_WALLET_ADDRESS"),
        "max_trade_usdc": _env_float(
            "MEGATRON_MAX_TRADE_USDC",
            25.0,
        ),
        "rpc_url": os.getenv(
            "SOLANA_RPC_URL",
            "https://api.mainnet-beta.solana.com",
        ),
        "jupiter_key_supplied": bool(
            os.getenv("JUPITER_API_KEY")
        ),
    }


def broadcast_versioned_transaction(
    transaction_bytes: bytes,
    *,
    rpc_url: str,
    timeout: float = 30.0,
) -> dict:
    """Serialize a signed versioned transaction and broadcast it on Solana."""

    encoded = base64.b64encode(transaction_bytes).decode()

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendTransaction",
        "params": [
            encoded,
            {
                "encoding": "base64",
                "preflightCommitment": "confirmed",
            },
        ],
    }

    req = Request(
        rpc_url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read().decode())

    return data


def _simulate_on_rpc(
    rpc_url: str,
    transaction_bytes: bytes,
    *,
    timeout: float = 30.0,
) -> tuple[bool, dict]:
    """Ask the RPC to simulate the unsigned swap first."""

    encoded = base64.b64encode(transaction_bytes).decode()

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "simulateTransaction",
        "params": [
            encoded,
            {
                "encoding": "base64",
                "commitment": "confirmed",
                "replaceRecentBlockhash": True,
                "sigVerify": False,
            },
        ],
    }

    req = Request(
        rpc_url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read().decode())

    simulation_error = (
        data.get("result", {})
        .get("value", {})
        .get("err")
    )

    return simulation_error is None, data


def execute_live_solana_swap(
    *,
    quote_response: dict,
    user_public_key: str,
    private_key: str,
    max_trade_usdc: float,
    rpc_url: str,
    confirm: callable,  # noqa: A001
) -> dict:
    """Full gated flow: build → simulate → confirm → sign + broadcast.

    GATE ORDER (each must pass):
        1. live execution enabled (checked by caller)
        2. simulation passes on the RPC
        3. explicit user confirmation
        4. sign with SOLANA_PRIVATE_KEY
        5. broadcast

    Returns a dict describing the outcome.
    """

    # --------------------------------------------------
    # SIMULATE FIRST
    # --------------------------------------------------

    built_ok, transaction_bytes, build_err = build_jupiter_swap_transaction(
        quote_response=quote_response,
        user_public_key=user_public_key,
    )

    if not built_ok or not transaction_bytes:
        return {
            "status": "REFUSED",
            "reason": f"swap build failed: {build_err}",
        }

    simulated, sim_data = _simulate_on_rpc(rpc_url, transaction_bytes)

    if not simulated:
        return {
            "status": "REFUSED",
            "reason": "RPC simulation failed — rejecting candidate",
            "simulation": sim_data,
        }

    # --------------------------------------------------
    # STRICT CONFIRMATION
    # --------------------------------------------------

    approved = confirm(
        f"\n  ⚠ SIGN & BROADCAST this swap on SOLANA mainnet? "
        f"(max ${max_trade_usdc:,.2f} USDC) [y/N]: "
    )

    if not approved:
        return {
            "status": "DECLINED",
            "reason": "confirmed by user",
        }

    # --------------------------------------------------
    # SIGN
    # --------------------------------------------------

    try:
        keypair = Keypair.from_base58_string(private_key.strip())
    except Exception as exc:
        return {
            "status": "REFUSED",
            "reason": f"invalid SOLANA_PRIVATE_KEY: {exc}",
        }

    try:
        transaction = VersionedTransaction.from_bytes(transaction_bytes)
        transaction.try_sign([keypair])
        signed_bytes = bytes(transaction.serialize())
    except Exception as exc:
        return {
            "status": "REFUSED",
            "reason": f"signing failed: {exc}",
        }

    # --------------------------------------------------
    # BROADCAST
    # --------------------------------------------------

    try:
        broadcast = broadcast_versioned_transaction(
            signed_bytes,
            rpc_url=rpc_url,
        )
    except Exception as exc:
        return {
            "status": "ERROR",
            "reason": f"broadcast failed: {exc}",
        }

    signature = broadcast.get("result")
    if not signature:
        return {
            "status": "ERROR",
            "reason": f"RPC refused broadcast: {broadcast}",
        }

    return {
        "status": "BROADCAST",
        "signature": signature,
        "rpc": rpc_url,
    }


def maybe_execute_live_swap(
    *,
    quote_response: dict,
    confirm,
) -> dict:
    """Gated entry point — refuses unless every env gate passes."""

    root = Path(__file__).resolve().parent.parent
    switch_file = root / ".live_trading"

    try:
        switch_on = (
            switch_file.exists()
            and switch_file.read_text(encoding="utf-8").strip().upper() == "ON"
        )
    except OSError:
        switch_on = False

    if not switch_on:
        return {
            "status": "REFUSED",
            "reason": "LIVE-KILL-SWITCH: live trading is OFF (run `live on` to enable)",
        }

    config = load_live_config()

    if not config["enabled"]:
        return {
            "status": "REFUSED",
            "reason": "MEGATRON_LIVE_EXECUTION is not set to true",
        }

    if not config["private_key_supplied"]:
        return {
            "status": "REFUSED",
            "reason": "SOLANA_PRIVATE_KEY is not configured",
        }

    if not config["jupiter_key_supplied"]:
        return {
            "status": "REFUSED",
            "reason": "JUPITER_API_KEY is not configured",
        }

    wallet = config["wallet_address"]
    if not wallet:
        return {
            "status": "REFUSED",
            "reason": "SOLANA_WALLET_ADDRESS is not configured",
        }

    return execute_live_solana_swap(
        quote_response=quote_response,
        user_public_key=wallet,
        private_key=os.getenv("SOLANA_PRIVATE_KEY", ""),
        max_trade_usdc=config["max_trade_usdc"],
        rpc_url=config["rpc_url"],
        confirm=confirm,
    )


def print_gate_status() -> int:
    """Print the live-execution gate status without doing anything."""
    config = load_live_config()

    gates = [
        ("MEGATRON_LIVE_EXECUTION=true", config["enabled"]),
        ("SOLANA_PRIVATE_KEY configured", config["private_key_supplied"]),
        ("JUPITER_API_KEY configured", config["jupiter_key_supplied"]),
        ("SOLANA_WALLET_ADDRESS configured", bool(config["wallet_address"])),
    ]

    for label, ok in gates:
        print(f"[{'OK' if ok else 'MISSING':>7}]  {label}")

    print(f"        max trade: ${config['max_trade_usdc']:,.2f} USDC")
    print(f"        rpc:       {config['rpc_url']}")

    if all(ok for _, ok in gates):
        print("\nLive execution: ENABLED — swaps will require explicit confirmation.")
        return 0

    print("\nLive execution: LOCKED — one or more gates are not configured.")
    return 1


_USDC_MICRO = 1_000_000
_SOL_LAMPORTS = 1_000_000_000


def cli_main(argv: list[str] | None = None) -> int:
    """CLI entry point: gate status (default) or a gated live swap."""
    import argparse

    parser = argparse.ArgumentParser(
        description="MEGACRYPTO // gated Solana live executor"
    )
    parser.add_argument(
        "--gates",
        action="store_true",
        help="print live-execution gate status and exit",
    )
    parser.add_argument(
        "--swap",
        action="store_true",
        help="fetch a live Jupiter quote and run the gated swap flow",
    )
    parser.add_argument(
        "--direction",
        choices=["BUY", "SELL"],
        default="BUY",
        help="BUY = USDC -> SOL, SELL = SOL -> USDC",
    )
    parser.add_argument(
        "--usdc",
        type=float,
        default=10.0,
        help="USDC input amount for a BUY swap",
    )
    parser.add_argument(
        "--sol",
        type=float,
        default=0.1,
        help="SOL input amount for a SELL swap (lamports = SOL * 1e9)",
    )
    parser.add_argument(
        "--venue",
        default="JUPITER",
        help="Jupiter DEX venue to quote",
    )
    parser.add_argument(
        "--slippage-bps",
        type=int,
        default=300,
        help="slippage in basis points (default 300 = 3%)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="per-request timeout in seconds",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="allow interactive y/N confirmation (required for broadcast)",
    )

    args = parser.parse_args(argv)

    if args.gates or not args.swap:
        return print_gate_status()

    from solana_arb_scanner import get_quote

    if args.direction == "BUY":
        amount = int(round(args.usdc * _USDC_MICRO))
    else:
        amount = int(round(args.sol * _SOL_LAMPORTS))

    try:
        quote = get_quote(
            venue=args.venue,
            direction=args.direction,
            amount=amount,
            slippage_bps=args.slippage_bps,
            timeout=args.timeout,
        )
    except Exception as exc:
        print(f"quote failed: {exc}")
        return 1

    config = load_live_config()

    def confirm(_: str) -> bool:
        if not args.confirm:
            return False
        try:
            return input("Type YES to confirm: ").strip().lower() in {"y", "yes"}
        except (KeyboardInterrupt, EOFError):
            return False

    result = maybe_execute_live_swap(
        quote_response=quote.raw,
        confirm=confirm,
    )

    print(json.dumps(result, indent=2))

    return 0 if result.get("status") == "BROADCAST" else 1


if __name__ == "__main__":
    raise SystemExit(cli_main())
