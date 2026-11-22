# MEGATRON USER GUIDE — commands & how to use it

All three tools are Terminal commands. Every live order goes through
the **kill switch + confirmation** flow described at the bottom — read
that once before you trade real money.

| Command | What it is |
|---------|-----------|
| `megastocks` | AI Hedge Fund for stocks (LLM analysts + Alpaca) |
| `megacalls` | Covered-call scanner (research + Alpaca execution) |
| `megacrypto` | Solana command center (scanner + gated live swap) |
| `live on` / `live off` / `live status` | Master kill switch for ALL live trading |

---

## 1. ONE-TIME SETUP

Your keys live in `~/ai-stocks/.env`. Everything is OFF until keys +
the kill switch are set.

```bash
cd ~/ai-stocks
cp .env.example .env          # only if you don't have one yet
nano .env                     # fill in your real keys
```

The important keys (for **real** trading):

```
ALPACA_API_KEY=your-trading-api-key
ALPACA_SECRET_KEY=your-trading-secret
ALPACA_MODE=live              # live = real money | paper = test
ALPACA_MAX_NOTIONAL=500       # per-order dollar cap
```

Use the Alpaca **Trading** keys, not the Broker keys. The code talks to
`api.alpaca.markets` / `paper-api.alpaca.markets`.

Scout + Solana are separate (sections 6–7). If you skip them you can
ignore those keys.

---

## 2. 60-SECOND RESEARCH PROOF (no money)

```bash
megastocks              # menu appears
# > [1] Full AI Hedge Fund, pick a ticker (e.g. AMD), watch it analyze

megacalls               # menu appears
# > [1] Conservative scan, type tickers (e.g. AMD), watch candidates

megacrypto              # menu appears
# > [1] Arbitrage Scanner — research flag
# > [2] Jupiter Quote Center — see live quotes
```

Nothing here places orders. Research is always safe.

---

## 3. MEGASTOCKS — AI Hedge Fund

### Menu (`megastocks`)

| Option | What it does |
|--------|--------------|
| `[1]` Full AI Hedge Fund | Analyst models + risk management |
| `[2]` AI Hedge Fund + Local Ollama | Uses your local model, no API cost |
| `[3]` Full AI + Show Reasoning | Same as 1, prints each analyst's thesis |
| `[4]` Backtest | Historical validation for the ticker |
| `[5]` Ollama + Reasoning | Local model + reasoning output |
| `[8]` ⚡ AI Hedge Fund + Alpaca Execution | Research **then** confirmed live orders |
| `[6]` / `[7]` | Change tickers / Exit |

### Direct commands

```bash
megastocks                                  # interactive menu
megastocks AMD                              # jump straight to research
# real orders (default research-only):
poetry run python ~/ai-stocks/src/main.py --ticker AMD --alpaca
poetry run python ~/ai-stocks/src/main.py --ticker AMD --alpaca --alpaca-mode paper
```

### What `[8]` / `--alpaca` does

1. Runs the full hedge fund analysis.
2. Prints the plan: `AAPL BUY 10 sh ($1,900 est)` for every non-hold signal.
3. Checks: market open → tradable → shortable (for shorts) → notional cap.
4. Asks you `Place BUY x AAPL?` — **default No**; only `Yes` submits.
5. Reports each order id.

---

## 4. MEGACALLS — Covered Calls

### Menu (`megacalls`)

| Option | What it does |
|--------|--------------|
| `[1]` Conservative / Liquid | Strict filters (volume ≥ 100, OI ≥ 500) |
| `[2]` Wider Candidate Search | Looser filters (volume ≥ 50, OI ≥ 250) |
| `[3]` Test Universe | Small smoke-test universe |
| `[4]` Change Ticker(s) | Re-pick symbols |
| `[5]` ⚡ Scan + Alpaca Execution | Scan then execution; asks 1 or 2 for scan style |
| `[6]` Exit | |

### Direct scanner commands

```bash
cd ~/ai-stocks
poetry run python -m app.backend.services.covered_call_scanner AMD MU PLTR --top 10
poetry run python -m app.backend.services.covered_call_scanner --universe midcap --limit 50 --top 10
poetry run python -m app.backend.services.covered_call_scanner --universe test --limit 3 --top 2

# with confirmed Alpaca execution:
poetry run python -m app.backend.services.covered_call_scanner AMD --alpaca --contracts 1 --max-cap 500
```

### What `--alpaca` does

1. You pick a ranked candidate (`Which rank to execute?` → `1`).
2. Shows the plan: `Leg 1 BUY 100 x NVDA (est $13,540)` + `Leg 2 SELL 1 x NVDA261016C00110000`.
3. Refuses if the stock leg exceeds `--max-cap` / `ALPACA_MAX_NOTIONAL`.
4. Confirms each leg separately (`[y/N]`, default No).
5. Option orders use `asset_class="option"` with the OCC symbol.

---

## 5. MEGACRYPTO — Solana Command Center

### Menu (`megacrypto`)

| Option | What it does |
|--------|--------------|
| `[1]` 🔎 Arbitrage Scanner | Researches USDC↔SOL cross-venue quotes |
| `[2]` 🪐 Jupiter Quote Center | Live quote explorer |
| `[3]` 🧪 Paper Trading | Record-keeping only |
| `[4]` 👛 Wallet Center | Watch-only balance/status |
| `[5]` 🛡 Risk / Settings | Config display |
| `[6]` 🔐 Live Trading Status | Explains the gating model |
| `[7]` ⚡ Solana LIVE Swap (gated) | simulations + confirmation + real broadcast |
| `[8]` 🚪 Exit | |

