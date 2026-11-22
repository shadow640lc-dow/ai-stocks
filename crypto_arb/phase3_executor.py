#!/usr/bin/env python3 
 
""" 
MEGATRON // PHASE 3 EXECUTION LAYER 
 
Purpose: 
    Prepare and validate Solana swap execution. 
 
Safety: 
    - No private-key loading 
    - No transaction signing 
    - No transaction broadcasting 
    - Simulation only 
 
Phase 3C: 
    Scanner 
        ↓ 
    Fresh Jupiter quote 
        ↓ 
    Jupiter unsigned transaction 
        ↓ 
    Deserialize 
        ↓ 
    Validate 
        ↓ 
    Solana RPC simulation 
 
IMPORTANT: 
    Phase 3C currently tests ONE swap leg. 
    It is NOT a complete two-leg arbitrage execution. 
""" 
 
from __future__ import annotations 
 
import os 
import json 
import base64 
 
from urllib.request import Request, urlopen 
from dataclasses import dataclass 
 
from solders.pubkey import Pubkey 
from solders.transaction import VersionedTransaction 
 
 
# ================================================================ 
# CONFIGURATION 
# ================================================================ 
 
@dataclass(frozen=True) 
class ExecutionConfig: 
    rpc_url: str 
    wallet_address: str | None 
    live_execution_enabled: bool 
    max_trade_usdc: float 
 
 
def load_config() -> ExecutionConfig: 
    return ExecutionConfig( 
        rpc_url=os.getenv( 
            "SOLANA_RPC_URL", 
            "https://api.mainnet-beta.solana.com", 
        ), 
        wallet_address=os.getenv( 
            "SOLANA_WALLET_ADDRESS" 
        ), 
        live_execution_enabled=os.getenv( 
            "MEGATRON_LIVE_EXECUTION", 
            "false", 
        ).lower() == "true", 
        max_trade_usdc=float( 
            os.getenv( 
                "MEGATRON_MAX_TRADE_USDC", 
                "25.0", 
            ) 
        ), 
    ) 
 
 
# ================================================================ 
# RPC 
# ================================================================ 
 
def check_rpc( 
    rpc_url: str, 
    timeout: float = 10.0, 
) -> tuple[bool, str]: 
    """Check Solana JSON-RPC connectivity.""" 
 
    payload = json.dumps( 
        { 
            "jsonrpc": "2.0", 
            "id": 1, 
            "method": "getHealth", 
        } 
    ).encode() 
 
    request = Request( 
        rpc_url, 
        data=payload, 
        headers={ 
            "Content-Type": "application/json", 
        }, 
        method="POST", 
    ) 
 
    try: 
        with urlopen(request, timeout=timeout) as response: 
            data = json.loads( 
                response.read().decode() 
            ) 
 
        if data.get("result") == "ok": 
            return True, "ok" 
 
        return False, str(data) 
 
    except Exception as exc: 
        return False, str(exc) 
 
 
# ================================================================ 
# WALLET VALIDATION 
# ================================================================ 
 
def validate_wallet_address(address: str) -> Pubkey: 
    """ 
    Validate a public Solana wallet address. 
 
    This does NOT access private keys. 
    This does NOT sign. 
    """ 
 
    return Pubkey.from_string(address) 
 
 
# ================================================================
# TOKEN PREFLIGHT
# ================================================================

USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGZwyTDt1v"


