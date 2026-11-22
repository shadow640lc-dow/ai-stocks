#!/usr/bin/env bash
# AI Hedge Fund Docker runner (Linux / macOS).
# Mirrors docker/run.bat: build, run, backtest, compose and Ollama helpers.
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

TICKER="AAPL,MSFT,NVDA"
USE_OLLAMA=0
OLLAMA_BASE_URL_VALUE=""
START_DATE=""
END_DATE=""
INITIAL_CASH="100000.0"
MARGIN_REQUIREMENT="0.0"
SHOW_REASONING=0
COMMAND=""
MODEL_NAME=""

usage() {
  cat <<'EOF'
AI Hedge Fund Docker Runner

Usage: run.sh [OPTIONS] COMMAND

Options:
  --ticker SYMBOLS        Comma-separated tickers (default: AAPL,MSFT,NVDA)
  --start-date DATE       Start date (YYYY-MM-DD)
  --end-date DATE         End date (YYYY-MM-DD)
  --initial-cash AMT      Initial cash (default: 100000.0)
  --margin-requirement R  Margin requirement ratio (default: 0.0)
  --ollama                Use local Ollama inference
  --ollama-base-url URL   Use an existing Ollama endpoint (implies --ollama)
  --show-reasoning        Print each agent's reasoning

Commands:
  main                    Run the hedge fund
  backtest                Run the backtester
  build                   Build the Docker image
  compose                 Run with Docker Compose (includes Ollama)
  ollama                  Start the Ollama container
  pull MODEL              Pull a model into the Ollama container
  help                    Show this help message

Examples:
  ./run.sh --ticker AAPL,MSFT,NVDA main
  ./run.sh --ticker AAPL,MSFT,NVDA --ollama main
  ./run.sh --ticker AAPL,MSFT,NVDA backtest
  ./run.sh compose
  ./run.sh pull llama3
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --ticker) TICKER="${2:?--ticker needs a value}"; shift 2 ;;
    --start-date) START_DATE="$2"; shift 2 ;;
    --end-date) END_DATE="$2"; shift 2 ;;
    --initial-cash) INITIAL_CASH="$2"; shift 2 ;;
    --margin-requirement) MARGIN_REQUIREMENT="$2"; shift 2 ;;
    --ollama) USE_OLLAMA=1; shift ;;
    --ollama-base-url) OLLAMA_BASE_URL_VALUE="${2:?--ollama-base-url needs a value}"; USE_OLLAMA=1; shift 2 ;;
    --show-reasoning) SHOW_REASONING=1; shift ;;
    main|backtest|build|compose|ollama) COMMAND="$1"; shift ;;
    pull) COMMAND="pull"; MODEL_NAME="${2:?pull needs a model name}"; shift 2 ;;
    help|--help|-h) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

if [ -z "$COMMAND" ]; then
  echo "Error: no command specified." >&2
  usage
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "Error: Docker Compose is not installed." >&2
  exit 1
fi

if [ -n "$OLLAMA_BASE_URL_VALUE" ]; then
  export OLLAMA_BASE_URL="$OLLAMA_BASE_URL_VALUE"
fi

if [ ! -f ../.env ] && [ -f ../.env.example ]; then
  echo "No .env file found. Creating one from .env.example..."
  cp ../.env.example ../.env
  echo "Please edit .env to add your API keys."
fi

build_image() {
  docker build -t ai-hedge-fund -f Dockerfile ..
}

ensure_image() {
  if ! docker image inspect ai-hedge-fund >/dev/null 2>&1; then
    echo "Building AI Hedge Fund image..."
    build_image
  fi
}

start_ollama() {
  "${COMPOSE[@]}" --profile embedded-ollama up -d ollama
  echo "Waiting for Ollama to start..."
  for _ in $(seq 1 30); do
    if "${COMPOSE[@]}" exec -T ollama curl -sf http://localhost:11434/api/version >/dev/null 2>&1; then
      echo "Ollama is running."
      return 0
    fi
    sleep 1
  done
  echo "Warning: could not confirm Ollama startup within 30 seconds." >&2
}

case "$COMMAND" in
  help)
    usage
    ;;
  build)
    build_image
    ;;
  compose)
    export OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://ollama:11434}"
    "${COMPOSE[@]}" --profile embedded-ollama up --build
    ;;
  ollama)
    start_ollama
    "${COMPOSE[@]}" exec -T ollama ollama list
    echo "Manage models with: ./run.sh pull <model-name>"
    ;;
  pull)
    start_ollama
    "${COMPOSE[@]}" exec -T ollama ollama pull "$MODEL_NAME"
    ;;
  main|backtest)
    ensure_image
    if [ "$COMMAND" = "main" ]; then
      SCRIPT="src/main.py"
    else
      SCRIPT="src/backtester.py"
    fi

    ARGS=(python "$SCRIPT" --ticker "$TICKER")
    [ -n "$START_DATE" ] && ARGS+=(--start-date "$START_DATE")
    [ -n "$END_DATE" ] && ARGS+=(--end-date "$END_DATE")
    ARGS+=(--initial-cash "$INITIAL_CASH" --margin-requirement "$MARGIN_REQUIREMENT")
    [ "$SHOW_REASONING" = 1 ] && ARGS+=(--show-reasoning)

    if [ "$USE_OLLAMA" = 1 ]; then
      if [ -z "$OLLAMA_BASE_URL_VALUE" ]; then
        start_ollama
      fi
      ARGS+=(--ollama)
      SERVICE="hedge-fund-ollama"
      [ "$SHOW_REASONING" = 1 ] && SERVICE="hedge-fund-reasoning"
      if [ -n "$OLLAMA_BASE_URL_VALUE" ]; then
        "${COMPOSE[@]}" run --rm "$SERVICE" "${ARGS[@]}"
      else
        "${COMPOSE[@]}" run --rm "$SERVICE" "${ARGS[@]}"
      fi
    else
      "${COMPOSE[@]}" run --rm hedge-fund "${ARGS[@]}"
    fi
    ;;
esac
