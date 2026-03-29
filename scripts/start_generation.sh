#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="$(cd "$ROOT/../../../.." && pwd)"
PY="${AI_MANGA_FACTORY_PYTHON:-$WORKSPACE_ROOT/.venvs/ai-manga-factory/Scripts/python.exe}"
RUNNER="$ROOT/scripts/run_adaptation_pack.py"

PACK_NAME="${1:-dgyx_ch1_20}"
SCENE_COUNT="${2:-20}"
MODE="${3:-placeholder}"

EXTRA_ARGS=()
if [[ -n "${ARK_API_KEY:-}" || -n "${VOLC_ARK_API_KEY:-}" ]]; then
  EXTRA_ARGS+=("--real-images")
fi

if [[ "$MODE" == "real" ]]; then
  EXTRA_ARGS+=("--real-images")
fi

echo "[run] starting adaptation pack: $PACK_NAME"
"$PY" "$RUNNER" --pack-name "$PACK_NAME" --scene-count "$SCENE_COUNT" "${EXTRA_ARGS[@]}"
echo "[run] done"