def get_usdc_token_accounts(
    rpc_url: str,
    wallet_address: str,
    timeout: float = 10.0,
) -> tuple[bool, int, int, str]:
    """
    Read the wallet's USDC token accounts.

    Returns:
        (ok, account_count, total_raw_amount, detail)

    This is read-only. No signing or transaction submission occurs.
    """
    pubkey = validate_wallet_address(wallet_address)

    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                str(pubkey),
                {"mint": USDC_MINT},
                {
                    "encoding": "jsonParsed",
                    "commitment": "confirmed",
                },
            ],
        }
    ).encode()

    request = Request(
        rpc_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(
                response.read().decode()
            )

        if "error" in data:
            return (
                False,
                0,
                0,
                str(data["error"]),
            )

        values = (
            data.get("result", {})
            .get("value", [])
        )

        total_raw = 0

        for account in values:
            parsed = (
                account
                .get("account", {})
                .get("data", {})
                .get("parsed", {})
            )

            info = parsed.get("info", {})
            token_amount = info.get(
                "tokenAmount",
                {},
            )

            total_raw += int(
                token_amount.get(
                    "amount",
                    0,
                )
            )

        return (
            True,
            len(values),
            total_raw,
            "ok",
        )

    except Exception as exc:
        return (
            False,
            0,
            0,
            str(exc),
        )


def diagnose_transaction_accounts(
    rpc_url: str,
    transaction_bytes: bytes,
    timeout: float = 10.0,
) -> dict[str, object]:
    """
    Read-only transaction account preflight.

    Checks every static account referenced by the transaction.
    This is specifically useful for diagnosing AccountNotFound
    before simulation.

    Address Lookup Table addresses are checked separately by the
    ALT account itself; this function never mutates the transaction.
    """
    result: dict[str, object] = {
        "ok": False,
        "static_account_count": 0,
        "missing_static_accounts": [],
        "alt_count": 0,
        "missing_alts": [],
        "detail": "",
    }

    try:
        tx = VersionedTransaction.from_bytes(
            transaction_bytes
        )
        message = tx.message

        static_keys = [
            str(key)
            for key in message.account_keys
        ]

        result["static_account_count"] = len(
            static_keys
        )

        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getMultipleAccounts",
                "params": [
                    static_keys,
                    {
                        "encoding": "base64",
                        "commitment": "confirmed",
                    },
                ],
            }
        ).encode()

        request = Request(
            rpc_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urlopen(
            request,
            timeout=timeout,
        ) as response:
            data = json.loads(
                response.read().decode()
            )

        if "error" in data:
            result["detail"] = (
                "getMultipleAccounts failed: "
                + str(data["error"])
            )
            return result

        values = (
            data.get("result", {})
            .get("value", [])
        )

        missing = [
            static_keys[index]
            for index, account in enumerate(values)
            if account is None
        ]

        result["missing_static_accounts"] = missing

        alt_keys = [
            str(lookup.account_key)
            for lookup in message.address_table_lookups
        ]

        result["alt_count"] = len(alt_keys)

        if alt_keys:
            alt_payload = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "getMultipleAccounts",
                    "params": [
                        alt_keys,
                        {
                            "encoding": "base64",
                            "commitment": "confirmed",
                        },
                    ],
                }
            ).encode()

            alt_request = Request(
                rpc_url,
                data=alt_payload,
                headers={
                    "Content-Type": "application/json",
                },
                method="POST",
            )

            with urlopen(
                alt_request,
                timeout=timeout,
            ) as response:
                alt_data = json.loads(
                    response.read().decode()
                )

            if "error" in alt_data:
                result["detail"] = (
                    "ALT lookup failed: "
                    + str(alt_data["error"])
                )
                return result

            alt_values = (
                alt_data
                .get("result", {})
                .get("value", [])
            )

            missing_alts = [
                alt_keys[index]
                for index, account in enumerate(
                    alt_values
                )
                if account is None
            ]

            result["missing_alts"] = missing_alts

        result["ok"] = (
            len(missing) == 0
            and len(result["missing_alts"]) == 0
        )

        if result["ok"]:
            result["detail"] = (
                "all static accounts and ALT accounts "
                "were found"
            )
        else:
            result["detail"] = (
                "one or more referenced accounts are missing"
            )

        return result

    except Exception as exc:
        result["detail"] = str(exc)
        return result


def get_sol_balance( 
    rpc_url: str, 
    wallet_address: str, 
    timeout: float = 10.0, 
) -> tuple[bool, float, str]: 
    """Read public SOL balance.""" 
 
    pubkey = validate_wallet_address( 
        wallet_address 
    ) 
 
    payload = json.dumps( 
        { 
            "jsonrpc": "2.0", 
            "id": 1, 
            "method": "getBalance", 
            "params": [str(pubkey)], 
        } 
    ).encode() 
 
    request = Request( 
        rpc_url, 
        data=payload, 
        headers={ 
            "Content-Type": "application/json", 
        }, 
        method="POST", 
    ) 
 
    try: 
        with urlopen(request, timeout=timeout) as response: 
            data = json.loads( 
                response.read().decode() 
            ) 
 
        if "error" in data: 
            return ( 
                False, 
                0.0, 
                str(data["error"]), 
            ) 
 
        lamports = int( 
            data["result"]["value"] 
        ) 
 
        sol = lamports / 1_000_000_000 
 
        return True, sol, "ok" 
 
    except Exception as exc: 
        return False, 0.0, str(exc) 
 
 
