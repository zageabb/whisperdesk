#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -n "${WHISPERDESK_PYTHON:-}" ]]; then
  PYTHON="$WHISPERDESK_PYTHON"
elif [[ -x "$HOME/whisper-env/bin/python" ]]; then
  PYTHON="$HOME/whisper-env/bin/python"
elif [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
else
  echo "No Python environment found. Create ~/whisper-env or .venv first." >&2
  exit 1
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-5070}"

echo "Starting WhisperDesk on ${HOST}:${PORT} using ${PYTHON}"
exec "$PYTHON" -m gunicorn \
  --workers 1 \
  --threads 4 \
  --timeout 120 \
  --bind "${HOST}:${PORT}" \
  run:app
