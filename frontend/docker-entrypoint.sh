#!/bin/sh
# Frontend dependencies are installed at container start (as required).
set -e

echo "[entrypoint] Installing Node dependencies from package.json ..."
npm install

echo "[entrypoint] Starting: $*"
exec "$@"
