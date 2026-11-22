#!/usr/bin/env python3
"""MEGATRON // MEGACRYPTO command center.

Front-end for the existing Solana arbitrage research scanner.

Features:
- Jupiter quote center (research-only)
- Arbitrage scanner launcher
- Paper-trading ledger
- Watch-only Solana wallet status/balances
- Risk/settings display
- Explicitly gated live-trading status
- Clean Ctrl+C handling

IMPORTANT:
This command center does not hold private keys and does not sign,
broadcast, or automatically submit real-money transactions.
"""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
CRYPTO = ROOT / "crypto_arb"
SCANNER = CRYPTO / "solana_arb_scanner.py"
CONFIG = CRYPTO / "megacrypto_config.json"
PAPER_LOG = CRYPTO / "paper_trades.csv"
LIVE_EXECUTOR = CRYPTO / "solana_live_executor.py"

# Terminal colors: MEGACRYPTO is NEON YELLOW.
RESET = "\033[0m"
BOLD = "\033[1m"
NEON_YELLOW = "\033[38;5;226m"
BRIGHT_YELLOW = "\033[38;5;220m"
GREEN = "\033[38;5;46m"
RED = "\033[38;5;196m"
CYAN = "\033[38;5;51m"
WHITE = "\033[97m"
GRAY = "\033[38;5;245m"

# Solana / Jupiter research endpoints.
RPC_URL = "https://api.mainnet-beta.solana.com"
JUPITER_QUOTE_URL = "https://lite-api.jup.ag/swap/v1/quote"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGZwyTDt1v"
SOL_MINT = "So11111111111111111111111111111111111111112"

DEFAULTS = {
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


def c(text: object, color: str = WHITE, bold: bool = False) -> str:
    return f"{BOLD if bold else ''}{color}{text}{RESET}"


def clear() -> None:
    os.system("clear")


def pause(message: str = "  Press ENTER to continue...") -> None:
    try:
        input(c(message, NEON_YELLOW))
    except (KeyboardInterrupt, EOFError):
        print()


def load_config() -> dict:
    cfg = DEFAULTS.copy()

    if CONFIG.exists():
        try:
            data = json.loads(CONFIG.read_text())
            if isinstance(data, dict):
                cfg.update({k: data[k] for k in DEFAULTS if k in data})
        except (OSError, json.JSONDecodeError):
            pass

    return cfg


def save_config(cfg: dict) -> None:
    CRYPTO.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2) + "\n")

    try:
        CONFIG.chmod(0o600)
    except OSError:
        pass


def header(title: str = "MEGATRON // MEGACRYPTO") -> None:
    print(c("╔" + "═" * 66 + "╗", NEON_YELLOW, True))
    print(c("║" + f" ⚡ {title} ".center(66) + "║", BRIGHT_YELLOW, True))
    print(c("║" + " NEON YELLOW // SOLANA COMMAND CENTER ".center(66) + "║",
            NEON_YELLOW, True))
    print(c("╠" + "═" * 66 + "╣", NEON_YELLOW, True))
    print(c("║  📡 Live quotes       READY".ljust(67) + "║", WHITE))
    print(c("║  🧪 Paper trading    READY".ljust(67) + "║", WHITE))
    print(c("║  👛 Wallet           WATCH-ONLY".ljust(67) + "║", WHITE))
    print(c("║  🛡 Real execution   LOCKED".ljust(67) + "║", WHITE))
    print(c("╚" + "═" * 66 + "╝", NEON_YELLOW, True))
    print()


def valid_solana_address(value: str) -> bool:
    return bool(re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", value))


def http_json(url: str, payload: dict | None = None) -> dict:
    if payload is None:
        req = Request(
            url,
            headers={"User-Agent": "MEGATRON-MEGACRYPTO/2.0"},
        )
    else:
        body = json.dumps(payload).encode()
        req = Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "MEGATRON-MEGACRYPTO/2.0",
            },
        )

    with urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode())


def rpc(method: str, params: list) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    return http_json(RPC_URL, payload)