### Gated swap `[7]`

```text
[1] Gate status (safe)          -> shows enable/keys/wallet readout
[2] Gated live swap BUY USDC->SOL   -> prompts USDC amount
[3] Gated live swap SELL SOL->USDC  -> prompts SOL amount
[4] Back
```

The swap pipeline, in order:
1. `MEGATRON_LIVE_EXECUTION=true` **and** `SOLANA_PRIVATE_KEY` **and**
   `SOLANA_WALLET_ADDRESS` **and** `JUPITER_API_KEY` (in `crypto_arb/.env`).
2. Fetches a fresh Jupiter quote.
3. **Simulates the swap on the RPC first.** A failed simulation cancels.
4. Asks you to type `YES` before anything is signed.
5. Signs with the private key and broadcasts **one** transaction.
6. Hard cap per swap: `MEGATRON_MAX_TRADE_USDC` (default **25 USDC**).

Relevant keys in `~/ai-stocks/.env`:

```
MEGATRON_LIVE_EXECUTION=false     # set true when you want real swaps
SOLANA_PRIVATE_KEY=your-base58-key
SOLANA_WALLET_ADDRESS=your-public-address
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
MEGATRON_MAX_TRADE_USDC=25
```

The public wallet address alone can build/simulate, but **broadcast
requires the private key** — that's how the current sign-in-code
executor works. If you don't want the key on disk, say so and I'll add
a Phantom wallet-connect path instead.

---

## 6. AI SCOUT WEBHOOK (opt-in execution)

Scout is the FastAPI backend. Only when every gate passes does it
submit an Alpaca order.

```bash
cd ~/ai-stocks
poetry run uvicorn app.backend.main:app --reload
curl http://localhost:8000/scout/status
```

Manual webhook test (no execution, just analysis):

```bash
curl -X POST http://localhost:8000/scout/webhook \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"AMD","action":"alert","price":465.58,"timeframe":"1D","message":"Test","source":"manual"}'
```

Webhook that requests execution (checks the gate chain):

```bash
curl -X POST http://localhost:8000/scout/webhook \
  -H 'Content-Type: application/json' \
  -d '{
    "ticker":"AMD","action":"buy","price":465.58,"qty":1,
    "execute":true,"secret":"YOUR_SCOUT_SECRET",
    "timeframe":"1D","message":"TradingView alert","source":"TradingView"
  }'
```

Gates for execution (all must pass):
1. `SCOUT_EXECUTION_ENABLED=true`
2. alert `secret` == `SCOUT_EXECUTION_SECRET`
3. `execute:true` and `qty > 0`, action in `buy/sell/short/cover`
4. AI classification is `HIGH_INTEREST` or `INVESTIGATE`
5. `alert_validation.status` is not `PRICE_MISMATCH`/`ALERT_DISCREPANCY`
6. US market open
7. notional under `ALPACA_MAX_NOTIONAL`
8. ticker tradable (+ shortable for shorts)
9. **kill switch ON** (section 8)

The webhook JSON response carries an `execution` block:
`{ "status": "ORDER_SUBMITTED", "order": { "id": ... } }` or
`{ "status": "REFUSED", "reason": "..." }`.

TradingView cannot call `localhost`. Point the alert at a public HTTPS
forward (ngrok/cloudflared) that routes to `/scout/webhook`.

---

## 7. BACKEND / WEB APP (optional)

```bash
cd ~/ai-stocks
poetry run uvicorn app.backend.main:app --reload   # backend + Scout
# in another terminal:
cd ~/ai-stocks/app/frontend
npm install
npm run dev                   # web UI at localhost:5173
```

Or both together: `bash run.sh` from `app/`.

---

## 8. THE KILL SWITCH — always OFF until you say on

This is the master control for **all** live trading, including Scout
webhooks and the Solana swap.

```bash
live            # or: live status — show current state
live on         # enable live trading
live off        # disable live trading
```

- Stored in `~/ai-stocks/.live_trading` (gitignored, plain `ON`/`OFF`).
- Every live path checks it as its **first** gate. OFF → everything
  refuses with `LIVE-KILL-SWITCH`.
- Long-lived processes (like the Scout backend) re-read the file per
  alert, so `live off` takes effect immediately, no restart.

## 9. THE SAFE REAL-TRADE ROUTINE

```bash
# 1) Every morning: check nothing leaks money
live status
megacrypto    # option [1]/[2] — research

# 2) When you actually want to trade:
live on

# 3) Run ONE confirmed path
megastocks    # option [8], approve each order, watch fills

# 4) Shut it back off the second you're done
live off
```

If a path refuses and you're not sure why, the reason is printed
(`live OFF`, market closed, cap exceeded, not tradable, etc.).

---

## 10. TROUBLESHOOTING

| Symptom | Cause / fix |
|---------|------------|
| `LIVE-KILL-SWITCH: live trading is OFF` | Run `live on` (then `live off` after) |
| `Alpaca keys are not configured` | `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` missing in `.env` |
| `ALPACA 401` | Wrong keys, or Trading vs Broker mismatch (use Trading) |
| `US market is closed. No orders placed` | AM/PM session gates; retry during market hours |
| `FUND_SAFETY: order estimate exceeds cap` | Lower the qty or raise `ALPACA_MAX_NOTIONAL` / `--max-cap` |
| `SOLANA_PRIVATE_KEY is not configured` | Not exported; set it for broadcast (or request wallet-connect) |
| `swap build failed: HTTP Error 422` | Bad `JUPITER_API_KEY` or quote expired; re-pull |
| Scanner found but nothing traded | Research mode is the default; execution is opt-in by design |