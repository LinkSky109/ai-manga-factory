#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="$(cd "$ROOT/../../../.." && pwd)"
PY="${AI_MANGA_FACTORY_PYTHON:-$WORKSPACE_ROOT/.venvs/ai-manga-factory/Scripts/python.exe}"
VALIDATOR="$ROOT/scripts/validate_job_output.py"
RUNNER="$ROOT/scripts/run_adaptation_pack.py"
PACK_NAME="${1:-dgyx_ch1_20}"

echo "[retry] validating latest manga output..."
if "$PY" "$VALIDATOR" --pack-name "$PACK_NAME"; then
  echo "[retry] latest output already passes validation."
  exit 0
fi

echo "[retry] validation failed, rerunning staged generation..."
EXTRA_ARGS=()
if [[ -n "${ARK_API_KEY:-}" || -n "${VOLC_ARK_API_KEY:-}" ]]; then
  EXTRA_ARGS+=("--real-images")
fi
"$PY" "$RUNNER" --pack-name "$PACK_NAME" --scene-count 20 "${EXTRA_ARGS[@]}"
echo "[retry] rerun complete"
