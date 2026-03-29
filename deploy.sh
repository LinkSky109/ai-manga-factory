#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "[error] docker not found in PATH" >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "[error] docker compose v2 not available" >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "[info] created .env from .env.example"
fi

if [[ ! -f secrets/runtime_storage_config.json ]]; then
  cp secrets/runtime_storage_config.example.json secrets/runtime_storage_config.json
  echo "[info] created secrets/runtime_storage_config.json from example"
fi

docker compose up -d --build
docker compose ps
