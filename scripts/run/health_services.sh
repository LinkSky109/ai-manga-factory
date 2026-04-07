#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$SCRIPT_DIR/common.sh"

api_pid=$(api_runtime_pid || true)
web_pid=$(web_runtime_pid || true)
worker_pid=$(worker_runtime_pid || true)

has_failure=0

print_health_line() {
  local check=$1
  local status=$2
  local details=$3
  printf '%-14s %-6s %s\n' "$check" "$status" "$details"
}

check_process() {
  local name=$1
  local pid=$2
  local details=$3

  if [[ -n "$pid" ]]; then
    print_health_line "$name" "ok" "$details"
  else
    print_health_line "$name" "fail" "$details"
    has_failure=1
  fi
}

check_process "api-process" "$api_pid" "pid=${api_pid:-missing}"
check_process "web-process" "$web_pid" "pid=${web_pid:-missing}"
check_process "worker-process" "$worker_pid" "pid=${worker_pid:-missing}"

if [[ -n "$api_pid" ]]; then
  api_body=$(curl -sS --max-time 5 "http://127.0.0.1:$API_PORT/health" || true)
  if [[ "$api_body" == *'"status":"ok"'* ]]; then
    print_health_line "api-http" "ok" "$api_body"
  else
    print_health_line "api-http" "fail" "${api_body:-request failed}"
    has_failure=1
  fi
else
  print_health_line "api-http" "skip" "api process is not running"
fi

if [[ -n "$web_pid" ]]; then
  web_status=$(curl -I -sS -o /dev/null -w "%{http_code}" --max-time 5 "http://127.0.0.1:$WEB_PORT" || true)
  if [[ "$web_status" == "200" ]]; then
    print_health_line "web-http" "ok" "HTTP $web_status"
  else
    print_health_line "web-http" "fail" "HTTP ${web_status:-request failed}"
    has_failure=1
  fi
else
  print_health_line "web-http" "skip" "web process is not running"
fi

if [[ "$has_failure" == "1" ]]; then
  exit 1
fi
