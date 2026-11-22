# AI-STOCKS OPERATIONS MANUAL

This manual is based on the current repository at `~/ai-stocks`. Run commands from the directory stated in each section.

## 1. Safety / Research-Only Rules

- The AI Hedge Fund can produce research decisions and run simulated backtests.
- Covered Call Hunter is research-only.
- Covered Call Scanner is research-only.
- Decision Engine is research-only.
- Scout is alert-only; its API responses include `trading_enabled: false`.
- No command documented here places a live brokerage order or connects to a broker.

These tools can help structure research. They do not guarantee profitable trades.

## 2. QUICK START 🚀

Use separate terminals for long-running services.

### Terminal 1 — backend

```bash
cd ~/ai-stocks
poetry install
cp .env.example .env
poetry run uvicorn app.backend.main:app --reload
```

Edit `.env` before running an LLM-backed workflow. Add `FINANCIAL_DATASETS_API_KEY` for financial-data workflows and a supported cloud-model key, or use Ollama for local models. If `.env` already exists, do not overwrite it with `cp`.

Expected backend URLs:

- API/docs: `http://localhost:8000/docs`
- Scout: `http://localhost:8000/scout/status`

Stop it with `Ctrl+C` in Terminal 1.

### Terminal 2 — frontend

```bash
cd ~/ai-stocks/app/frontend
npm install
npm run dev
```

Open the Vite URL, normally `http://localhost:5173`. Stop it with `Ctrl+C`.

### Terminal 3 — research commands

Run a small Covered Call scan:

```bash
cd ~/ai-stocks
poetry run python -m app.backend.services.covered_call_scanner --universe test --limit 3 --top 2
```

Run the AI Hedge Fund with local Ollama:

```bash
cd ~/ai-stocks
poetry run python src/main.py --ticker AMD --ollama
```

Check Scout:

```bash
curl http://localhost:8000/scout/status
```

### TWO-TERMINAL WORKFLOW

Use two terminal windows when running the AI Stocks web services and research tools. Keep the backend terminal open while anything needs the FastAPI API. Use the second terminal for the scanner or frontend.

#### TERMINAL 1 — BACKEND

From the repository root, run:

```bash
cd ~/ai-stocks
poetry run uvicorn app.backend.main:app --reload
```

Keep Terminal 1 running. This starts the FastAPI backend on port `8000`. A successful startup should include:

```text
Application startup complete.
```

Do not close Terminal 1 while using the frontend, Scout, or backend API. Stop the server safely with `Ctrl+C` in Terminal 1.

If Uvicorn reports `Address already in use`, another process already owns port `8000`—often another backend instance. Check it before stopping anything:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

Stop only the confirmed old process by its displayed PID:

```bash
kill <PID>
```

Then rerun the backend command. Do not kill an unknown process.

#### TERMINAL 2 — SCANNER / RESEARCH

Open a second terminal. The research scan runs there:

```bash
cd ~/ai-stocks
poetry run python -m app.backend.services.covered_call_scanner --universe test --limit 3 --top 2
```

Terminal 2 is where the research scan runs. The scanner uses the project’s data/service integrations as required; it is not the FastAPI server itself. It is research-only: it does not automatically buy stocks, sell covered calls, or submit orders.

- `--universe test` selects the small built-in liquid test universe.
- `--limit 3` scans at most three underlying stocks from that universe.
- `--top 2` displays at most two final contracts. It does not reduce the number of qualifying contracts evaluated by the Decision Engine.

For a larger mid-cap scan:

```bash
cd ~/ai-stocks
poetry run python -m app.backend.services.covered_call_scanner --universe midcap --limit 20 --top 10
```

For direct tickers, use positional arguments (there is no `--tickers` option for this scanner):

```bash
cd ~/ai-stocks
poetry run python -m app.backend.services.covered_call_scanner AMD MU PLTR SOFI HOOD --top 10
```

#### FRONTEND TWO-TERMINAL WORKFLOW

For the web UI, use the same Terminal 1 backend and use Terminal 2 for Vite:

Terminal 1:

```bash
cd ~/ai-stocks
poetry run uvicorn app.backend.main:app --reload
```

Terminal 2:

```bash
cd ~/ai-stocks/app/frontend
npm run dev
```

The frontend normally runs at `http://localhost:5173` and the backend at `http://localhost:8000`, matching the existing project documentation and frontend configuration. Keep both terminals running while using the web UI.

#### WHICH TERMINAL DO I USE?

| Activity | Terminal |
| --- | --- |
| Backend/API | Terminal 1 |
| Scanner/research | Terminal 2 |
| Frontend | Terminal 2 when running the web UI |
| Ollama | Leave its service running separately when required |
| Compile/tests | Any terminal; preferably with the backend stopped while troubleshooting |

