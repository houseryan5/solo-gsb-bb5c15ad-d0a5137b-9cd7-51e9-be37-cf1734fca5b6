#!/bin/sh
# Dependencies are installed at container start (as required), then the
# API process takes over.
set -e

echo "[entrypoint] Installing Python dependencies from requirements.txt ..."
pip install --no-cache-dir -r /app/requirements.txt

echo "[entrypoint] Starting: $*"
exec "$@"
