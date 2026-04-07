#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$SCRIPT_DIR/common.sh"

HEALTH_RETRIES=${HEALTH_RETRIES:-30}
HEALTH_INTERVAL=${HEALTH_INTERVAL:-1}
SHOW_LOGS=${SHOW_LOGS:-1}
LINES=${LINES:-5}
FOLLOW=${FOLLOW:-0}
SERVICE=${SERVICE:-}

wait_for_health() {
  local attempt health_output=""

  for ((attempt = 1; attempt <= HEALTH_RETRIES; attempt += 1)); do
    if health_output=$(bash "$SCRIPT_DIR/health_services.sh" 2>&1); then
      printf '%s\n' "$health_output"
      return 0
    fi

    if [[ "$attempt" -lt "$HEALTH_RETRIES" ]]; then
      sleep "$HEALTH_INTERVAL"
    fi
  done

  printf '%s\n' "$health_output"
  return 1
}

print_endpoint_summary() {
  printf '\nEndpoints\n'
  print_service_line "web" "ready" "http://127.0.0.1:$WEB_PORT/"
  print_service_line "api" "ready" "http://127.0.0.1:$API_PORT/health"
}

print_next_steps() {
  printf '\nCommands\n'
  print_service_line "status" "hint" "make status"
  print_service_line "health" "hint" "make health"
  print_service_line "logs" "hint" "make logs SERVICE=api"
  print_service_line "stop" "hint" "make stop"
}

printf 'Starting AI Manga Factory dev environment\n'
bash "$SCRIPT_DIR/start_services.sh"

printf '\nWaiting for healthy services\n'
if ! wait_for_health; then
  printf '\nHealth checks did not pass after %s attempts\n' "$HEALTH_RETRIES" >&2
  bash "$SCRIPT_DIR/status_services.sh" || true
  printf '\nRecent logs\n' >&2
  SERVICE="$SERVICE" LINES="$LINES" FOLLOW=0 bash "$SCRIPT_DIR/logs_services.sh" || true
  exit 1
fi

printf '\n'
bash "$SCRIPT_DIR/status_services.sh"
print_endpoint_summary
print_next_steps

if [[ "$SHOW_LOGS" == "1" || "$FOLLOW" == "1" ]]; then
  printf '\nRecent logs\n'
  SERVICE="$SERVICE" LINES="$LINES" FOLLOW="$FOLLOW" bash "$SCRIPT_DIR/logs_services.sh"
fi
