#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
COMPOSE_DIR="$REPO_ROOT/infra/compose"
ENV_FILE=${ENV_FILE:-"$COMPOSE_DIR/.env.prod"}
BACKUP_PATH=${BACKUP_PATH:-}
OBSERVABILITY_FLAG=${OBSERVABILITY_FLAG:-0}

bash "$SCRIPT_DIR/validate_prod_env.sh" "$ENV_FILE"
bash "$SCRIPT_DIR/require_docker_runtime.sh"

if [[ -n "$BACKUP_PATH" ]]; then
  echo "Rollback requested with database restore: $BACKUP_PATH"
  echo "This will overwrite the current database contents."
  bash "$SCRIPT_DIR/restore_postgres.sh" "$BACKUP_PATH"
fi

cd "$COMPOSE_DIR"

if [[ "$OBSERVABILITY_FLAG" == "1" ]]; then
  docker compose -f docker-compose.prod.yml --env-file "$ENV_FILE" --profile observability up -d
else
  docker compose -f docker-compose.prod.yml --env-file "$ENV_FILE" up -d
fi

echo "Rollback compose command completed."
