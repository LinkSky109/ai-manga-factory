#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$SCRIPT_DIR/common.sh"

API_DIR="$REPO_ROOT/apps/api"
WEB_DIR="$REPO_ROOT/apps/web"
WORKER_DIR="$REPO_ROOT/apps/worker"

start_api() {
  local pid_file pid existing_port_pid
  pid_file=$(api_pid_file)
  cleanup_stale_pid_file "$pid_file"
  pid=$(read_pid_file "$pid_file")
  if [[ -n "$pid" ]] && is_pid_running "$pid"; then
    print_service_line "api" "running" "pid=$pid url=http://127.0.0.1:$API_PORT"
    return
  fi

  existing_port_pid=$(port_pid "$API_PORT")
  if [[ -n "$existing_port_pid" ]]; then
    print_service_line "api" "blocked" "port $API_PORT already in use by pid=$existing_port_pid"
    return
  fi

  ensure_python_venv "$API_DIR"
  pid=$(spawn_detached "$API_DIR" "$(api_log_file)" \
    "$API_DIR/.venv/bin/python" -m uvicorn src.main:app --host 127.0.0.1 --port "$API_PORT")
  echo "$pid" > "$pid_file"
  print_service_line "api" "started" "pid=$pid url=http://127.0.0.1:$API_PORT log=$(api_log_file)"
}

start_web() {
  local pid_file pid existing_port_pid
  pid_file=$(web_pid_file)
  cleanup_stale_pid_file "$pid_file"
  pid=$(read_pid_file "$pid_file")
  if [[ -n "$pid" ]] && is_pid_running "$pid"; then
    print_service_line "web" "running" "pid=$pid url=http://127.0.0.1:$WEB_PORT"
    return
  fi

  existing_port_pid=$(port_pid "$WEB_PORT")
  if [[ -n "$existing_port_pid" ]]; then
    print_service_line "web" "blocked" "port $WEB_PORT already in use by pid=$existing_port_pid"
    return
  fi

  ensure_web_dependencies "$WEB_DIR"
  pid=$(spawn_detached "$WEB_DIR" "$(web_log_file)" npm run dev)
  echo "$pid" > "$pid_file"
  print_service_line "web" "started" "pid=$pid url=http://127.0.0.1:$WEB_PORT log=$(web_log_file)"
}

find_worker_pid() {
  find_process_pid_by_pattern "src/entrypoints/main.py --poll-interval 2"
}

start_worker() {
  local pid_file pid
  pid_file=$(worker_pid_file)
  cleanup_stale_pid_file "$pid_file"
  pid=$(read_pid_file "$pid_file")
  if [[ -n "$pid" ]] && is_pid_running "$pid"; then
    print_service_line "worker" "running" "pid=$pid log=$(worker_log_file)"
    return
  fi

  pid=$(find_worker_pid)
  if [[ -n "$pid" ]]; then
    echo "$pid" > "$pid_file"
    print_service_line "worker" "running" "pid=$pid log=$(worker_log_file)"
    return
  fi

  ensure_python_venv "$WORKER_DIR"
  pid=$(spawn_detached "$WORKER_DIR" "$(worker_log_file)" \
    "$WORKER_DIR/.venv/bin/python" src/entrypoints/main.py --poll-interval 2)
  echo "$pid" > "$pid_file"
  print_service_line "worker" "started" "pid=$pid log=$(worker_log_file)"
}

printf 'Starting AI Manga Factory services\n'
start_api
start_web
start_worker
