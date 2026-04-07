#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$SCRIPT_DIR/common.sh"

WORKER_DIR="$REPO_ROOT/apps/worker"

stop_pid_file_service() {
  local name=$1
  local pid_file=$2
  local pid

  cleanup_stale_pid_file "$pid_file"
  pid=$(read_pid_file "$pid_file")
  if [[ -n "$pid" ]] && is_pid_running "$pid"; then
    kill "$pid"
    wait_for_pid_exit "$pid" || true
    rm -f "$pid_file"
    print_service_line "$name" "stopped" "pid=$pid"
    return
  fi

  rm -f "$pid_file"
  print_service_line "$name" "stopped" "no tracked process"
}

stop_worker() {
  local pid_file pid
  pid_file=$(worker_pid_file)
  cleanup_stale_pid_file "$pid_file"
  pid=$(read_pid_file "$pid_file")

  if [[ -z "$pid" ]]; then
    pid=$(find_process_pid_by_pattern "src/entrypoints/main.py --poll-interval 2")
  fi

  if [[ -n "$pid" ]] && is_pid_running "$pid"; then
    kill "$pid"
    wait_for_pid_exit "$pid" || true
    rm -f "$pid_file"
    print_service_line "worker" "stopped" "pid=$pid"
    return
  fi

  rm -f "$pid_file"
  print_service_line "worker" "stopped" "no tracked process"
}

printf 'Stopping AI Manga Factory services\n'
stop_pid_file_service "web" "$(web_pid_file)"
stop_pid_file_service "api" "$(api_pid_file)"
stop_worker
