#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
LOG_DIR="$REPO_ROOT/logs/services"
PID_DIR="$LOG_DIR/pids"

API_PORT=8000
WEB_PORT=5173

mkdir -p "$LOG_DIR" "$PID_DIR"

api_pid_file() {
  printf '%s\n' "$PID_DIR/api.pid"
}

web_pid_file() {
  printf '%s\n' "$PID_DIR/web.pid"
}

worker_pid_file() {
  printf '%s\n' "$PID_DIR/worker.pid"
}

api_log_file() {
  printf '%s\n' "$LOG_DIR/api.log"
}

web_log_file() {
  printf '%s\n' "$LOG_DIR/web.log"
}

worker_log_file() {
  printf '%s\n' "$LOG_DIR/worker.log"
}

service_log_file() {
  local service=$1
  case "$service" in
    api)
      api_log_file
      ;;
    web)
      web_log_file
      ;;
    worker)
      worker_log_file
      ;;
    *)
      return 1
      ;;
  esac
}

service_pid_or_port() {
  local pid_file=$1
  local port=${2:-}
  local pid

  cleanup_stale_pid_file "$pid_file"
  pid=$(read_pid_file "$pid_file")
  if [[ -n "$pid" ]] && is_pid_running "$pid"; then
    printf '%s\n' "$pid"
    return
  fi

  if [[ -n "$port" ]]; then
    pid=$(port_pid "$port")
    if [[ -n "$pid" ]]; then
      printf '%s\n' "$pid"
      return
    fi
  fi
}

api_runtime_pid() {
  service_pid_or_port "$(api_pid_file)" "$API_PORT"
}

web_runtime_pid() {
  service_pid_or_port "$(web_pid_file)" "$WEB_PORT"
}

worker_runtime_pid() {
  local pid_file pid
  pid_file=$(worker_pid_file)
  cleanup_stale_pid_file "$pid_file"
  pid=$(read_pid_file "$pid_file")
  if [[ -n "$pid" ]] && is_pid_running "$pid"; then
    printf '%s\n' "$pid"
    return
  fi

  find_process_pid_by_pattern "src/entrypoints/main.py --poll-interval 2"
}

port_pid() {
  local port=$1
  lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -n 1 || true
}

is_pid_running() {
  local pid=$1
  if [[ -z "$pid" ]]; then
    return 1
  fi
  kill -0 "$pid" 2>/dev/null
}

wait_for_pid_exit() {
  local pid=$1
  local attempts=${2:-50}
  local interval=${3:-0.1}
  local i

  if [[ -z "$pid" ]]; then
    return 0
  fi

  for ((i = 0; i < attempts; i += 1)); do
    if ! is_pid_running "$pid"; then
      return 0
    fi
    sleep "$interval"
  done

  return 1
}

read_pid_file() {
  local pid_file=$1
  if [[ -f "$pid_file" ]]; then
    tr -d '[:space:]' < "$pid_file"
  fi
}

cleanup_stale_pid_file() {
  local pid_file=$1
  local pid
  pid=$(read_pid_file "$pid_file")
  if [[ -n "$pid" ]] && ! is_pid_running "$pid"; then
    rm -f "$pid_file"
  fi
}

ensure_python_venv() {
  local app_dir=$1
  if [[ ! -x "$app_dir/.venv/bin/python" ]]; then
    (
      cd "$app_dir"
      python3 -m venv .venv
      .venv/bin/pip install -e .
    )
  fi
}

ensure_web_dependencies() {
  local app_dir=$1
  if [[ ! -d "$app_dir/node_modules" ]]; then
    (
      cd "$app_dir"
      npm install
    )
  fi
}

print_service_line() {
  local name=$1
  local status=$2
  local details=$3
  printf '%-8s %-8s %s\n' "$name" "$status" "$details"
}

find_process_pid_by_pattern() {
  local pattern=$1
  ps -axo pid=,command= | awk -v pattern="$pattern" '
    index($0, pattern) > 0 && index($0, "awk -v pattern") == 0 {
      print $1
      exit
    }
  '
}

spawn_detached() {
  local cwd=$1
  local log_file=$2
  shift 2

  python3 - "$cwd" "$log_file" "$@" <<'PY'
import os
import subprocess
import sys

cwd = sys.argv[1]
log_file = sys.argv[2]
command = sys.argv[3:]

with open(log_file, "ab", buffering=0) as log_handle, open(os.devnull, "rb") as stdin_handle:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdin=stdin_handle,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

print(process.pid)
PY
}