def execution_status( 
    config: ExecutionConfig, 
) -> dict[str, object]: 
 
    wallet_valid = False 
 
    if config.wallet_address: 
        try: 
            validate_wallet_address( 
                config.wallet_address 
            ) 
            wallet_valid = True 
        except ValueError: 
            wallet_valid = False 
 
    return { 
        "rpc_configured": bool( 
            config.rpc_url 
        ), 
        "wallet_configured": bool( 
            config.wallet_address 
        ), 
        "wallet_valid": wallet_valid, 
        "live_execution_enabled": 
            config.live_execution_enabled, 
        "max_trade_usdc": 
            config.max_trade_usdc, 
        "signing_enabled": False, 
        "broadcast_enabled": False, 
    } 
 
 
# ================================================================ 
# JUPITER 
# ================================================================ 
 
JUPITER_SWAP_URL = ( 
    "https://api.jup.ag/swap/v1/swap" 
) 
 
 
def _post_json( 
    url: str, 
    payload: dict, 
    *, 
    headers: dict[str, str] | None = None, 
    timeout: float = 20.0, 
) -> dict: 
    """POST JSON and return decoded JSON.""" 
 
    request_headers = { 
        "Content-Type": "application/json", 
        "Accept": "application/json", 
    } 
 
    if headers: 
        request_headers.update(headers) 
 
    request = Request( 
        url, 
        data=json.dumps(payload).encode(), 
        headers=request_headers, 
        method="POST", 
    ) 
 
    with urlopen( 
        request, 
        timeout=timeout, 
    ) as response: 
        return json.loads( 
            response.read().decode() 
        ) 
 
 
# ================================================================ 
# PHASE 3C // BUILD 
# ================================================================ 
 
def build_jupiter_swap_transaction( 
    quote_response: dict, 
    user_public_key: str, 
    *, 
    timeout: float = 20.0, 
) -> tuple[bool, bytes | None, str]: 
    """ 
    Ask Jupiter to build an unsigned swap transaction. 
 
    IMPORTANT: 
        - No private key 
        - No signing 
        - No broadcasting 
    """ 
 
    pubkey = validate_wallet_address( 
        user_public_key 
    ) 
 
    api_key = os.getenv( 
        "JUPITER_API_KEY" 
    ) 
 
    if not api_key: 
        return ( 
            False, 
            None, 
            "JUPITER_API_KEY is not configured", 
        ) 
 
    payload = { 
        "quoteResponse": quote_response, 
        "userPublicKey": str(pubkey), 
        "wrapAndUnwrapSol": True, 
        "dynamicComputeUnitLimit": True, 
    } 
 
    try: 
        data = _post_json( 
            JUPITER_SWAP_URL, 
            payload, 
            headers={ 
                "x-api-key": api_key, 
            }, 
            timeout=timeout, 
        ) 
 
        if "error" in data: 
            return ( 
                False, 
                None, 
                str(data["error"]), 
            ) 
 
        encoded = data.get( 
            "swapTransaction" 
        ) 
 
        if not encoded: 
            return ( 
                False, 
                None, 
                "Jupiter returned no swapTransaction", 
            ) 
 
        raw_transaction = base64.b64decode( 
            encoded 
        ) 
 
        if not raw_transaction: 
            return ( 
                False, 
                None, 
                "Jupiter returned an empty transaction", 
            ) 
 
        # Deserialize only. 
        # No signing occurs here. 
        VersionedTransaction.from_bytes( 
            raw_transaction 
        ) 
 
        return ( 
            True, 
            raw_transaction, 
            "transaction built and deserialized", 
        ) 
 
    except Exception as exc: 
        return ( 
            False, 
            None, 
            str(exc), 
        ) 
 
 
# ================================================================ 
# PHASE 3C // SIMULATION 
# ================================================================ 
 
