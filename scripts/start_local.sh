#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="python3"
if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
elif ! command -v python3 >/dev/null 2>&1; then
  echo "Need python3 or a project .venv." >&2
  exit 1
fi

if [ ! -f "$ROOT/.streamlit/secrets.toml" ]; then
  cp "$ROOT/.streamlit/secrets.toml.example" "$ROOT/.streamlit/secrets.toml"
  echo "Created .streamlit/secrets.toml from the example (local_demo_mode is on)."
fi

if ! "$PYTHON" -c "import streamlit" >/dev/null 2>&1; then
  echo "Installing Python dependencies…"
  if [ ! -x "$ROOT/.venv/bin/python" ]; then
    python3 -m venv "$ROOT/.venv"
    PYTHON="$ROOT/.venv/bin/python"
  fi
  "$PYTHON" -m pip install -q -r "$ROOT/requirements.txt"
fi

"$PYTHON" "$ROOT/scripts/seed_local_whitelist.py"
echo "Starting Streamlit. OTP will show on screen in local demo mode."
exec "$PYTHON" -m streamlit run "$ROOT/app.py"
