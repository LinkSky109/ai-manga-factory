#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

bash "$SCRIPT_DIR/stop_services.sh"
bash "$SCRIPT_DIR/start_services.sh"
