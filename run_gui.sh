#!/usr/bin/env bash
# MEGATRON desktop launcher — creates its own Qt venv on first run.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

# Ensure a display is available (X11/Wayland) — the desktop entry may not
# set DISPLAY, so we default to :0 for the local Xwayland server.
if [ -z "$DISPLAY" ]; then
    DISPLAY=:0
    export DISPLAY
fi

VENV=".venv-gui"

if [ ! -x "$VENV/bin/python" ]; then
  BASE=""
  for candidate in python3.12 python3.13 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then BASE="$candidate"; break; fi
  done
  if [ -z "$BASE" ]; then
    echo "MEGATRON: no python3 found." >&2
    exit 1
  fi
  echo "MEGATRON: creating $VENV with $BASE"
  "$BASE" -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet PySide6-Essentials
fi

echo "MEGATRON: launching with DISPLAY=$DISPLAY"
exec "$VENV/bin/python" -m megatron_gui "$@"
