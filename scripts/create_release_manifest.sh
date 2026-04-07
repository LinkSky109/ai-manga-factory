#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
OUTPUT_DIR=${OUTPUT_DIR:-"$REPO_ROOT/backups/releases"}
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
OUTPUT_PATH="$OUTPUT_DIR/release-manifest-$TIMESTAMP.md"

mkdir -p "$OUTPUT_DIR"

git_value() {
  local cmd=$1
  if command -v git >/dev/null 2>&1 && git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$REPO_ROOT" $cmd 2>/dev/null || echo "unknown"
  else
    echo "unknown"
  fi
}

GIT_SHA=$(git_value "rev-parse HEAD")
GIT_BRANCH=$(git_value "rev-parse --abbrev-ref HEAD")
GIT_STATUS=$(git_value "status --short")

cat > "$OUTPUT_PATH" <<EOF
# Release Manifest

- Timestamp: $TIMESTAMP
- Git SHA: $GIT_SHA
- Git Branch: $GIT_BRANCH
- Env File: ${ENV_FILE:-infra/compose/.env.prod}
- Regression Command: RUN_E2E_BROWSER=1 bash /Users/link/work/ai-manga-factory/scripts/test.sh
- Deploy Command: bash /Users/link/work/ai-manga-factory/scripts/deploy_prod.sh

## Git Status

\`\`\`
$GIT_STATUS
\`\`\`
EOF

echo "Release manifest created: $OUTPUT_PATH"
