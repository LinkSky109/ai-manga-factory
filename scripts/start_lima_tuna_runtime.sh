#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
CONFIG_FILE="$REPO_ROOT/infra/compose/lima/tuna-docker-rootful.yaml"
INSTANCE_NAME=${INSTANCE_NAME:-tuna-docker}
CONTEXT_NAME="lima-$INSTANCE_NAME"

if ! command -v limactl >/dev/null 2>&1; then
  echo "limactl is required but not installed."
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker CLI is required but not installed."
  exit 1
fi

if limactl list --format '{{.Name}}' | grep -qx "$INSTANCE_NAME"; then
  echo "Starting existing Lima instance: $INSTANCE_NAME"
  limactl start "$INSTANCE_NAME" --tty=false --timeout 30m
else
  echo "Creating and starting Lima instance from $CONFIG_FILE"
  limactl start --name "$INSTANCE_NAME" "$CONFIG_FILE" --tty=false --timeout 30m
fi

SOCKET_DIR=$(limactl list "$INSTANCE_NAME" --format '{{.Dir}}')
SOCKET_URL="unix://$SOCKET_DIR/sock/docker.sock"

if ! docker context inspect "$CONTEXT_NAME" >/dev/null 2>&1; then
  docker context create "$CONTEXT_NAME" --docker "host=$SOCKET_URL" >/dev/null
fi

docker context use "$CONTEXT_NAME" >/dev/null

echo "Docker context switched to $CONTEXT_NAME"
docker info >/dev/null
echo "Docker runtime is reachable via $SOCKET_URL"