def simulate_transaction( 
    rpc_url: str, 
    transaction_bytes: bytes, 
    *, 
    timeout: float = 20.0, 
) -> tuple[bool, dict, str]: 
    """ 
    Simulate a Solana versioned transaction. 
 
    No signing. 
    No broadcasting. 
 
    Returns detailed RPC simulation diagnostics. 
    """ 
 
    encoded = base64.b64encode( 
        transaction_bytes 
    ).decode() 
 
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
 
    try: 
        request = Request( 
            rpc_url, 
            data=json.dumps( 
                payload 
            ).encode(), 
            headers={ 
                "Content-Type": 
                    "application/json", 
            }, 
            method="POST", 
        ) 
 
        with urlopen( 
            request, 
            timeout=timeout, 
        ) as response: 
            data = json.loads( 
                response.read().decode() 
            ) 
 
        # -------------------------------------------------------- 
        # RPC-level error 
        # -------------------------------------------------------- 
 
        if "error" in data: 
            error = data["error"] 
 
            return ( 
                False, 
                data, 
                "RPC SIMULATION ERROR: " 
                + json.dumps( 
                    error, 
                    indent=2, 
                ), 
            ) 
 
        value = ( 
            data 
            .get("result", {}) 
            .get("value") 
        ) 
 
        if value is None: 
            return ( 
                False, 
                data, 
                "RPC returned no simulation value", 
            ) 
 
        simulation_error = value.get( 
            "err" 
        ) 
 
        # -------------------------------------------------------- 
        # Successful simulation 
        # -------------------------------------------------------- 
 
        if simulation_error is None: 
 
            units = value.get( 
                "unitsConsumed" 
            ) 
 
            logs = value.get( 
                "logs" 
            ) or [] 
 
            detail_lines = [ 
                "SIMULATION PASSED" 
            ] 
 
            if units is not None: 
                detail_lines.append( 
                    f"COMPUTE UNITS: {units}" 
                ) 
 
            if logs: 
                detail_lines.append( 
                    "SIMULATION LOGS:" 
                ) 
 
                detail_lines.extend( 
                    f"  {log}" 
                    for log in logs 
                ) 
 
            return ( 
                True, 
                data, 
                "\n".join( 
                    detail_lines 
                ), 
            ) 
 
        # -------------------------------------------------------- 
        # Failed simulation 
        # -------------------------------------------------------- 
 
        detail_lines = [ 
            "SIMULATION FAILED: " 
            + str(simulation_error) 
        ] 
 
        units = value.get( 
            "unitsConsumed" 
        ) 
 
        if units is not None: 
            detail_lines.append( 
                f"COMPUTE UNITS: {units}" 
            ) 
 
        logs = value.get( 
            "logs" 
        ) or [] 
 
        if logs: 
            detail_lines.append( 
                "SIMULATION LOGS:" 
            ) 
 
            detail_lines.extend( 
                f"  {log}" 
                for log in logs 
            ) 
        else: 
            detail_lines.append( 
                "SIMULATION LOGS: NONE RETURNED" 
            ) 
 
        return ( 
            False, 
            data, 
            "\n".join( 
                detail_lines 
            ), 
        ) 
 
    except Exception as exc: 
        return ( 
            False, 
            {}, 
            "SIMULATION REQUEST ERROR: " 
            + str(exc), 
        ) 
 
 
# ================================================================ 
# TRANSACTION VALIDATION 
# ================================================================ 
 
def validate_transaction_bytes( 
    transaction_bytes: bytes, 
) -> tuple[bool, str]: 
    """ 
    Validate that bytes represent 
    a Solana versioned transaction. 
    """ 
 
    if not transaction_bytes: 
        return ( 
            False, 
            "transaction is empty", 
        ) 
 
    try: 
        tx = VersionedTransaction.from_bytes( 
            transaction_bytes 
        ) 
 
        if tx is None: 
            return ( 
                False, 
                "transaction deserialization returned None", 
            ) 
 
        return ( 
            True, 
            "versioned transaction deserialized successfully", 
        ) 
 
    except Exception as exc: 
        return ( 
            False, 
            "transaction validation failed: " 
            + str(exc), 
        ) 
 
 
# ================================================================ 
# PHASE 3C // COMPLETE PIPELINE 
# ================================================================ 
 
