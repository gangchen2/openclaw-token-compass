#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_DIR="$(cd "$ROOT_DIR/.." && pwd)"
PLUGIN_DIR="$ROOT_DIR/openclaw-plugin"

if ! command -v openclaw >/dev/null 2>&1; then
  echo "openclaw command not found. Please install OpenClaw CLI first."
  exit 1
fi

if [[ ! -d "$PLUGIN_DIR" ]]; then
  echo "Plugin directory not found: $PLUGIN_DIR"
  exit 1
fi

openclaw plugins install -l "$PLUGIN_DIR"
openclaw plugins enable token-compass
openclaw plugins info token-compass
openclaw plugins doctor

echo
echo "Plugin installed and enabled: token-compass"
echo "Recommended env vars:"
echo "  export TOKEN_COMPASS_BIN=\"$WORKSPACE_DIR/.venv/bin/openclaw-token-compass\""
echo "  export TOKEN_COMPASS_DB=\"$ROOT_DIR/data/token_forecast.db\""