def wallet_balances(address: str) -> tuple[float, float]:
    sol_resp = rpc(
        "getBalance",
        [address, {"commitment": "confirmed"}],
    )
    sol = float(sol_resp["result"]["value"]) / 1_000_000_000

    token_resp = rpc(
        "getTokenAccountsByOwner",
        [
            address,
            {"mint": USDC_MINT},
            {"encoding": "jsonParsed", "commitment": "confirmed"},
        ],
    )

    usdc = 0.0
    for item in token_resp.get("result", {}).get("value", []):
        amount = (
            item.get("account", {})
            .get("data", {})
            .get("parsed", {})
            .get("info", {})
            .get("tokenAmount", {})
        )
        usdc += float(amount.get("uiAmountString") or 0)

    return sol, usdc


def jupiter_quote(amount_usdc: float) -> dict:
    """Get a research-only Jupiter quote for USDC -> SOL.

    This does not create, sign, or broadcast a transaction.
    """
    if amount_usdc <= 0:
        raise ValueError("Amount must be positive.")

    amount_base_units = int(round(amount_usdc * 1_000_000))

    params = urlencode(
        {
            "inputMint": USDC_MINT,
            "outputMint": SOL_MINT,
            "amount": amount_base_units,
            "slippageBps": 50,
        }
    )

    url = f"{JUPITER_QUOTE_URL}?{params}"
    return http_json(url)


def jupiter_center(cfg: dict) -> None:
    while True:
        clear()
        header("MEGATRON // JUPITER QUOTE CENTER")

        print(c("┌─ 🪐 JUPITER RESEARCH ROUTER", NEON_YELLOW, True))
        print(c("│ Status: LIVE QUOTE / RESEARCH ONLY", GREEN, True))
        print(c("│ Transaction signing: DISABLED", RED, True))
        print(c("│ Transaction broadcast: DISABLED", RED, True))
        print(c("└────────────────────────────────────────────", NEON_YELLOW))
        print()

        print(c("[1] Quote $10 USDC → SOL", CYAN))
        print(c("[2] Quote custom amount", CYAN))
        print(c("[3] Back", CYAN))

        try:
            choice = input(c("\n  Select: ", NEON_YELLOW, True)).strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return

        if choice == "3":
            return

        if choice not in {"1", "2"}:
            print(c("  ✖ Invalid selection.", RED, True))
            pause()
            continue

        if choice == "1":
            amount = 10.0
        else:
            try:
                amount = float(
                    input(c("  USDC amount: ", NEON_YELLOW)).strip()
                )
            except (ValueError, KeyboardInterrupt, EOFError):
                print(c("\n  ✖ Invalid amount.", RED, True))
                pause()
                continue

        clear()
        header("MEGATRON // JUPITER QUOTE")

        print(c("┌─ 📡 LIVE JUPITER QUOTE", NEON_YELLOW, True))
        print(c(f"│ Input:  ${amount:,.6f} USDC", WHITE))
        print(c("│ Output: SOL", WHITE))
        print(c("│ Mode:   RESEARCH ONLY", GREEN, True))
        print(c("└────────────────────────────────────────────", NEON_YELLOW))
        print()

        try:
            quote = jupiter_quote(amount)

            out_amount = int(quote.get("outAmount", 0)) / 1_000_000_000
            price_impact = quote.get("priceImpact")

            print(c(f"  ✓ Jupiter output: {out_amount:.9f} SOL", GREEN, True))

            if price_impact is not None:
                try:
                    print(c(
                        f"  ✓ Price impact: {float(price_impact) * 100:.4f}%",
                        WHITE,
                    ))
                except (TypeError, ValueError):
                    print(c(f"  ✓ Price impact: {price_impact}", WHITE))

            route_plan = quote.get("routePlan") or []
            print(c(f"  ✓ Route steps: {len(route_plan)}", WHITE))
            print()
            print(c("  🛡 No transaction was created or submitted.", GREEN, True))

        except HTTPError as exc:
            print(c(f"  ✖ Jupiter HTTP error: {exc.code}", RED, True))
            if exc.code == 429:
                print(c("  ⚠ Rate limit reached. Wait before retrying.", BRIGHT_YELLOW))
        except (URLError, TimeoutError) as exc:
            print(c(f"  ✖ Jupiter connection failed: {exc}", RED, True))
        except Exception as exc:
            print(c(f"  ✖ Quote failed: {exc}", RED, True))

        pause()


