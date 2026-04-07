#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$SCRIPT_DIR/common.sh"

print_api_status() {
  local pid
  pid=$(api_runtime_pid)
  if [[ -n "$pid" ]]; then
    print_service_line "api" "running" "pid=$pid url=http://127.0.0.1:$API_PORT log=$(api_log_file)"
  else
    print_service_line "api" "stopped" "expected url=http://127.0.0.1:$API_PORT"
  fi
}

print_web_status() {
  local pid
  pid=$(web_runtime_pid)
  if [[ -n "$pid" ]]; then
    print_service_line "web" "running" "pid=$pid url=http://127.0.0.1:$WEB_PORT log=$(web_log_file)"
  else
    print_service_line "web" "stopped" "expected url=http://127.0.0.1:$WEB_PORT"
  fi
}

print_worker_status() {
  local pid
  pid=$(worker_runtime_pid)
  if [[ -n "$pid" ]]; then
    echo "$pid" > "$(worker_pid_file)"
    print_service_line "worker" "running" "pid=$pid log=$(worker_log_file)"
  else
    print_service_line "worker" "stopped" "expected command=src/entrypoints/main.py --poll-interval 2"
  fi
}

printf 'AI Manga Factory service status\n'
print_api_status
print_web_status
print_worker_status