## 3. COMMAND CHEAT SHEET

| Command | What it does | When to use it | Safe/research status |
| --- | --- | --- | --- |
| `poetry install` | Installs root Python dependencies. | First setup or missing Python packages. | Setup only. |
| `poetry run python src/main.py --ticker AMD --ollama` | Runs the AI Hedge Fund with local LLM selection. | Analyst-driven research. | Research only; no broker orders. |
| `poetry run python src/backtester.py --ticker AMD` | Runs the legacy backtest CLI. | Historical simulation. | Simulated only. |
| `poetry run backtester --ticker AMD` | Runs the modular backtester console entry point. | Historical simulation. | Simulated only. |
| `poetry run uvicorn app.backend.main:app --reload` | Starts FastAPI and Scout endpoints. | Web app, API, Scout. | Service; no broker orders. |
| `npm run dev` | Starts the Vite frontend. | Web UI development/use. | UI only. |
| `bash run.sh` from `app/` | Starts backend and frontend together. | Convenient local web startup. | Service launcher; no broker orders. |
| `poetry run python -m app.backend.services.covered_call_scanner --universe test --limit 3 --top 2` | Small live-data covered-call scan. | Verify scanner or research candidates. | Research only. |
| `poetry run python -m v2.backtesting` | Runs the fixed-universe v2 PEAD demo. | v2 quantitative research. | Simulated only. |
| `poetry run python -m v2.event_study` | Runs the fixed-universe earnings event study. | v2 research. | Research only. |
| `poetry run python src/utils/ollama.py --check-model llama3.1:latest` | Checks Ollama and one model. | Before local-model workflows. | Local model management only. |
| `./run.sh build` from `docker/` | Builds the Docker image. | Docker setup. | Setup only. |
| `./run.sh --ticker AMD main` from `docker/` | Runs the main workflow in Docker. | Containerized research. | Research only. |
| `./run.sh --ticker AMD backtest` from `docker/` | Runs the backtester in Docker. | Containerized simulation. | Simulated only. |

## 4. AI HEDGE FUND

### Main CLI: `src/main.py`

Type: **RUNNABLE CLI**. It runs the existing analyst workflow, risk management, and portfolio-management stages, then prints decision support output.

Run with Ollama:

```bash
cd ~/ai-stocks
poetry run python src/main.py --ticker AMD --ollama
```

Run with a cloud-model selection:

```bash
cd ~/ai-stocks
poetry run python src/main.py --ticker AMD
```

Run multiple comma-separated tickers:

```bash
poetry run python src/main.py --ticker AMD,MU,PLTR
```

Run a defined date range:

```bash
poetry run python src/main.py --ticker AMD --start-date 2026-01-01 --end-date 2026-08-01
```

Set initial cash and short-margin requirement:

```bash
poetry run python src/main.py --ticker AMD --initial-cash 100000 --margin-requirement 0
```

Show agent reasoning:

```bash
poetry run python src/main.py --ticker AMD --show-reasoning
```

The CLI prompts interactively for analysts and, unless a valid `--model` is supplied, for the model. It requires Financial Datasets data access and either a cloud-model credential or a working Ollama server/model.

Expected output: analyst selections, model selection, colored analyst signals, risk/portfolio output, and final decisions. Stop with `Ctrl+C`.

### AI HEDGE FUND — CLI

The default CLI presentation is a neon-blue research terminal. It keeps the original analyst payloads and decisions intact, but presents them in this order:

1. Executive Summary
2. Analyst Consensus
3. Analyst Grid
4. Fundamentals (when returned)
5. Individual analyst details and wrapped reasoning
6. Fund Decision
7. Portfolio Summary
8. Research/simulation safety footer

Basic run:

```bash
cd ~/ai-stocks
poetry run python src/main.py --ticker AMD --ollama
```

The command still prompts for analyst selection and Ollama model selection. The selected model and selected analysts are unchanged; only terminal presentation is reorganized.

Reading the terminal:

- `🟢 BULLISH`, `🟡 NEUTRAL`, and `🔴 BEARISH` are the analyst signals returned by the existing agents.
- Confidence is the confidence value returned by each analyst. The executive consensus confidence is a display summary derived from the visible analyst confidences; it does not feed back into decision-making.
- `BUY`, `HOLD`, `SELL`, `SHORT`, and `COVER` are the existing portfolio-manager actions. The formatter does not calculate or alter them.
- Consensus counts show how many visible analyst signals are bullish, neutral, or bearish.
- The portfolio panel summarizes the existing action, quantity, and confidence for each ticker.
- Nested reasoning dictionaries are extracted into readable sections. The original dictionaries remain in the result object; they are simply not dumped as raw JSON by default.