def wallet_center(cfg: dict) -> None:
    while True:
        clear()
        header("MEGATRON // WALLET CENTER")

        address = cfg.get("wallet_address", "")

        if address:
            print(c("┌─ 👛 WATCH-ONLY WALLET", NEON_YELLOW, True))
            print(c(f"│ Address: {address}", WHITE))

            try:
                sol, usdc = wallet_balances(address)
                print(c(f"│ SOL:     {sol:.6f}", GREEN))
                print(c(f"│ USDC:    ${usdc:,.2f}", GREEN))
                print(c("│ Network: Solana Mainnet", CYAN))
            except Exception as exc:
                print(c(f"│ Balance lookup failed: {exc}", RED))

            print(c("│", WHITE))
            print(c("│ 🔐 Private keys: NOT STORED", GREEN, True))
            print(c("│ 🔐 Seed phrase:  NOT STORED", GREEN, True))
            print(c("└─ WATCH-ONLY MODE", NEON_YELLOW, True))
        else:
            print(c("┌─ 👛 WALLET", NEON_YELLOW, True))
            print(c("│ No wallet address configured.", GRAY))
            print(c("└─ WATCH-ONLY MODE", NEON_YELLOW, True))

        print()
        print(c("[1] Add/change watch-only wallet", CYAN))
        print(c("[2] Refresh balance", CYAN))
        print(c("[3] Remove wallet", CYAN))
        print(c("[4] Back", CYAN))

        try:
            choice = input(
                c("\n  Select: ", NEON_YELLOW, True)
            ).strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return

        if choice == "1":
            try:
                value = input(
                    c("  Solana public address: ", NEON_YELLOW)
                ).strip()
            except (KeyboardInterrupt, EOFError):
                print()
                return

            if not valid_solana_address(value):
                print(c(
                    "\n  ✖ That does not look like a valid Solana public address.",
                    RED,
                    True,
                ))
                pause()
            else:
                cfg["wallet_address"] = value
                save_config(cfg)
                print(c(
                    "\n  ✓ Watch-only wallet saved.",
                    GREEN,
                    True,
                ))
                pause()

        elif choice == "2":
            continue

        elif choice == "3":
            cfg["wallet_address"] = ""
            save_config(cfg)
            print(c(
                "\n  ✓ Wallet removed from MEGACRYPTO configuration.",
                GREEN,
                True,
            ))
            pause()

        elif choice == "4":
            return


def paper_center(cfg: dict) -> None:
    CRYPTO.mkdir(parents=True, exist_ok=True)

    while True:
        clear()
        header("MEGATRON // PAPER TRADING")

        print(c("┌─ 🧪 PAPER ACCOUNT", NEON_YELLOW, True))
        print(c("│ No real funds are used.", GREEN, True))
        print(c(
            f"│ Max paper trade: ${cfg['max_trade_usdc']:.2f}",
            WHITE,
        ))
        print(c("└────────────────────────────────────────────", NEON_YELLOW))
        print()

        print(c("[1] Record a paper trade", CYAN))
        print(c("[2] View paper trade history", CYAN))
        print(c("[3] Back", CYAN))

        try:
            choice = input(
                c("\n  Select: ", NEON_YELLOW, True)
            ).strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return

        if choice == "1":
            try:
                ticker = input(
                    c("  Asset/pair [SOL/USDC]: ", NEON_YELLOW)
                ).strip().upper() or "SOL/USDC"

                amount = float(
                    input(c("  Capital USDC: ", NEON_YELLOW)).strip()
                )
                pnl = float(
                    input(c("  Simulated P&L USDC: ", NEON_YELLOW)).strip()
                )
            except (ValueError, KeyboardInterrupt, EOFError):
                print(c("  ✖ Enter valid numeric values.", RED, True))
                pause()
                continue

            if amount <= 0 or amount > cfg["max_trade_usdc"]:
                print(c(
                    f"  ✖ Amount must be > 0 and <= "
                    f"${cfg['max_trade_usdc']:.2f}.",
                    RED,
                    True,
                ))
                pause()
                continue

            new = not PAPER_LOG.exists()

            with PAPER_LOG.open("a", newline="") as f:
                writer = csv.writer(f)

                if new:
                    writer.writerow([
                        "timestamp",
                        "asset",
                        "capital_usdc",
                        "pnl_usdc",
                        "mode",
                    ])

                writer.writerow([
                    datetime.now(timezone.utc).isoformat(),
                    ticker,
                    f"{amount:.6f}",
                    f"{pnl:.6f}",
                    "PAPER",
                ])

            print(c(
                "  ✓ Paper trade recorded. No real transaction occurred.",
                GREEN,
                True,
            ))
            pause()

        elif choice == "2":
            if PAPER_LOG.exists():
                print(c("\n" + PAPER_LOG.read_text(), WHITE))
            else:
                print(c(
                    "\n  No paper trades recorded yet.",
                    GRAY,
                ))
            pause("\n  Press ENTER...")

        elif choice == "3":
            return


