#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
source "$SCRIPT_DIR/common.sh"

SERVICE=${SERVICE:-${1:-}}
LINES=${LINES:-40}
FOLLOW=${FOLLOW:-0}

if [[ $# -gt 0 ]] && [[ ${1:-} == "$SERVICE" ]]; then
  shift
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --follow|-f)
      FOLLOW=1
      ;;
    --lines|-n)
      shift
      if [[ $# -eq 0 ]]; then
        echo "missing value for --lines" >&2
        exit 1
      fi
      LINES=$1
      ;;
    api|web|worker)
      SERVICE=$1
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 1
      ;;
  esac
  shift
done

if ! [[ "$LINES" =~ ^[0-9]+$ ]] || [[ "$LINES" -lt 1 ]]; then
  echo "LINES must be a positive integer" >&2
  exit 1
fi

print_log_block() {
  local service=$1
  local log_file
  log_file=$(service_log_file "$service") || {
    echo "unknown service: $service" >&2
    exit 1
  }

  printf '===== %s (%s) =====\n' "$service" "$log_file"
  if [[ -f "$log_file" ]]; then
    tail -n "$LINES" "$log_file"
  else
    echo "log file not found"
  fi
}

if [[ -n "$SERVICE" ]]; then
  log_file=$(service_log_file "$SERVICE") || {
    echo "unknown service: $SERVICE" >&2
    exit 1
  }

  if [[ "$FOLLOW" == "1" ]]; then
    touch "$log_file"
    exec tail -n "$LINES" -f "$log_file"
  fi

  print_log_block "$SERVICE"
  exit 0
fi

if [[ "$FOLLOW" == "1" ]]; then
  touch "$(api_log_file)" "$(web_log_file)" "$(worker_log_file)"
  exec tail -n "$LINES" -f "$(api_log_file)" "$(web_log_file)" "$(worker_log_file)"
fi

print_log_block api
echo
print_log_block web
echo
print_log_block worker
