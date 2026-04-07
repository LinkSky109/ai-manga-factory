#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
COMPOSE_DIR="$REPO_ROOT/infra/compose"
ENV_FILE=${ENV_FILE:-"$COMPOSE_DIR/.env.prod"}

printf '[1/4] Validate production env\n'
bash "$SCRIPT_DIR/validate_prod_env.sh" "$ENV_FILE"

printf '\n[2/4] Validate Docker Compose\n'
if command -v docker >/dev/null 2>&1; then
  (
    cd "$COMPOSE_DIR"
    docker compose -f docker-compose.prod.yml --env-file "$ENV_FILE" config >/dev/null
  )
  echo 'Docker Compose config is valid.'
else
  echo 'Skipping Docker Compose validation: docker command not available.'
fi

printf '\n[3/4] Validate Docker runtime\n'
bash "$SCRIPT_DIR/require_docker_runtime.sh"

printf '\n[4/4] Validate Caddy config\n'
if command -v caddy >/dev/null 2>&1; then
  caddy validate --config "$REPO_ROOT/infra/caddy/Caddyfile"
else
  echo 'Skipping Caddy validation: caddy command not available.'
fi

echo
echo 'Production stack verification completed.'