def settings_center(cfg: dict) -> None:
    fields = [
        ("max_trade_usdc", "Maximum trade USDC", float),
        ("daily_loss_limit_usdc", "Daily loss limit USDC", float),
        ("min_net_edge_pct", "Minimum net edge %", float),
        ("strong_edge_pct", "Strong edge %", float),
        ("max_price_impact_pct", "Maximum price impact %", float),
        ("slippage_bps", "Slippage bps", int),
    ]

    while True:
        clear()
        header("MEGATRON // RISK SETTINGS")

        print(c("┌─ 🛡 HARD RISK LIMITS", NEON_YELLOW, True))

        for key, label, _ in fields:
            print(c(f"│ {label:<28} {cfg[key]}", WHITE))

        print(c("└────────────────────────────────────────────", NEON_YELLOW))
        print()

        print(c("[1] Max trade", CYAN))
        print(c("[2] Daily loss limit", CYAN))
        print(c("[3] Minimum net edge", CYAN))
        print(c("[4] Strong edge", CYAN))
        print(c("[5] Maximum price impact", CYAN))
        print(c("[6] Slippage", CYAN))
        print(c("[7] Back", CYAN))

        try:
            choice = input(
                c("\n  Select: ", NEON_YELLOW, True)
            ).strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return

        if choice == "7":
            return

        if choice.isdigit() and 1 <= int(choice) <= 6:
            key, label, caster = fields[int(choice) - 1]

            try:
                value = caster(
                    input(c(f"  {label}: ", NEON_YELLOW)).strip()
                )

                if value <= 0:
                    raise ValueError

                cfg[key] = value
                save_config(cfg)

                print(c("  ✓ Setting saved.", GREEN, True))
            except (ValueError, KeyboardInterrupt, EOFError):
                print(c(
                    "  ✖ Invalid positive value.",
                    RED,
                    True,
                ))

            pause()


def stop_child_process(process: subprocess.Popen) -> None:
    """Stop the scanner cleanly without leaving a traceback."""
    if process.poll() is not None:
        return

    try:
        process.terminate()
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
            process.wait(timeout=3)
        except Exception:
            pass
    except Exception:
        pass


