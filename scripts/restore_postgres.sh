#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: bash scripts/restore_postgres.sh <backup.sql.gz>"
  exit 1
fi

BACKUP_PATH=$1
if [[ ! -f "$BACKUP_PATH" ]]; then
  echo "Backup not found: $BACKUP_PATH"
  exit 1
fi

: "${PGHOST:=127.0.0.1}"
: "${PGPORT:=5432}"
: "${PGDATABASE:=ai_manga_factory}"
: "${PGUSER:=postgres}"
: "${PGPASSWORD:=postgres}"
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
COMPOSE_DIR=${COMPOSE_DIR:-"$REPO_ROOT/infra/compose"}
COMPOSE_ENV_FILE=${COMPOSE_ENV_FILE:-"$COMPOSE_DIR/.env.prod"}

printf 'Restoring PostgreSQL from %s\n' "$BACKUP_PATH"
if command -v psql >/dev/null 2>&1; then
  gunzip -c "$BACKUP_PATH" | PGPASSWORD="$PGPASSWORD" psql \
    --host "$PGHOST" \
    --port "$PGPORT" \
    --username "$PGUSER" \
    --dbname "$PGDATABASE"
elif command -v docker >/dev/null 2>&1 && [[ -f "$COMPOSE_ENV_FILE" ]]; then
  gunzip -c "$BACKUP_PATH" | (
    cd "$COMPOSE_DIR"
    docker compose -f docker-compose.prod.yml --env-file "$COMPOSE_ENV_FILE" exec -T postgres \
      sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
  )
else
  echo "Neither psql nor a usable docker compose production context is available."
  exit 1
fi

printf 'Restore complete.\n'