The final panel always states `NO AUTOMATIC TRADE EXECUTED` and `RESEARCH / SIMULATION MODE`. This CLI remains decision support and simulation only.

The Python 3.14/Pydantic V1 compatibility warning may appear before the report because it is emitted by a dependency during import. It represents a real compatibility warning and is not globally suppressed by the formatter. Use the project’s supported Poetry/Python environment and treat the warning as a dependency-maintenance item rather than hiding it.

### Legacy backtester: `src/backtester.py`

Type: **RUNNABLE CLI**. It simulates the hedge-fund workflow over historical dates.

Small example:

```bash
cd ~/ai-stocks
poetry run python src/backtester.py --ticker AMD --start-date 2026-07-01 --end-date 2026-08-01
```

Ollama variant:

```bash
poetry run python src/backtester.py --ticker AMD --ollama
```

Expected output: simulated daily trades, portfolio values, and performance metrics. `Ctrl+C` stops it; the backtester attempts to show partial results. It uses remote/historical data but does not place trades.

### Modular backtester

Type: **RUNNABLE CLI**, registered by Poetry as `backtester = "src.backtesting.cli:main"`.

```bash
cd ~/ai-stocks
poetry run backtester --ticker AMD
```

Small defined period:

```bash
poetry run backtester --ticker AMD --start-date 2026-07-01 --end-date 2026-08-01 --initial-capital 100000
```

Expected output includes `ENGINE RUN COMPLETE`, total return, Sharpe, Sortino, and maximum drawdown. It is a simulation only.

## 5. COVERED CALL SYSTEM 📞

### Covered Call Scanner

Type: **RUNNABLE CLI**: `app/backend/services/covered_call_scanner.py`.

The scanner has two stages:

1. Fetch underlying stock data and apply the existing stock filters.
2. Fetch eligible option chains and apply the existing option filters.

Qualifying contracts retain their Hunter score, then each is evaluated by the Decision Engine before report display.

Small test scan:

```bash
cd ~/ai-stocks
poetry run python -m app.backend.services.covered_call_scanner --universe test --limit 3 --top 2
```

Mid-cap scan:

```bash
poetry run python -m app.backend.services.covered_call_scanner --universe midcap --limit 50 --top 10
```

Specific tickers are positional arguments, not `--tickers`:

```bash
poetry run python -m app.backend.services.covered_call_scanner AMD MU PLTR --top 10
```

Available scanner options:

| Option | Meaning |
| --- | --- |
| `--universe test` | Uses the small built-in liquid test universe. |
| `--universe midcap` | Uses the built-in mid-cap universe. |
| positional tickers | Uses only the provided symbols. |
| `--limit N` | Limits how many underlying stocks are scanned. |
| `--top N` | Limits how many final contracts are **displayed**. |
| `--min-days N` / `--max-days N` | Minimum/maximum days to expiration. |
| `--min-delta X` / `--max-delta X` | Call delta range. |
| `--min-otm X` / `--max-otm X` | Strike distance above stock price, in percent. |
| `--min-volume N` | Minimum option volume. |
| `--min-oi N` | Minimum open interest. |

#### `--top` controls display only

`--top` does **not** control how many qualifying contracts receive Decision Engine analysis. The scanner first collects and Hunter-ranks every qualifying candidate, evaluates every one with Decision Engine, stores the result on that candidate, and only then selects `candidates[:top]` for output.

- `Call candidates` = contracts that passed the existing filters.
- `Engine evaluations` = qualifying contracts evaluated by Decision Engine.
- `--top` = how many ranked/detail reports are printed.

Use this exact verification command:

```bash
poetry run python -m app.backend.services.covered_call_scanner --universe test --limit 3 --top 2
```

Successful output such as:

```text
Call candidates:     10
Engine evaluations:  10
```

with `--top 2` means all 10 qualifying contracts were analyzed, while only the two highest Hunter-ranked contracts were displayed.

The scanner accesses live Yahoo Finance stock and option data. Network, delayed, unavailable, or illiquid option data can result in no candidates. It prints `NO TRADE EXECUTED` and contains no order functionality.

### Covered Call Hunter

Type: **LIBRARY/MODULE**, not normally a direct executable. `covered_call_hunter.py` has no CLI or `__main__` block.

Use it from Python when testing its public API:

```bash
cd ~/ai-stocks
poetry run python - <<'PY'
from app.backend.services.covered_call_hunter import covered_call_hunter

candidate = covered_call_hunter.evaluate(
    ticker="DEMO",
    stock_price=100.0,
    market_cap=10_000_000_000,
    quality_score=75.0,
    growth_score=80.0,
    valuation_score=70.0,
    financial_health_score=85.0,
    strike=110.0,
    expiration="2026-09-25",
    days_to_expiration=26,
    premium=2.50,
    open_interest=2500,
    option_volume=1000,
    bid=2.40,
    ask=2.60,
    implied_volatility=0.40,
    iv_rank=65.0,
    delta=0.25,
    earnings_date=None,
)
print(covered_call_hunter.build_human_summary(candidate))
PY
```

This supplied-data smoke test accesses no live market data and does not execute trades.

### Megatron Decision Engine 💰

Type: **LIBRARY/MODULE**, not normally a direct executable. `decision_engine.py` has no CLI or `__main__` block.

The scanner automatically converts every qualifying `CoveredCallCandidate` into stock/option dictionaries, calls `decision_engine.evaluate(...)`, stores the `DecisionResult` as `candidate.decision_result`, then reuses that cached result while printing the ranked and detailed reports.

Verified supplied-data smoke test:

```bash
cd ~/ai-stocks
poetry run python - <<'PY'
from app.backend.services.decision_engine import build_decision_summary, decision_engine

result = decision_engine.evaluate(
    ticker="DEMO",
    stock={
        "price": 100.0,
        "market_cap": 10_000_000_000,
        "quality_score": 75.0,
        "growth_score": 80.0,
        "valuation_score": 70.0,
        "financial_health_score": 85.0,
    },
    option={
        "strike": 110.0,
        "expiration": "2026-09-25",
        "days_to_expiration": 26,
        "premium": 2.50,
        "premium_yield": 2.50,
        "annualized_premium_yield": 35.1,
        "open_interest": 2500,
        "option_volume": 1000,
        "bid": 2.40,
        "ask": 2.60,
        "bid_ask_spread_pct": 8.0,
        "implied_volatility": 0.40,
        "iv_rank": 65.0,
        "delta": 0.25,
        "earnings_date": None,
        "upside_to_strike_pct": 10.0,
    },
)
print(build_decision_summary(result))
PY
```

This smoke test uses only supplied dictionaries. Decision Engine does not fetch data or place trades.

## 6. SCOUT 🤖

Scout is exposed by the FastAPI backend. Start the backend first:

```bash
cd ~/ai-stocks
poetry run uvicorn app.backend.main:app --reload
```

Check Scout:

```bash
curl http://localhost:8000/scout/status
```

Expected status includes `mode: "alert-only"` and `trading_enabled: false`.

Scout webhook endpoint:

```text
POST /scout/webhook
```

Local webhook test:

```bash
curl -X POST http://localhost:8000/scout/webhook \
  -H 'Content-Type: application/json' \
  -d '{
    "ticker": "AMD",
    "action": "alert",
    "price": 465.58,
    "timeframe": "1D",
    "message": "Manual Scout test",
    "source": "manual"
  }'
```

Scout requires internet access to Yahoo Finance and a running Ollama server with its current default model, `llama3.1:latest`. It logs the human-readable report to the backend terminal and returns a machine-readable response. It does not execute trades.

### TradingView webhook

TradingView cannot call `http://localhost:8000` on your computer. It needs a publicly reachable HTTPS forwarding endpoint that routes to this FastAPI backend. This repository does not include a tunnel or deployment mechanism.

After arranging such an endpoint, use this path:

```text
https://<your-public-host>/scout/webhook
```

Use a TradingView alert message that renders to valid JSON:

```json
{
  "ticker": "{{ticker}}",
  "action": "alert",
  "price": {{close}},
  "timeframe": "{{interval}}",
  "message": "TradingView alert",
  "source": "TradingView"
}
```

The final rendered `price` must be numeric and the final alert message must be valid JSON.

### Scout live execution (opt-in webhook orders)

Scout will NOT place orders unless every gate passes:

1. `SCOUT_EXECUTION_ENABLED=true` in `~/ai-stocks/.env`
2. The alert payload carries `"secret": "<SCOUT_EXECUTION_SECRET>"` matching the env value
3. `"execute": true` and `"qty": <positive int>` on the alert
4. The AI classification is `HIGH_INTEREST` or `INVESTIGATE`
5. `alert_validation.status` is not `PRICE_MISMATCH` / `ALERT_DISCREPANCY`
6. The US market is open
7. The estimated notional stays under `ALPACA_MAX_NOTIONAL`
8. The ticker is tradable (and shortable for `short`)