def launch_scanner(cfg: dict) -> None:
    if not SCANNER.exists():
        clear()
        header("MEGATRON // ARBITRAGE SCANNER")
        print(c(f"Scanner not found: {SCANNER}", RED, True))
        pause()
        return

    clear()
    header("MEGATRON // ARBITRAGE SCANNER")

    print(c("  Existing scanner preserved.", GREEN, True))
    print(c("  Research/paper mode is the default.", WHITE))
    print(c("  Real execution remains locked.", RED, True))
    print()
    print(c("[1] One scan", CYAN))
    print(c("[2] Continuous scan", CYAN))
    print(c("[3] Scan with live safety gate", CYAN))
    print(c("[4] Back", CYAN))

    try:
        choice = input(
            c("\n  Select: ", NEON_YELLOW, True)
        ).strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return

    if choice == "4":
        return

    args = [sys.executable, str(SCANNER)]

    if choice == "1":
        args += ["--once"]

    elif choice == "2":
        pass

    elif choice == "3":
        # The scanner's own safety gate decides whether an opportunity
        # qualifies. The command center still does not sign/broadcast.
        args += ["--once", "--live"]

    else:
        print(c("  ✖ Invalid selection.", RED, True))
        pause()
        return

    print()
    print(c("┌─ 🚀 STARTING ARBITRAGE SCANNER", NEON_YELLOW, True))
    print(c("│ Jupiter quotes: LIVE", WHITE))
    print(c("│ Research mode:  ACTIVE", GREEN, True))
    print(c("│ Live execution: LOCKED", RED, True))
    print(c("│ Real transactions: DISABLED", RED, True))
    print(c("│", WHITE))
    print(c("└─ Press Ctrl+C once to stop safely.", NEON_YELLOW))
    print()

    process: subprocess.Popen | None = None

    try:
        process = subprocess.Popen(args, cwd=CRYPTO)

        return_code = process.wait()

        print()

        if return_code == 0:
            print(c("✓ Scanner completed normally.", GREEN, True))
        else:
            print(c(
                f"Scanner exited with code {return_code}.",
                BRIGHT_YELLOW,
            ))

        pause("\n  Press ENTER to return to MEGACRYPTO...")

    except KeyboardInterrupt:
        print()
        print(c("🛑 STOP REQUEST RECEIVED", NEON_YELLOW, True))

        if process is not None:
            stop_child_process(process)

        print()
        print(c(
            "╔══════════════════════════════════════════════════════════════╗",
            NEON_YELLOW,
            True,
        ))
        print(c(
            "║          ⚡ MEGACRYPTO // SCAN STOPPED                    ║",
            BRIGHT_YELLOW,
            True,
        ))
        print(c(
            "╠══════════════════════════════════════════════════════════════╣",
            NEON_YELLOW,
            True,
        ))
        print(c(
            "║  🛑 User requested stop                                    ║",
            WHITE,
        ))
        print(c(
            "║  🛡 No live trade executed                                 ║",
            GREEN,
        ))
        print(c(
            "║  🛡 No transaction signed                                  ║",
            GREEN,
        ))
        print(c(
            "║  🛡 No funds moved                                         ║",
            GREEN,
        ))
        print(c(
            "╚══════════════════════════════════════════════════════════════╝",
            NEON_YELLOW,
            True,
        ))
        print()

        pause("  Press ENTER to return to MEGACRYPTO...")

    finally:
        if process is not None and process.poll() is None:
            stop_child_process(process)


def launch_live_executor(cfg: dict) -> None:
    if not LIVE_EXECUTOR.exists():
        clear()
        header("MEGATRON // LIVE SOLANA SWAP")
        print(c(
            f"Live executor not found: {LIVE_EXECUTOR}",
            RED,
            True,
        ))
        pause()
        return

    clear()
    header("MEGATRON // LIVE SOLANA SWAP")

    print(c(
        "  This launches the gated signer/executor in",
        WHITE,
    ))
    print(c(
        "  research-mode by default (gate status only).",
        WHITE,
    ))
    print()
    print(c("[1] Gate status (safe)", CYAN))
    print(c("[2] Gated live swap (BUY USDC→SOL)", CYAN))
    print(c("[3] Gated live swap (SELL SOL→USDC)", CYAN))
    print(c("[4] Back", CYAN))

    try:
        choice = input(
            c("\n  Select: ", NEON_YELLOW, True)
        ).strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return

    if choice == "4":
        return

    args = [sys.executable, str(LIVE_EXECUTOR)]

    if choice == "1":
        args += ["--gates"]

    elif choice == "2":
        try:
            usdc = input(
                c("\n  USDC amount: ", NEON_YELLOW, True)
            ).strip()
        except (KeyboardInterrupt, EOFError):
            return
        try:
            amount = float(usdc or "10")
        except ValueError:
            print(c(
                "  ✖ Invalid USDC amount.",
                RED,
                True,
            ))
            pause()
            return
        args += [
            "--swap",
            "--direction",
            "BUY",
            "--usdc",
            str(amount),
            "--confirm",
        ]

    elif choice == "3":
        try:
            sol = input(
                c("\n  SOL amount: ", NEON_YELLOW, True)
            ).strip()
        except (KeyboardInterrupt, EOFError):
            return
        try:
            amount = float(sol or "0.1")
        except ValueError:
            print(c(
                "  ✖ Invalid SOL amount.",
                RED,
                True,
            ))
            pause()
            return
        args += [
            "--swap",
            "--direction",
            "SELL",
            "--sol",
            str(amount),
            "--confirm",
        ]

    else:
        print(c("  ✖ Invalid selection.", RED, True))
        pause()
        return

    print()
    print(c("┌─ 🚀 STARTING GATED SOLANA EXECUTOR", NEON_YELLOW, True))
    print(c("│ Live execution: GATED", WHITE))
    print(c("│ Broadcast: only after explicit confirmation", WHITE))
    print(c("└─", NEON_YELLOW))
    print()

    try:
        return_code = subprocess.run(
            args,
            cwd=CRYPTO,
        ).returncode
    except KeyboardInterrupt:
        print(c(
            "\n🛑 Gated executor stopped by user.",
            NEON_YELLOW,
            True,
        ))
        return

    if return_code:
        print(c(
            "\n ✗ Gated executor did not complete.",
            RED,
            True,
        ))

    pause("\n  Press ENTER to return to MEGACRYPTO...")


