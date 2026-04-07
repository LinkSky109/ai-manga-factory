#!/usr/bin/env bash

set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not available."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "docker daemon is not reachable. Start Docker Desktop or Colima before continuing."
  exit 1
fi

echo "Docker runtime is reachable."
