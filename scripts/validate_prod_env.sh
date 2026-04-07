#!/usr/bin/env bash

set -euo pipefail

ENV_FILE=${1:-/Users/link/work/ai-manga-factory/infra/compose/.env.prod}

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Production env file not found: $ENV_FILE"
  exit 1
fi

read_env_value() {
  local key=$1
  local line
  line=$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 || true)
  printf '%s' "${line#*=}"
}

require_nonempty() {
  local key=$1
  local value
  value=$(read_env_value "$key")
  if [[ -z "$value" ]]; then
    echo "Missing required value: $key"
    exit 1
  fi
}

require_not_placeholder() {
  local key=$1
  local value
  value=$(read_env_value "$key")
  if [[ "$value" == "change-me" || "$value" == "postgres" || "$value" == "admin" ]]; then
    echo "Replace placeholder value for: $key"
    exit 1
  fi
}

truthy() {
  local raw=$1
  local normalized
  normalized=$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')
  [[ "$normalized" == "1" || "$normalized" == "true" || "$normalized" == "yes" || "$normalized" == "on" ]]
}

require_nonempty "DATABASE_URL"
require_nonempty "REDIS_URL"
require_nonempty "PUBLIC_HTTP_PORT"

require_nonempty "POSTGRES_PASSWORD"
require_not_placeholder "POSTGRES_PASSWORD"

auth_enabled_value=$(read_env_value "AUTH_ENABLED")
if truthy "${auth_enabled_value:-false}"; then
  require_nonempty "AUTH_BOOTSTRAP_ADMIN_TOKEN"
  require_not_placeholder "AUTH_BOOTSTRAP_ADMIN_TOKEN"
fi

grafana_enabled_value=$(read_env_value "GRAFANA_ENABLED")
if truthy "${grafana_enabled_value:-false}"; then
  require_nonempty "GRAFANA_ADMIN_PASSWORD"
  require_not_placeholder "GRAFANA_ADMIN_PASSWORD"
fi

object_storage_mode=$(read_env_value "OBJECT_STORAGE_MODE")
if [[ "$object_storage_mode" == "s3" ]]; then
  require_nonempty "S3_BUCKET"
  require_nonempty "S3_ACCESS_KEY_ID"
  require_nonempty "S3_SECRET_ACCESS_KEY"
fi

echo "Production env validation passed: $ENV_FILE"