When all gates pass, a single day-limit order is submitted to Alpaca
(`buy`→buy, `sell`→sell, `short`→sell, `cover`→buy). Any failure is
returned in the webhook JSON under `execution` with `status: REFUSED`.

Hand-rolled webhook example that requests execution:

```bash
curl -X POST http://localhost:8000/scout/webhook \
  -H 'Content-Type: application/json' \
  -d '{
    "ticker": "AMD",
    "action": "buy",
    "price": 465.58,
    "qty": 1,
    "execute": true,
    "secret": "YOUR_SCOUT_SECRET",
    "timeframe": "1D",
    "message": "TradingView alert",
    "source": "TradingView"
  }'
```

## 7. SCOUT ANALYSTS

Type: **LIBRARY/MODULE**, not a standalone CLI. `app/backend/services/scout_analysts.py` has no `__main__` entry point.

It runs these six analyst agents:

- technical
- fundamentals
- growth
- valuation
- sentiment
- news sentiment

Verified library smoke-test command:

```bash
cd ~/ai-stocks
poetry run python - <<'PY'
from app.backend.services.scout_analysts import run_scout_analysts

result = run_scout_analysts(
    ticker="AMD",
    market_data={"price": 465.58},
    alert={"action": "alert", "timeframe": "1D", "message": "manual test"},
    model_name="gpt-4.1",
    model_provider="OpenAI",
)
print(result)
PY
```

This can invoke analyst/data/LLM services and therefore needs the relevant credentials. It is research-only and does not submit orders.

## 8. OLLAMA

Check the local server:

```bash
curl http://localhost:11434/api/version
```

List downloaded models:

```bash
ollama list
```

Start a local foreground server:

```bash
ollama serve
```

Stop a foreground server with `Ctrl+C` in its terminal.

Pull Scout's default model:

```bash
ollama pull llama3.1:latest
```

Check a model through the project helper:

```bash
cd ~/ai-stocks
poetry run python src/utils/ollama.py --check-model llama3.1:latest
```

Check, start, or stop Ollama through the running backend:

```bash
curl http://localhost:8000/ollama/status
curl -X POST http://localhost:8000/ollama/start
curl -X POST http://localhost:8000/ollama/stop
```

## 9. WEB APP 🌐

### FastAPI

```bash
cd ~/ai-stocks
poetry run uvicorn app.backend.main:app --reload
```

Runs on port `8000`. Use Terminal 1. Stop with `Ctrl+C`.

### Vite frontend

```bash
cd ~/ai-stocks/app/frontend
npm run dev
```

Runs on port `5173` by default. Use Terminal 2. Stop with `Ctrl+C`.

### Combined launcher

Run from `app/`, not the repository root:

```bash
cd ~/ai-stocks/app
bash run.sh
```

It checks dependencies, starts both services, attempts to open the browser, and removes its temporary logs when stopped. Press `Ctrl+C` in that launcher terminal to stop both child services.

## 10. DOCKER

Run Docker commands from `~/ai-stocks/docker`:

```bash
cd ~/ai-stocks/docker
```

Build the image:

```bash
./run.sh build
```

Run the main workflow:

```bash
./run.sh --ticker AMD main
```

Run the backtester:

```bash
./run.sh --ticker AMD backtest
```

Run main with Docker-managed Ollama:

```bash
./run.sh --ticker AMD --ollama main
```

Start only Docker Ollama and list its models:

```bash
./run.sh ollama
```

Pull a Docker Ollama model:

```bash
./run.sh pull llama3.1:latest
```

Run Compose with embedded Ollama:

```bash
./run.sh compose
```

Stop foreground Docker work with `Ctrl+C`. Stop the embedded Ollama container with:

```bash
docker compose --profile embedded-ollama stop ollama
```

Docker runs are still research/simulation workflows; they do not add broker execution.

## 11. TESTING / VALIDATION 🧪

Compile the Decision Engine, Scout Analysts, and scanner. Run each command separately; this avoids a wrapped terminal line turning `app/backend/services/` into an invalid directory argument:

```bash
cd ~/ai-stocks
poetry run python -m py_compile app/backend/services/decision_engine.py
```

```bash
poetry run python -m py_compile app/backend/services/scout_analysts.py
```

```bash
poetry run python -m py_compile app/backend/services/covered_call_scanner.py
```

Compile principal service modules:

```bash
poetry run python -m py_compile src/main.py src/backtester.py app/backend/main.py app/backend/services/scout_service.py
```

Run all tests:

```bash
poetry run pytest
```

Run the v2 tests:

```bash
poetry run pytest v2
```

