#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

printf '\n[1/4] API unit + integration tests\n'
(
  cd "$REPO_ROOT/apps/api"
  .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
)

printf '\n[2/4] Web production build\n'
(
  cd "$REPO_ROOT/apps/web"
  npm run build
)

printf '\n[3/4] Playwright spec compile/list\n'
(
  cd "$REPO_ROOT/apps/web"
  npm run test:e2e:list
)

printf '\n[4/4] Optional browser E2E\n'
if [[ "${RUN_E2E_BROWSER:-0}" == "1" ]]; then
  (
    cd "$REPO_ROOT/apps/web"
    npm run test:e2e
  )
else
  printf 'Skipping browser execution. Set RUN_E2E_BROWSER=1 to run full Playwright smoke tests.\n'
fi
