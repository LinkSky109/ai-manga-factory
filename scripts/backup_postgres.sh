#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
BACKUP_DIR=${BACKUP_DIR:-"$REPO_ROOT/backups/postgres"}
COMPOSE_DIR=${COMPOSE_DIR:-"$REPO_ROOT/infra/compose"}
COMPOSE_ENV_FILE=${COMPOSE_ENV_FILE:-"$COMPOSE_DIR/.env.prod"}
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
BACKUP_PATH="$BACKUP_DIR/ai-manga-factory-$TIMESTAMP.sql.gz"

: "${PGHOST:=127.0.0.1}"
: "${PGPORT:=5432}"
: "${PGDATABASE:=ai_manga_factory}"
: "${PGUSER:=postgres}"
: "${PGPASSWORD:=postgres}"

mkdir -p "$BACKUP_DIR"

printf 'Backing up PostgreSQL to %s\n' "$BACKUP_PATH"
if command -v pg_dump >/dev/null 2>&1; then
  PGPASSWORD="$PGPASSWORD" pg_dump \
    --host "$PGHOST" \
    --port "$PGPORT" \
    --username "$PGUSER" \
    --dbname "$PGDATABASE" \
    --no-owner \
    --no-privileges | gzip > "$BACKUP_PATH"
elif command -v docker >/dev/null 2>&1 && [[ -f "$COMPOSE_ENV_FILE" ]]; then
  (
    cd "$COMPOSE_DIR"
    docker compose -f docker-compose.prod.yml --env-file "$COMPOSE_ENV_FILE" exec -T postgres \
      sh -lc 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges'
  ) | gzip > "$BACKUP_PATH"
else
  echo "Neither pg_dump nor a usable docker compose production context is available."
  exit 1
fi

printf 'Backup complete: %s\n' "$BACKUP_PATH"