def phase3c_simulate( 
    rpc_url: str, 
    quote_response: dict, 
    user_public_key: str, 
) -> dict[str, object]: 
    """ 
    Complete Phase 3C pipeline: 
 
        Jupiter build 
            ↓ 
        deserialize 
            ↓ 
        validate 
            ↓ 
        simulate 
 
    No signing. 
    No broadcasting. 
    """ 
 
    result: dict[str, object] = { 
        "built": False, 
        "validated": False, 
        "simulated": False, 
        "simulation_error": None, 
    } 
 
    # ------------------------------------------------------------ 
    # BUILD 
    # ------------------------------------------------------------ 
 
    ( 
        built, 
        transaction_bytes, 
        build_detail, 
    ) = build_jupiter_swap_transaction( 
        quote_response, 
        user_public_key, 
    ) 
 
    result["built"] = built 
    result["build_detail"] = build_detail 
 
    if ( 
        not built 
        or transaction_bytes is None 
    ): 
        return result 
 
    # ------------------------------------------------------------ 
    # VALIDATE 
    # ------------------------------------------------------------ 
 
    ( 
        valid, 
        validation_detail, 
    ) = validate_transaction_bytes( 
        transaction_bytes 
    ) 
 
    result["validated"] = valid 
    result["validation_detail"] = ( 
        validation_detail 
    )

    if not valid:
        return result

    # ------------------------------------------------------------
    # READ-ONLY ACCOUNT PREFLIGHT
    # ------------------------------------------------------------

    account_preflight = diagnose_transaction_accounts(
        rpc_url,
        transaction_bytes,
    )

    result["account_preflight"] = account_preflight

    # ------------------------------------------------------------
    # SIMULATE
    # ------------------------------------------------------------
    # SIMULATE
    # ------------------------------------------------------------

    (
        simulated,
        simulation_data,
        simulation_detail,
    ) = simulate_transaction(
        rpc_url,
        transaction_bytes,
    )

    result["simulated"] = simulated
    result["simulation_detail"] = simulation_detail
    result["simulation"] = simulation_data

    if not simulated:
        result["simulation_error"] = simulation_detail

    return result 
 
 
# ================================================================ 
# STATUS 
# ================================================================ 
 
def print_status() -> None: 
 
    config = load_config() 
 
    status = execution_status( 
        config 
    ) 
 
    rpc_ok, rpc_detail = check_rpc( 
        config.rpc_url 
    ) 
 
    wallet_balance = None 
    balance_detail = ( 
        "wallet not configured" 
    ) 
 
    if ( 
        config.wallet_address 
        and rpc_ok 
    ): 
        ( 
            balance_ok, 
            wallet_balance, 
            balance_detail, 
        ) = get_sol_balance( 
            config.rpc_url, 
            config.wallet_address, 
        ) 
 
        if not balance_ok: 
            wallet_balance = None 
 
    print() 
 
    print( 
        "╔══════════════════════════════════════════════════════════════╗" 
    ) 
    print( 
        "║             MEGATRON // PHASE 3 EXECUTION                 ║" 
    ) 
    print( 
        "╠══════════════════════════════════════════════════════════════╣" 
    ) 
 
    print( 
        f"║ RPC CONFIGURED      " 
        f"{'YES' if status['rpc_configured'] else 'NO':<35}║" 
    ) 
 
    print( 
        f"║ RPC HEALTH          " 
        f"{'OK' if rpc_ok else 'FAILED':<35}║" 
    ) 
 
    print( 
        f"║ WALLET CONFIGURED   " 
        f"{'YES' if status['wallet_configured'] else 'NO':<35}║" 
    ) 
 
    print( 
        f"║ WALLET VALID        " 
        f"{'YES' if status['wallet_valid'] else 'NO':<35}║" 
    ) 
 
    if wallet_balance is not None: 
        print( 
            f"║ SOL BALANCE         " 
            f"{wallet_balance:.9f} SOL" 
            f"{' ':<21}║" 
        ) 
    else: 
        print( 
            "║ SOL BALANCE         NOT QUERIED                         ║" 
        ) 
 
    print( 
        f"║ LIVE EXECUTION      " 
        f"{'ON' if status['live_execution_enabled'] else 'OFF':<35}║" 
    ) 
 
    print( 
        "║ SIGNING             DISABLED                            ║" 
    ) 
 
    print( 
        "║ BROADCAST           DISABLED                            ║" 
    ) 
 
    print( 
        "║ MODE                BUILD / VALIDATE / SIMULATE        ║" 
    ) 
 
    print( 
        "╚══════════════════════════════════════════════════════════════╝" 
    ) 
 
    print() 
 
 
# ================================================================ 
# PHASE 3C // CLI TEST 
# ================================================================ 
 