Some v2 live tests skip unless `FINANCIAL_DATASETS_API_KEY` is configured.

Frontend validation:

```bash
cd ~/ai-stocks/app/frontend
npm run lint
npm run build
```

Success looks like: `py_compile` is silent, pytest reports passed/skipped tests with exit status zero, lint has no reported violations, and Vite builds successfully.

## 12. LIVE EXECUTION 💸

Live trading is **off by default** everywhere. Keys live in
`~/ai-stocks/.env` (gitignored — never commit it). Copy the template
with `cp .env.example .env` and fill in the real values.

### Common pre-flight

| Variable | Used by | Notes |
| --- | --- | --- |
| `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` | megastocks, megacalls, Scout | Alpaca **Trading** keys |
| `ALPACA_MODE` | broker | `live` or `paper` (default `live`) |
| `ALPACA_MAX_NOTIONAL` | broker | per-order dollar cap |
| `SCOUT_EXECUTION_ENABLED` | Scout webhook | must be `true` to execute |
| `SCOUT_EXECUTION_SECRET` | Scout webhook | must match alert `secret` field |
| `MEGATRON_LIVE_EXECUTION` | megacrypto | must be `true` to sign/broadcast |
| `SOLANA_PRIVATE_KEY` | megacrypto | base58 keypair |
| `SOLANA_WALLET_ADDRESS` | megacrypto | signer public key |
| `SOLANA_RPC_URL` | megacrypto | RPC endpoint |
| `MEGATRON_MAX_TRADE_USDC` | megacrypto | hard cap per swap (default 25) |
| `JUPITER_API_KEY` | megacrypto | loaded from `crypto_arb/.env` |

### Every order path follows the same safety model

1. **Gates** must pass (keys set, market rules, caps).
2. **Confirmation** — the terminal prompts you explicitly per order
   (megastocks / megacalls / megacrypto) or the alert must carry the
   shared secret (Scout). Nothing signs or broadcasts on its own.
3. Refusals return a clear `REFUSED` reason instead of failing silently.

### megastocks → Alpaca

```bash
megastocks --ticker AMD --alpaca --alpaca-mode paper
```

Menu option `[8] ⚡ AI Hedge Fund + Alpaca Execution`. Every buy/sell/
short/cover is confirmed before placement. Shorts are only opened when
Alpaca reports the ticker shortable.

### megacalls → Alpaca

```bash
cd ~/ai-stocks
poetry run python -m app.backend.services.covered_call_scanner AMD --alpaca --contracts 1 --max-cap 500
```

Menu option `[5] ⚡ Scan + Alpaca Execution`. Places a buy of
`contracts × 100` shares plus a sell-to-open of the OCC option symbol.

### Scout webhook → Alpaca

Set `SCOUT_EXECUTION_ENABLED=true` and a `SCOUT_EXECUTION_SECRET`, then
include `execute`, `qty`, and `secret` in the TradingView alert JSON.
See "Scout live execution" under section 6.

### megacrypto → Solana (gated swap)

```bash
megacrypto
```

Menu option `[7] ⚡ Solana LIVE Swap (gated)`. Launches
`crypto_arb/solana_live_executor.py` which:

1. checks `MEGATRON_LIVE_EXECUTION`, `SOLANA_PRIVATE_KEY`,
   `SOLANA_WALLET_ADDRESS`, `JUPITER_API_KEY`;
2. fetches a fresh Jupiter quote;
3. **always simulates** the swap on the RPC before anything else;
4. asks for an explicit typed `YES` before signing;
5. signs with the private key and broadcasts one transaction.

Refusal modes tested: live disabled, missing key, missing wallet,
simulation failure, declined confirmation.

Direct CLI (research): `python3 crypto_arb/solana_live_executor.py --gates`

### Master kill switch — `live on` / `live off`

A single on/off switch guards **all** live paths. Default OFF.

```bash
live          # show status
live on       # enable live trading (writes ~/ai-stocks/.live_trading = ON)
live off      # disable live trading (writes OFF)
```

- Every live executor checks this as its FIRST gate: megastocks
  `--alpaca`, megacalls `--alpaca`, Scout webhook execution, and the
  megacrypto Solana swap all refuse with `LIVE-KILL-SWITCH` until the
  switch reads `ON`.
- The switch is a plain file (`~/ai-stocks/.live_trading`) so long-lived
  processes (e.g. the Scout webhook) pick up changes immediately with
  no restart. It is gitignored and never committed.
- Existing per-path gates (`ALPACA_MODE`, `SCOUT_EXECUTION_ENABLED`,
  `MEGATRON_LIVE_EXECUTION`, cap limits) still apply on top of it.
