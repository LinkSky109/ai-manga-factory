#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
ENV_FILE=${ENV_FILE:-"$REPO_ROOT/infra/compose/.env.prod"}
OUTPUT_DIR=${OUTPUT_DIR:-"$REPO_ROOT/backups/releases"}
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
OUTPUT_PATH="$OUTPUT_DIR/deployment-drill-$TIMESTAMP.md"

RUN_REGRESSION=${RUN_REGRESSION:-1}
RUN_VERIFY=${RUN_VERIFY:-1}
RUN_DEPLOY=${RUN_DEPLOY:-0}
RUN_SMOKE=${RUN_SMOKE:-0}
RUN_BACKUP=${RUN_BACKUP:-0}
RUN_FACTORY_SMOKE=${RUN_FACTORY_SMOKE:-0}
RUN_RELEASE_MANIFEST=${RUN_RELEASE_MANIFEST:-1}
RUN_E2E_BROWSER=${RUN_E2E_BROWSER:-1}

mkdir -p "$OUTPUT_DIR"

RELEASE_MANIFEST_PATH="not-created"
OVERALL_RESULT="PASS"

git_value() {
  local cmd=$1
  if command -v git >/dev/null 2>&1 && git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$REPO_ROOT" $cmd 2>/dev/null || echo "unknown"
  else
    echo "unknown"
  fi
}

run_step() {
  local label=$1
  local command_string=$2
  local logfile
  logfile=$(mktemp)

  printf '\n[%s] %s\n' "$(date +"%H:%M:%S")" "$label"
  if bash -lc "$command_string" >"$logfile" 2>&1; then
    append_step "$label" "PASS" "$command_string" "$logfile"
  else
    OVERALL_RESULT="FAIL"
    append_step "$label" "FAIL" "$command_string" "$logfile"
    cat "$logfile"
    rm -f "$logfile"
    echo "Deployment drill failed at step: $label"
    exit 1
  fi

  if [[ "$label" == "Create Release Manifest" ]]; then
    RELEASE_MANIFEST_PATH=$(grep -Eo '/.*release-manifest-[0-9-]+\.md' "$logfile" | tail -n 1 || true)
    if [[ -z "$RELEASE_MANIFEST_PATH" ]]; then
      RELEASE_MANIFEST_PATH="created-but-path-unresolved"
    fi
  fi

  rm -f "$logfile"
}

append_step() {
  local label=$1
  local status=$2
  local command_string=$3
  local logfile=$4
  {
    printf '## %s\n\n' "$label"
    printf -- '- Status: %s\n' "$status"
    printf -- '- Command: `%s`\n\n' "$command_string"
    printf '```text\n'
    cat "$logfile"
    printf '\n```\n\n'
  } >> "$OUTPUT_PATH"
}

cat > "$OUTPUT_PATH" <<EOF
# Deployment Drill Record

- Timestamp: $TIMESTAMP
- Env File: $ENV_FILE
- Git SHA: $(git_value "rev-parse HEAD")
- Git Branch: $(git_value "rev-parse --abbrev-ref HEAD")
- Planned Release Manifest: pending
- Overall Result: pending

EOF

if [[ "$RUN_REGRESSION" == "1" ]]; then
  run_step "Regression Suite" "cd '$REPO_ROOT' && RUN_E2E_BROWSER='$RUN_E2E_BROWSER' bash scripts/test.sh"
fi

if [[ "$RUN_VERIFY" == "1" ]]; then
  run_step "Verify Production Stack" "cd '$REPO_ROOT' && ENV_FILE='$ENV_FILE' bash scripts/verify_prod_stack.sh"
fi

if [[ "$RUN_RELEASE_MANIFEST" == "1" ]]; then
  run_step "Create Release Manifest" "cd '$REPO_ROOT' && ENV_FILE='$ENV_FILE' bash scripts/create_release_manifest.sh"
fi

if [[ "$RUN_DEPLOY" == "1" ]]; then
  run_step "Deploy Production Stack" "cd '$REPO_ROOT' && ENV_FILE='$ENV_FILE' bash scripts/deploy_prod.sh"
fi

if [[ "$RUN_SMOKE" == "1" ]]; then
  run_step "Production Smoke Check" "cd '$REPO_ROOT' && ENV_FILE='$ENV_FILE' bash scripts/check_production_endpoints.sh"
fi

if [[ "$RUN_FACTORY_SMOKE" == "1" ]]; then
  run_step "Factory Workflow Smoke" "cd '$REPO_ROOT' && ENV_FILE='$ENV_FILE' bash scripts/run_factory_smoke.sh"
fi

if [[ "$RUN_BACKUP" == "1" ]]; then
  run_step "PostgreSQL Backup Drill" "cd '$REPO_ROOT' && ENV_FILE='$ENV_FILE' bash scripts/backup_postgres.sh"
fi

python3 - "$OUTPUT_PATH" "$RELEASE_MANIFEST_PATH" "$OVERALL_RESULT" <<'PY'
from pathlib import Path
import sys

output_path = Path(sys.argv[1])
manifest_path = sys.argv[2]
overall_result = sys.argv[3]
content = output_path.read_text(encoding="utf-8")
content = content.replace("- Planned Release Manifest: pending", f"- Planned Release Manifest: {manifest_path}")
content = content.replace("- Overall Result: pending", f"- Overall Result: {overall_result}")
output_path.write_text(content, encoding="utf-8")
PY

echo "Deployment drill record created: $OUTPUT_PATH"
