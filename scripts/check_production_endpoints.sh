#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
ENV_FILE=${ENV_FILE:-"$REPO_ROOT/infra/compose/.env.prod"}

read_env_value() {
  local key=$1
  local line
  if [[ ! -f "$ENV_FILE" ]]; then
    return 0
  fi
  line=$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 || true)
  printf '%s' "${line#*=}"
}

truthy() {
  local raw=$1
  local normalized
  normalized=$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')
  [[ "$normalized" == "1" || "$normalized" == "true" || "$normalized" == "yes" || "$normalized" == "on" ]]
}

PUBLIC_HTTP_PORT=${PUBLIC_HTTP_PORT:-$(read_env_value "PUBLIC_HTTP_PORT")}
BASE_URL=${BASE_URL:-"http://127.0.0.1:${PUBLIC_HTTP_PORT:-8080}"}
AUTH_ENABLED=${AUTH_ENABLED:-$(read_env_value "AUTH_ENABLED")}
PROD_API_TOKEN=${PROD_API_TOKEN:-$(read_env_value "AUTH_BOOTSTRAP_ADMIN_TOKEN")}

request_body() {
  local path=$1
  shift
  curl --fail --silent --show-error "$@" "$BASE_URL$path"
}

assert_contains() {
  local body=$1
  local needle=$2
  local label=$3
  local normalized_body
  local normalized_needle
  normalized_body=$(printf '%s' "$body" | tr -d '[:space:]')
  normalized_needle=$(printf '%s' "$needle" | tr -d '[:space:]')
  if [[ "$normalized_body" != *"$normalized_needle"* ]]; then
    echo "Unexpected response for $label. Missing token: $needle"
    echo "Body: $body"
    exit 1
  fi
}

check_endpoint() {
  local name=$1
  local path=$2
  local body
  printf 'Checking %-20s %s%s\n' "$name" "$BASE_URL" "$path"
  body=$(request_body "$path")
  if [[ $# -ge 3 ]]; then
    assert_contains "$body" "$3" "$name"
  fi
}

check_authorized_endpoint() {
  local name=$1
  local path=$2
  local expected=$3
  if ! truthy "${AUTH_ENABLED:-false}"; then
    check_endpoint "$name" "$path" "$expected"
    return 0
  fi

  if [[ -z "${PROD_API_TOKEN:-}" || "${PROD_API_TOKEN:-}" == "change-me" ]]; then
    echo "AUTH_ENABLED=true but PROD_API_TOKEN is missing. Export PROD_API_TOKEN or provide a populated .env.prod."
    exit 1
  fi

  local body
  printf 'Checking %-20s %s%s\n' "$name" "$BASE_URL" "$path"
  body=$(request_body "$path" -H "Authorization: Bearer $PROD_API_TOKEN")
  assert_contains "$body" "$expected" "$name"
}

check_endpoint "health" "/health" "\"status\":\"ok\""
check_endpoint "metrics" "/metrics" "ai_manga_factory_"
check_endpoint "web" "/" "<!doctype html"
check_authorized_endpoint "auth me" "/api/v1/auth/me" "\"auth_enabled\":"
check_authorized_endpoint "monitoring overview" "/api/v1/monitoring/overview" "\"summary\":"
check_authorized_endpoint "storage targets" "/api/v1/storage/targets" "\"items\":"
check_authorized_endpoint "settings overview" "/api/v1/settings/overview" "\"runtime\":"

printf 'Production endpoint smoke passed for %s\n' "$BASE_URL"