def live_center(cfg: dict) -> None:
    clear()
    header("MEGATRON // LIVE TRADING")

    print(c("┌─ 🔐 LIVE EXECUTION", NEON_YELLOW, True))
    print(c("│ STATUS: LOCKED", RED, True))
    print(c("│ Wallet signing: DISABLED", WHITE))
    print(c("│ Auto-trading:   DISABLED", WHITE))
    print(c("│ Transaction broadcast: DISABLED", WHITE))
    print(c("│", WHITE))
    print(c(
        "│ The scanner can evaluate trade eligibility,",
        GRAY,
    ))
    print(c(
        "│ but this command center does not sign or",
        GRAY,
    ))
    print(c(
        "│ broadcast real-money transactions.",
        GRAY,
    ))
    print(c("└─ 🛡 SAFETY FIRST", NEON_YELLOW, True))
    print()

    print(c(
        "Real execution requires a separately reviewed signer/executor",
        GRAY,
    ))
    print(c(
        "with explicit confirmation and the same risk gates.",
        GRAY,
    ))

    pause("\n  Press ENTER to return...")


def main() -> int:
    cfg = load_config()

    while True:
        clear()
        header()

        print(c("┌─ COMMAND CENTER", NEON_YELLOW, True))
        print(c("│ [1] 🔎 Arbitrage Scanner", CYAN))
        print(c("│ [2] 🪐 Jupiter Quote Center", CYAN))
        print(c("│ [3] 🧪 Paper Trading", CYAN))
        print(c("│ [4] 👛 Wallet Center", CYAN))
        print(c("│ [5] 🛡 Risk / Settings", CYAN))
        print(c("│ [6] 🔐 Live Trading Status", CYAN))
        print(c("│ [7] ⚡ Solana LIVE Swap (gated)", CYAN))
        print(c("│ [8] 🚪 Exit", CYAN))
        print(c(
            "└────────────────────────────────────────────",
            NEON_YELLOW,
        ))
        print()

        wallet_status = (
            "CONFIGURED (watch-only)"
            if cfg.get("wallet_address")
            else "NOT CONFIGURED"
        )

        wallet_color = GREEN if cfg.get("wallet_address") else GRAY

        print(c(
            f"  Wallet: {wallet_status}",
            wallet_color,
        ))
        print(c("  Auto-trading: DISABLED", RED, True))
        print(c("  Real transactions: DISABLED", RED, True))

        try:
            choice = input(
                c("\n  Select: ", NEON_YELLOW, True)
            ).strip()
        except (KeyboardInterrupt, EOFError):
            print()
            print(c(
                "\nMEGATRON // MEGACRYPTO standing by. ⚡",
                NEON_YELLOW,
                True,
            ))
            return 0

        if choice == "1":
            launch_scanner(cfg)

        elif choice == "2":
            jupiter_center(cfg)

        elif choice == "3":
            paper_center(cfg)

        elif choice == "4":
            wallet_center(cfg)

        elif choice == "5":
            settings_center(cfg)

        elif choice == "6":
            live_center(cfg)

        elif choice == "7":
            launch_live_executor(cfg)

        elif choice == "8":
            clear()
            print(c(
                "MEGATRON // MEGACRYPTO standing by. ⚡",
                NEON_YELLOW,
                True,
            ))
            return 0

        else:
            print(c("  ✖ Invalid selection.", RED, True))
            pause()


if __name__ == "__main__":
    raise SystemExit(main())
