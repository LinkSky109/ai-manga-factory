#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
ENV_FILE=${ENV_FILE:-"$REPO_ROOT/infra/compose/.env.prod"}
OUTPUT_DIR=${OUTPUT_DIR:-"$REPO_ROOT/backups/releases"}
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
OUTPUT_PATH="$OUTPUT_DIR/factory-smoke-$TIMESTAMP.md"
SOURCE_FILE=${SOURCE_FILE:-"$REPO_ROOT/data/demo_projects/dpcq_chapter_seed.md"}
JOB_TIMEOUT_SECONDS=${JOB_TIMEOUT_SECONDS:-90}
POLL_INTERVAL_SECONDS=${POLL_INTERVAL_SECONDS:-2}
EXECUTION_MODE=${EXECUTION_MODE:-async}
ROUTING_MODE=${ROUTING_MODE:-smart}
PROJECT_NAME=${PROJECT_NAME:-"生产链路 Smoke $TIMESTAMP"}

mkdir -p "$OUTPUT_DIR"
TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

read_env_value() {
  local key=$1
  local line
  if [[ ! -f "$ENV_FILE" ]]; then
    return 0
  fi
  line=$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 || true)
  printf '%s' "${line#*=}"
}

truthy() {
  local raw=$1
  local normalized
  normalized=$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')
  [[ "$normalized" == "1" || "$normalized" == "true" || "$normalized" == "yes" || "$normalized" == "on" ]]
}

PUBLIC_HTTP_PORT=${PUBLIC_HTTP_PORT:-$(read_env_value "PUBLIC_HTTP_PORT")}
BASE_URL=${BASE_URL:-"http://127.0.0.1:${PUBLIC_HTTP_PORT:-8080}"}
AUTH_ENABLED=${AUTH_ENABLED:-$(read_env_value "AUTH_ENABLED")}
PROD_API_TOKEN=${PROD_API_TOKEN:-$(read_env_value "AUTH_BOOTSTRAP_ADMIN_TOKEN")}

AUTH_CURL_ARGS=()
if truthy "${AUTH_ENABLED:-false}"; then
  if [[ -z "${PROD_API_TOKEN:-}" || "${PROD_API_TOKEN:-}" == "change-me" ]]; then
    echo "AUTH_ENABLED=true but PROD_API_TOKEN is missing. Export PROD_API_TOKEN or provide a populated ENV_FILE."
    exit 1
  fi
  AUTH_CURL_ARGS=(-H "Authorization: Bearer $PROD_API_TOKEN")
fi

if [[ ! -f "$SOURCE_FILE" ]]; then
  SOURCE_FILE="$TEMP_DIR/fallback-source.txt"
  cat > "$SOURCE_FILE" <<'EOF'
第1章 乌坦城风起
萧炎站在乌坦城议事堂中央，望向远处的药老。族人们在大堂里低声议论。

第2章 夜谈药老
夜色降临，萧炎来到后山石台，与药老对谈。月光落在山道和古树之间。
EOF
fi

request_json() {
  local method=$1
  local path=$2
  local payload_file=${3:-}
  local response_file
  local status_code

  response_file=$(mktemp "$TEMP_DIR/response.XXXXXX")

  if [[ -n "$payload_file" ]]; then
    status_code=$(
      curl --silent --show-error --output "$response_file" --write-out "%{http_code}" \
        --request "$method" \
        -H "Content-Type: application/json" \
        "${AUTH_CURL_ARGS[@]}" \
        --data-binary "@$payload_file" \
        "$BASE_URL$path"
    )
  else
    status_code=$(
      curl --silent --show-error --output "$response_file" --write-out "%{http_code}" \
        --request "$method" \
        "${AUTH_CURL_ARGS[@]}" \
        "$BASE_URL$path"
    )
  fi

  if [[ ! "$status_code" =~ ^2 ]]; then
    echo "Request failed: $method $BASE_URL$path"
    echo "HTTP status: $status_code"
    cat "$response_file"
    exit 1
  fi

  cat "$response_file"
}

json_get() {
  local payload=$1
  local path=$2
  python3 - "$payload" "$path" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1] or "null")
path = [segment for segment in sys.argv[2].split(".") if segment]
value = payload
for segment in path:
    if isinstance(value, list):
        value = value[int(segment)]
    else:
        value = value[segment]
if isinstance(value, (dict, list)):
    print(json.dumps(value, ensure_ascii=False))
elif value is None:
    print("")
else:
    print(value)
PY
}

json_maybe_get() {
  local payload=$1
  local path=$2
  python3 - "$payload" "$path" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1] or "null")
path = [segment for segment in sys.argv[2].split(".") if segment]
value = payload
try:
    for segment in path:
        if value is None:
            print("")
            raise SystemExit(0)
        if isinstance(value, list):
            value = value[int(segment)]
        else:
            value = value[segment]
except (KeyError, IndexError, TypeError, ValueError):
    print("")
    raise SystemExit(0)
if isinstance(value, (dict, list)):
    print(json.dumps(value, ensure_ascii=False))
elif value is None:
    print("")
else:
    print(value)
PY
}

json_len() {
  local payload=$1
  local path=$2
  python3 - "$payload" "$path" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1] or "null")
path = [segment for segment in sys.argv[2].split(".") if segment]
value = payload
for segment in path:
    if isinstance(value, list):
        value = value[int(segment)]
    else:
        value = value[segment]
print(len(value))
PY
}