- Safety flow: `live off` → run research freely → `live on` only for the
  minutes you intend to place orders → `live off` again.

## 13. PORT / PROCESS TROUBLESHOOTING 🔧

Inspect port owners:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

Fallback when `lsof` is unavailable:

```bash
ss -ltnp | rg ':(8000|5173)\b'
```

If a known, verified process owns a port, stop only that PID:

```bash
kill <PID>
```

`Address already in use` means another process owns the requested port. Inspect first, then stop the confirmed old service or choose another port for an isolated backend test:

```bash
poetry run uvicorn app.backend.main:app --reload --port 8001
```

Keep the normal backend on `8000` whenever using the current frontend. Several frontend modules explicitly use `http://localhost:8000`; changing only the backend port can break the UI.

## 14. LOGS / DATABASE / OUTPUTS

- Covered Call Scanner, Covered Call Hunter, and Decision Engine reports are terminal output only; they do not persist scan reports automatically.
- Scout logs its human-readable report to the FastAPI backend terminal and returns it in the webhook response.
- FastAPI's SQLite database is `~/ai-stocks/app/backend/hedge_fund.db`.
- The backend storage route can create JSON files in `~/ai-stocks/outputs/` through `POST /storage/save-json`.
- `app/run.sh` creates temporary backend/frontend log files while it is running, then deletes them during cleanup.
- `src/utils/visualize.py` can write `graph.png` when called, but the current main CLI does not call that helper.

## 15. RUNNABLE VS NOT RUNNABLE

| File/location | Type | Run directly? | How to use |
| --- | --- | --- | --- |
| `src/main.py` | Runnable CLI | Yes | `poetry run python src/main.py --ticker AMD --ollama` |
| `src/backtester.py` | Runnable CLI | Yes | `poetry run python src/backtester.py --ticker AMD` |
| `src/backtesting/cli.py` | Poetry CLI entry point | Via `backtester` | `poetry run backtester --ticker AMD` |
| `app/backend/main.py` | FastAPI application module | Through Uvicorn | `poetry run uvicorn app.backend.main:app --reload` |
| `app/backend/services/covered_call_scanner.py` | Runnable module | Yes, with `-m` | `poetry run python -m app.backend.services.covered_call_scanner ...` |
| `src/utils/ollama.py` | Runnable utility | Yes | `poetry run python src/utils/ollama.py --check-model llama3.1:latest` |
| `v2/backtesting/__main__.py` | Runnable module/demo | Yes, with `-m` | `poetry run python -m v2.backtesting` |
| `v2/event_study/__main__.py` | Runnable module/demo | Yes, with `-m` | `poetry run python -m v2.event_study` |
| `app/run.sh` | Service launcher | Yes, from `app/` | `cd app && bash run.sh` |
| `docker/run.sh` | Docker launcher | Yes, from `docker/` | `cd docker && ./run.sh <command>` |
| `app/backend/services/covered_call_hunter.py` | Library/module | No normal CLI | Import `covered_call_hunter`. |
| `app/backend/services/decision_engine.py` | Library/module | No normal CLI | Import `decision_engine`. |
| `app/backend/services/scout_analysts.py` | Library/module | No normal CLI | Import `run_scout_analysts`. |
| `app/backend/services/scout_service.py` | Backend service | No normal CLI | Use `/scout/webhook` through FastAPI. |
| `src/agents/*` | Agent libraries | No | Imported by workflow code. |
| `src/backtesting/*` | Backtesting libraries | No | Imported by CLI/backtest code. |
| `src/data/*` | Data libraries | No | Imported by workflows. |
| `src/tools/*` | Tool libraries | No | Imported by workflows. |
| `src/graph/*` | Graph libraries | No | Imported by workflows. |
| `src/llm/*` | LLM libraries | No | Imported by workflows. |
| `src/utils/*` | Utilities | Normally no | Only `src/utils/ollama.py` has a CLI block. |
| `app/backend/routes/*` | FastAPI routers | No | Served through `app.backend.main:app`. |
| other backend service modules | Backend libraries/services | No | Imported by FastAPI routes/services. |
| `tests/`, `v2/**/test_*.py` | Test modules | No direct script | Run with `poetry run pytest`. |

No Streamlit application or Streamlit entry point exists in the current repository.

## 16. TROUBLESHOOTING

### Address already in use

Check the port owner before stopping anything:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

Stop only the confirmed PID:

```bash
kill <PID>
```

Then restart the intended service. A running backend should remain in Terminal 1; do not start a second backend on the same port.

### `vite: not found`

Run the frontend dependency installation from the frontend directory:

```bash
cd ~/ai-stocks/app/frontend
npm install
npm run dev
```

### Command accidentally split across multiple lines

Long commands pasted into a narrow terminal can be split so that zsh treats the second line as a new command. For example, splitting after `app/backend/services/` can produce `Is a directory` followed by `zsh: command not found`.

Run long commands on one line, or run separate files as separate commands:

```bash
poetry run python -m py_compile app/backend/services/decision_engine.py
```

```bash
poetry run python -m py_compile app/backend/services/scout_analysts.py
```

### Successful `py_compile` produces no output

That is expected. No output and a returned shell prompt mean the file compiled successfully. An error message means Python found a syntax or path problem.

### Stopping a running server

Use `Ctrl+C` in the terminal that is running Uvicorn or Vite. For the combined `app/run.sh` launcher, use `Ctrl+C` in its terminal so its cleanup handler can stop both child services.

### `poetry: command not found`

Install Poetry, restart the shell if required, then verify:

```bash
poetry --version
```

### Python module is missing

Run from the repository root:

```bash
cd ~/ai-stocks
poetry install
```

Use `poetry run ...` rather than system `python`.

### `npm: command not found`

Install Node.js/npm, then rerun:

```bash
cd ~/ai-stocks/app/frontend
npm install
```

### Yahoo Finance or option data fails

The scanner and Scout require internet access. Retry after checking connectivity; some tickers/options may be unavailable or fail the active filters. This does not indicate a trade should be made.

### No scanner candidates

The scanner will report no qualifying candidates when no contract satisfies the current filters. Confirm the selected universe/tickers, then use only the documented filter arguments if broader research is intended.

### Ollama model/server error

Check the server and models:

```bash
curl http://localhost:11434/api/version
ollama list
ollama pull llama3.1:latest
```

Start it when necessary:

```bash
ollama serve
```

### Backend or frontend cannot start

Check ports `8000` and `5173`, identify the owning PID, then stop only that confirmed process. See section 12.

### Missing financial-data or LLM credentials

Review `.env` and set only the key required for the provider/workflow you selected. Do not print or commit secrets.

## 17. DAILY WORKFLOW

1. Start the backend in Terminal 1 and frontend in Terminal 2 when using the web UI.
2. Check Ollama and its models if using local LLM workflows.
3. Check Scout status; send a local Scout test only when needed.
4. Run the small Covered Call scan first.
5. Review the scanner's liquidity, warnings, Hunter score, and contract data.
6. Review the cached Decision Engine report for every displayed contract; remember all qualifying contracts were evaluated even when `--top` displays fewer.
7. Run the AI Hedge Fund for broader analyst decision support.
8. Run a backtest when a historical simulation is appropriate.
9. Record conclusions, assumptions, source timestamps, and reasons for any personal decision outside this project.
10. Stop Uvicorn, Vite, Ollama, or Docker services you no longer need with their documented safe stop method.

The workflow is decision support, not a profit guarantee. Do independent research and use disciplined risk management.

## 18. QUICK COMMAND CARD

```bash
# Enter the repository
cd ~/ai-stocks
```

```bash
# Install Python dependencies
poetry install
```

```bash
# Start FastAPI / Scout backend
poetry run uvicorn app.backend.main:app --reload
```

```bash
# Start frontend (new terminal)
cd ~/ai-stocks/app/frontend
npm install
npm run dev
```

```bash
# Small Covered Call Scanner verification
cd ~/ai-stocks
poetry run python -m app.backend.services.covered_call_scanner --universe test --limit 3 --top 2
```

```bash
# Mid-cap scan
poetry run python -m app.backend.services.covered_call_scanner --universe midcap --limit 50 --top 10
```

```bash
# Specific ticker scan
poetry run python -m app.backend.services.covered_call_scanner AMD MU PLTR --top 10
```

```bash
# AI Hedge Fund with Ollama
poetry run python src/main.py --ticker AMD --ollama
```

```bash
# Legacy backtest
poetry run python src/backtester.py --ticker AMD
```

```bash
# Scout status
curl http://localhost:8000/scout/status
```

```bash
# Ollama status and model list
curl http://localhost:11434/api/version
ollama list
```

```bash
# Compile Decision Engine
poetry run python -m py_compile app/backend/services/decision_engine.py
```

```bash
# Compile Scout Analysts
poetry run python -m py_compile app/backend/services/scout_analysts.py
```

```bash
# Compile Covered Call Scanner
poetry run python -m py_compile app/backend/services/covered_call_scanner.py
```

```bash
# Test suites
poetry run pytest
poetry run pytest v2
```

```bash
# Check service ports
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
```