def phase3c_cli_test( 
    usdc_amount: float, 
) -> int: 
    """ 
    Run safe Phase 3C test. 
 
    Flow: 
 
        scanner 
            ↓ 
        fresh BUY quotes 
            ↓ 
        best route 
            ↓ 
        Jupiter transaction build 
            ↓ 
        deserialize 
            ↓ 
        validate 
            ↓ 
        simulate 
 
    Safety: 
        - no private key 
        - no signing 
        - no broadcasting 
    """ 
 
    config = load_config() 
 
    print() 
 
    print( 
        "╔══════════════════════════════════════════════════════════════╗" 
    ) 
    print( 
        "║                MEGATRON // PHASE 3C TEST                  ║" 
    ) 
    print( 
        "╠══════════════════════════════════════════════════════════════╣" 
    ) 
    print( 
        "║ MODE                BUILD / VALIDATE / SIMULATE           ║" 
    ) 
    print( 
        "║ SIGNING             DISABLED                              ║" 
    ) 
    print( 
        "║ BROADCAST           DISABLED                              ║" 
    ) 
    print( 
        f"║ RESEARCH SIZE       ${usdc_amount:.2f} USDC" 
        f"{' ':<32}║" 
    ) 
    print( 
        "╚══════════════════════════════════════════════════════════════╝" 
    ) 
 
    print() 
 
    # ------------------------------------------------------------ 
    # AMOUNT VALIDATION 
    # ------------------------------------------------------------ 
 
    if usdc_amount <= 0: 
        print( 
            "❌ USDC amount must be greater than 0." 
        ) 
        return 2 
 
    if ( 
        usdc_amount 
        > config.max_trade_usdc 
    ): 
        print( 
            "❌ RESEARCH AMOUNT EXCEEDS SAFETY LIMIT" 
        ) 
        print( 
            f"   Requested: ${usdc_amount:.2f}" 
        ) 
        print( 
            f"   Maximum:   ${config.max_trade_usdc:.2f}" 
        ) 
        return 2 
 
    # ------------------------------------------------------------ 
    # WALLET 
    # ------------------------------------------------------------ 
 
    if not config.wallet_address: 
        print( 
            "❌ PHASE 3C TEST REQUIRES " 
            "SOLANA_WALLET_ADDRESS" 
        ) 
        print( 
            "   Public wallet address only." 
        ) 
        print( 
            "   No private key is required." 
        ) 
        return 2 
 
    try: 
        validate_wallet_address( 
            config.wallet_address 
        ) 
    except ValueError as exc: 
        print( 
            f"❌ INVALID WALLET PUBLIC KEY: {exc}" 
        ) 
        return 2 
 
    # ------------------------------------------------------------ 
    # RPC 
    # ------------------------------------------------------------ 
 
    rpc_ok, rpc_detail = check_rpc( 
        config.rpc_url 
    ) 
 
    print( 
        f"RPC HEALTH           " 
        f"{'OK' if rpc_ok else 'FAILED'}" 
    ) 
 
    if not rpc_ok: 
        print( 
            f"RPC DETAIL           {rpc_detail}" 
        ) 
        return 1
    print(
        "WALLET PUBLIC KEY    VALID"
    )

    # ------------------------------------------------------------
    # WALLET FUNDING PREFLIGHT
    # ------------------------------------------------------------

    sol_ok, sol_balance, sol_detail = get_sol_balance(
        config.rpc_url,
        config.wallet_address,
    )

    if sol_ok:
        print(
            f"SOL BALANCE          {sol_balance:.9f} SOL"
        )
    else:
        print(
            f"SOL BALANCE          UNAVAILABLE: {sol_detail}"
        )

    usdc_ok, usdc_accounts, usdc_raw, usdc_detail = (
        get_usdc_token_accounts(
            config.rpc_url,
            config.wallet_address,
        )
    )

    if usdc_ok:
        usdc_balance = usdc_raw / 1_000_000
        print(
            f"USDC ACCOUNTS        {usdc_accounts}"
        )
        print(
            f"USDC BALANCE         {usdc_balance:.6f} USDC"
        )

        if usdc_accounts == 0:
            print(
                "⚠ USDC SOURCE ACCOUNT NOT FOUND"
            )
            print(
                "  A USDC -> SOL simulation cannot"
            )
            print(
                "  spend USDC without a source token account."
            )
    else:
        print(
            f"USDC PREFLIGHT       FAILED: {usdc_detail}"
        )

    print()

    # ------------------------------------------------------------
    # SCANNER IMPORT 
    # ------------------------------------------------------------ 
 
    try: 
        import solana_arb_scanner as scanner 
    except Exception as exc: 
        print( 
            "❌ SCANNER IMPORT FAILED" 
        ) 
        print( 
            f"   {exc}" 
        ) 
        return 1 
 
    # ------------------------------------------------------------ 
    # FRESH QUOTES 
    # ------------------------------------------------------------ 
 
    amount_raw = int( 
        round( 
            usdc_amount * 1_000_000 
        ) 
    ) 
 
    print( 
        "PHASE 3C // FRESH QUOTE" 
    ) 
 
    print( 
        f"REQUEST             ${usdc_amount:.2f} USDC" 
    ) 
 
    print( 
        "DIRECTION            USDC -> SOL" 
    ) 
 
    print() 
 
    best_quote = None 
 
    for venue in scanner.DEFAULT_VENUES: 
 
        try: 
            quote = scanner.get_quote( 
                venue, 
                "BUY", 
                amount_raw, 
                scanner.DEFAULT_SLIPPAGE_BPS, 
                timeout=scanner.DEFAULT_TIMEOUT, 
                max_retries=1, 
                backoff_seconds=1.0, 
                request_delay=1.0, 
            ) 
 
            if quote is None: 
                print( 
                    f"  ✗ {venue:<18} NO QUOTE" 
                ) 
                continue 
 
            print( 
                f"  ✓ {venue:<18} " 
                f"OUT {quote.output_amount} SOL-raw" 
            ) 
 
            if ( 
                best_quote is None 
                or quote.output_amount 
                > best_quote.output_amount 
            ): 
                best_quote = quote 
 
        except Exception as exc: 
            print( 
                f"  ✗ {venue:<18} ERROR" 
            ) 
            print( 
                f"      {exc}" 
            ) 
 
    if best_quote is None: 
        print() 
        print( 
            "❌ NO BUY QUOTE AVAILABLE" 
        ) 
        return 1 
 
    # ------------------------------------------------------------ 
    # BEST ROUTE 
    # ------------------------------------------------------------ 
 
    print() 
 
    print( 
        "BEST BUY ROUTE" 
    ) 
 
    print( 
        f"VENUE              " 
        f"{best_quote.venue}" 
    ) 
 
    print( 
        f"INPUT              " 
        f"${usdc_amount:.2f} USDC" 
    ) 
 
    print( 
        f"OUTPUT             " 
        f"{best_quote.output_amount} SOL-raw" 
    ) 
 
    print( 
        f"PRICE IMPACT       " 
        f"{best_quote.price_impact_pct:.6f}%" 
    ) 
 
    print( 
        f"ROUTE              " 
        f"{best_quote.route_labels}" 
    ) 
 
    print() 
 
    # ------------------------------------------------------------ 
    # BUILD 
    # ------------------------------------------------------------ 
 
    print( 
        "PHASE 3C // BUILD" 
    ) 
 
    print( 
        "Requesting unsigned Jupiter transaction..." 
    ) 
 
    result = phase3c_simulate( 
        config.rpc_url, 
        best_quote.raw, 
        config.wallet_address, 
    ) 
 
    # ------------------------------------------------------------ 
    # BUILD RESULT 
    # ------------------------------------------------------------ 
 
    if result.get("built"): 
        print() 
        print( 
            "PHASE 3C BUILD       PASSED" 
        ) 
        print( 
            "BUILD DETAIL         " 
            f"{result.get('build_detail')}" 
        ) 
    else: 
        print() 
        print( 
            "PHASE 3C BUILD       FAILED" 
        ) 
        print( 
            "BUILD DETAIL         " 
            f"{result.get('build_detail')}" 
        ) 
 
        print() 
        print( 
            "🛡 NO PRIVATE KEY" 
        ) 
        print( 
            "🛡 NO SIGNING" 
        ) 
        print( 
            "🛡 NO BROADCAST" 
        ) 
 
        return 1 
 
    # ------------------------------------------------------------ 
    # VALIDATION RESULT 
    # ------------------------------------------------------------ 
 
    if result.get("validated"): 
        print( 
            "PHASE 3C VALIDATE    PASSED" 
        ) 
        print( 
            "VALIDATION DETAIL    " 
            f"{result.get('validation_detail')}" 
        ) 
    else: 
        print( 
            "PHASE 3C VALIDATE    FAILED" 
        ) 
        print( 
            "VALIDATION DETAIL    " 
            f"{result.get('validation_detail')}" 
        ) 
 
        print() 
        print( 
            "🛡 NO PRIVATE KEY" 
        ) 
        print( 
            "🛡 NO SIGNING" 
        ) 
        print( 
            "🛡 NO BROADCAST" 
        ) 
 
        return 1

    # ------------------------------------------------------------
    # ACCOUNT PREFLIGHT RESULT
    # ------------------------------------------------------------

    preflight = result.get(
        "account_preflight",
        {},
    )

    if isinstance(preflight, dict):
        print()
        print("PHASE 3C ACCOUNT PREFLIGHT")
        print(
            "STATIC ACCOUNTS       "
            f"{preflight.get('static_account_count', 'UNKNOWN')}"
        )
        print(
            "ALT TABLES             "
            f"{preflight.get('alt_count', 'UNKNOWN')}"
        )

        missing_static = preflight.get(
            "missing_static_accounts",
            [],
        )
        missing_alts = preflight.get(
            "missing_alts",
            [],
        )

        print(
            "MISSING STATIC        "
            f"{len(missing_static)}"
        )
        print(
            "MISSING ALTS          "
            f"{len(missing_alts)}"
        )
        print(
            "PREFLIGHT DETAIL      "
            f"{preflight.get('detail', '')}"
        )

        if missing_static:
            print("MISSING STATIC KEYS:")
            for key in missing_static:
                print(f"  {key}")

        if missing_alts:
            print("MISSING ALT KEYS:")
            for key in missing_alts:
                print(f"  {key}")

    # ------------------------------------------------------------
    # SIMULATION RESULT
    # ------------------------------------------------------------

    if result.get("simulated"):
 
 
        print( 
            "PHASE 3C SIMULATE    PASSED" 
        ) 
 
        print( 
            "SIMULATION DETAIL" 
        ) 
 
        print( 
            result.get( 
                "simulation_detail", 
                "SIMULATION PASSED", 
            ) 
        ) 
 
    else: 
 
        print( 
            "PHASE 3C SIMULATE    FAILED" 
        ) 
 
        print( 
            "SIMULATION DETAIL" 
        )
        simulation_error = result.get(
            "simulation_error",
            "Unknown simulation error",
        )

        print(simulation_error)

        simulation_blob = str(
            simulation_error
        )

        if "AccountNotFound" in simulation_blob:
            print()
            print("ACCOUNTNOTFOUND DIAGNOSTIC")
            print(
                "The transaction built successfully,"
            )
            print(
                "but the RPC could not resolve an account"
            )
            print(
                "needed during simulation."
            )

            if usdc_ok and usdc_accounts == 0:
                print(
                    "LIKELY CAUSE: wallet has no USDC token account."
                )
            else:
                print(
                    "See PHASE 3C ACCOUNT PREFLIGHT above"
                )
                print(
                    "for missing static/ALT account details."
                )

    # ------------------------------------------------------------
    # SAFETY SUMMARY 
    # ------------------------------------------------------------ 
 
    print() 
    print( 
        "🛡 NO PRIVATE KEY" 
    ) 
    print( 
        "🛡 NO SIGNING" 
    ) 
    print( 
        "🛡 NO BROADCAST" 
    ) 
 
    return ( 
        0 
        if result.get("simulated") 
        else 1 
    ) 
 
 
# ================================================================ 
# CLI 
# ================================================================ 
 
if __name__ == "__main__": 
 
    import argparse 
 
    parser = argparse.ArgumentParser( 
        description=( 
            "MEGATRON Phase 3 execution layer" 
        ) 
    ) 
 
    parser.add_argument( 
        "--phase3c-test", 
        action="store_true", 
        help=( 
            "Run the safe Phase 3C " 
            "build/validate/simulate test" 
        ), 
    ) 
 
    parser.add_argument( 
        "--usdc", 
        type=float, 
        default=10.0, 
        help=( 
            "USDC research amount " 
            "for Phase 3C test" 
        ), 
    ) 
 
    args = parser.parse_args() 
 
    if args.usdc <= 0: 
        raise SystemExit( 
            "--usdc must be greater than 0." 
        ) 
 
    if args.phase3c_test: 
 
        raise SystemExit( 
            phase3c_cli_test( 
                args.usdc 
            ) 
        ) 
 
    print_status()