fetch_playback() {
  local playback_url=$1
  local target_url
  if [[ "$playback_url" == http://* || "$playback_url" == https://* ]]; then
    target_url=$playback_url
  else
    target_url="$BASE_URL$playback_url"
  fi
  curl --fail --silent --show-error --output /dev/null "${AUTH_CURL_ARGS[@]}" "$target_url"
}

project_payload="$TEMP_DIR/project.json"
python3 - "$PROJECT_NAME" <<'PY' > "$project_payload"
import json
import sys

print(json.dumps({
    "name": sys.argv[1],
    "description": "Step 12 production minimal factory smoke",
}, ensure_ascii=False))
PY

project_response=$(request_json "POST" "/api/v1/projects" "$project_payload")
project_id=$(json_get "$project_response" "id")

init_payload="$TEMP_DIR/initialize.json"
python3 - "$SOURCE_FILE" "$ROUTING_MODE" <<'PY' > "$init_payload"
import json
import sys
from pathlib import Path

source_path = Path(sys.argv[1])
routing_mode = sys.argv[2]
text = source_path.read_text(encoding="utf-8")
print(json.dumps({
    "source_title": source_path.stem,
    "source_type": "novel_text",
    "source_text": text,
    "overwrite_assets": False,
    "routing_mode": routing_mode,
}, ensure_ascii=False))
PY

init_response=$(request_json "POST" "/api/v1/projects/$project_id/initialize" "$init_payload")
chapter_count=$(json_len "$init_response" "chapters")
if [[ "$chapter_count" -lt 1 ]]; then
  echo "Initialization returned no chapters."
  exit 1
fi

chapter_id=$(json_get "$init_response" "chapters.0.id")
generation_provider=$(json_maybe_get "$init_response" "generation_trace.resolved_provider_key")

workflow_payload="$TEMP_DIR/workflow.json"
python3 - "$project_id" "$ROUTING_MODE" <<'PY' > "$workflow_payload"
import json
import sys

print(json.dumps({
    "project_id": int(sys.argv[1]),
    "name": "生产最小 Smoke 流水线",
    "description": "验证初始化、异步执行、预览闭环",
    "routing_mode": sys.argv[2],
    "nodes": [
        {"key": "storyboard", "title": "分镜", "provider_type": "llm"},
        {"key": "video", "title": "视频", "provider_type": "video"},
        {"key": "voice", "title": "配音", "provider_type": "voice"}
    ],
    "edges": [
        {"source": "storyboard", "target": "video"},
        {"source": "video", "target": "voice"}
    ],
}, ensure_ascii=False))
PY

workflow_response=$(request_json "POST" "/api/v1/workflows" "$workflow_payload")
workflow_id=$(json_get "$workflow_response" "id")

job_payload="$TEMP_DIR/job.json"
python3 - "$project_id" "$chapter_id" "$workflow_id" "$EXECUTION_MODE" "$ROUTING_MODE" <<'PY' > "$job_payload"
import json
import sys

print(json.dumps({
    "project_id": int(sys.argv[1]),
    "chapter_id": int(sys.argv[2]),
    "workflow_id": int(sys.argv[3]),
    "execution_mode": sys.argv[4],
    "routing_mode": sys.argv[5],
    "input": {},
}, ensure_ascii=False))
PY

job_response=$(request_json "POST" "/api/v1/jobs" "$job_payload")
job_id=$(json_get "$job_response" "id")
job_status=$(json_get "$job_response" "status")

deadline=$(( $(date +%s) + JOB_TIMEOUT_SECONDS ))
while [[ "$job_status" == "queued" || "$job_status" == "running" ]]; do
  if [[ "$(date +%s)" -ge "$deadline" ]]; then
    echo "Timed out waiting for job $job_id to complete."
    exit 1
  fi
  sleep "$POLL_INTERVAL_SECONDS"
  job_response=$(request_json "GET" "/api/v1/jobs/$job_id")
  job_status=$(json_get "$job_response" "status")
done

if [[ "$job_status" != "completed" ]]; then
  echo "Smoke job $job_id did not complete successfully."
  echo "$job_response"
  exit 1
fi

preview_response=$(request_json "GET" "/api/v1/projects/$project_id/previews")
preview_count=$(json_len "$preview_response" "items")
if [[ "$preview_count" -lt 1 ]]; then
  echo "Smoke run produced no preview items."
  exit 1
fi

first_playback_url=$(json_get "$preview_response" "items.0.playback_url")
first_stage_key=$(json_get "$preview_response" "items.0.stage_key")
fetch_playback "$first_playback_url"

monitoring_response=$(request_json "GET" "/api/v1/monitoring/overview")
queued_jobs=$(json_get "$monitoring_response" "summary.queued_jobs")
running_jobs=$(json_get "$monitoring_response" "summary.running_jobs")

cat > "$OUTPUT_PATH" <<EOF
# Factory Smoke Record

- Timestamp: $TIMESTAMP
- Base URL: $BASE_URL
- Env File: $ENV_FILE
- Source File: $SOURCE_FILE
- Execution Mode: $EXECUTION_MODE
- Routing Mode: $ROUTING_MODE
- Project ID: $project_id
- Chapter ID: $chapter_id
- Workflow ID: $workflow_id
- Job ID: $job_id
- Job Status: $job_status
- Initialization Provider: ${generation_provider:-unknown}
- Preview Count: $preview_count
- First Preview Stage: $first_stage_key
- First Preview URL: $first_playback_url
- Monitoring queued_jobs: $queued_jobs
- Monitoring running_jobs: $running_jobs

## Notes

- This smoke verifies: project creation, source initialization, workflow creation, job execution, preview listing, preview fetch, and monitoring overview.
EOF

echo "Factory smoke completed successfully."
echo "Project: $project_id | Workflow: $workflow_id | Job: $job_id | Previews: $preview_count"
echo "Factory smoke record created: $OUTPUT_PATH"
