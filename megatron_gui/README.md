# MEGATRON — Unified Desktop Terminal

One native Qt window for the three MEGATRON engines:

| Page | Wraps | What is exposed |
|------|-------|-----------------|
| **MEGASTOCKS** | `megastocks.py` → `src/main.py`, `src/backtester.py` | Ticker universe, 6 research modes, native analyst roster, model picker, structured research stream, per-order prompt |
| **MEGACALLS** | `megacalls.py` → `app.backend.services.covered_call_scanner` | Underlyings, 3 scan styles, contracts, stock-leg cap, Alpaca toggle |
| **MEGACRYPTO** | `megacrypto.py` → `solana_arb_scanner.py`, `solana_live_executor.py` | Scanner, Jupiter quotes, watch-only wallet, paper ledger, risk limits, gated swap |

The GUI **does not reimplement any engine**. It builds the same command
lines the terminal launchers use, renders merged output as structured
finance rows (MEGASTOCKS analyst cards; MEGACALLS and MEGACRYPTO scanner
reports), and forwards typing to stdin so y/N approvals still work.
Crypto quote and wallet calls reuse `megacrypto.py`'s own helpers.

## Run

```bash
./run_gui.sh
```

First run creates `.venv-gui` and installs PySide6-Essentials (~90 MB).
Later runs start instantly.

Direct:

```bash
.venv-gui/bin/python -m megatron_gui
```

## Controls

- **Left control rail** — ticker input and tabs, research mode, analyst
  roster, model selector, AI status, local-only / auto-pick, gate status
  and Run / Stop all live in one compact rail. Drag the divider to resize
  it, or use the `‹` / `›` strip to collapse and restore it.
- **Master gate** — the header toggle writes `.live_trading`. Turning it
  on asks for confirmation. Turning it off is immediate and blocks new
  orders in every engine.
- **Report input / RAW** — when an engine asks `[y/N]` or `Place BUY…?`,
  type the answer in the report input and press Enter. `RAW` toggles the
  untouched engine text. `STOP` terminates the child process.
- **Ctrl+1…4** — switch pages.
- **Session feed** — dashboard lists what each page launched.

## Analyst roster and research stream

Click **EDIT** beside the staff count to open the roster. It mirrors the
CLI checkbox contract without a terminal:

| Key | Action |
|-----|--------|
| Up / Down | Move focus |
| Space | Toggle the focused analyst |
| A | Select all, or clear all when everything is selected |
| Enter | Confirm (refused when nothing is selected) |
| Escape | Close without starting research |
| Mouse | Click a row to focus and toggle it |

Analysts are grouped into investment legends and specialists, with name,
specialisation and philosophy shown. The **model** picker in the left rail
feeds `--model`; both selections are snapshotted when a run starts, so
editing them cannot change a queued multi-ticker batch. Selection is
persisted with QSettings and never touches execution state. Local-only and
automatic model selection are available directly beneath the picker.

Research output is parsed from the engine's own report into cards: analyst
name, state (queued / running / complete / failed / cancelled), signal,
confidence, arrival time, and expandable details. Unparsed output remains
in **ENGINE OUTPUT**, and tracebacks become one error card with the
summary instead of a wall of Python.

### Multi-chart workspace and buy alert

MEGASTOCKS keeps one independent Yahoo chart per selected ticker:

- **1 ticker** — one large chart.
- **2 tickers** — side by side.
- **3–4 tickers** — 2×2 grid.
- **More tickers** — a scrollable two-column chart grid.

Each chart keeps its own ticker, **1M / 3M / 6M / 1Y** timeframe, moving
average, volume and loaded candle data. Changing NVDA to 1M never changes
the AMD chart. Clicking a ticker tab focuses the matching chart and its
research tab.

Every chart carries its own **SIGNAL ALERT** generated from that ticker's
portfolio-manager decision, never from a local guess:

| Fund action | Alert |
|-------------|-------|
| BUY / COVER | Green **BUY ALERT** |
| SELL / SHORT | Red **DO NOT BUY** |
| HOLD | Amber **NO BUY — HOLD** |
| No decision | **NO BUY SIGNAL** |

The research output has one tab per ticker. A multi-ticker batch cannot mix
analyst cards, metrics or decisions between symbols. The chart grid and
each report are independently scrollable.

The workspace stacks research beneath the charts on normal desktop widths
and moves it beside the grid on ultrawide displays. The rail and workspace
divider positions, collapsed state, ticker list and research mode are saved
in QSettings.

Growth and Valuation analysts now have a free-data path too: Growth accepts
the latest Yahoo snapshot (and fills EPS/FCF/operating growth from quarterly
statements when available), while Valuation reconstructs line items from
Yahoo's quarterly financials, balance sheet and cash-flow statements when
no `FINANCIAL_DATASETS_API_KEY` is configured.

The roster is read from `src/utils/analysts.py` and `src/llm/models.py` in
the poetry environment and cached in `.megatron_cache/`; there is no
second analyst list to drift.

## Fidelity to the terminal flows

- Stocks: `--ticker` is passed once per ticker, exactly like `megastocks`,
  followed by `--analysts` and `--model` so the engine never waits on a TTY
  prompt. Research runs never pass `--alpaca`; only the LIVE mode does.
- Calls: conservative = top 10 / vol 100 / OI 500, wider = top 15 / vol
  50 / OI 250, test = `--universe test --limit 3 --top 5`.
- Crypto swaps run through `poetry run python crypto_arb/solana_live_executor.py`
  so `solders` and `phase3_executor` resolve from the project env.

## Design

A near-black phosphor-green desk (`#020705`) with a neon accent per
engine — acid lime for stocks, mint for calls, matrix green for crypto.
JetBrainsMono Nerd Font carries every label, number and paragraph. The
theme lives in `theme.py`; shared widgets are in `components.py`, the
analyst stream in `research.py`, and the scanner report renderer in
`report.py`. Percentage bars are drawn in `research.MiniBar`.

## Install as an app (Omarchy / Hyprland)

```bash
mkdir -p ~/.local/share/applications ~/.local/share/icons/hicolor/scalable/apps
cp megatron.desktop ~/.local/share/applications/
cp assets/megatron.svg ~/.local/share/icons/hicolor/scalable/apps/megatron.svg
```

The runtime window icon also uses `assets/megatron-*.png`. If the project
moves, update `Exec` and `Path` in the desktop file.

## Requirements

- Python 3.11+ with venv (PySide6-Essentials installs into `.venv-gui`)
- Poetry for the stock/call engines
- Keys in `.env` for anything live; research works without them
- The gated Solana swap also needs the signer library in the poetry env:
  `poetry run python -m pip install solders`. Without it the executor
  exits on import and the console shows the traceback.
