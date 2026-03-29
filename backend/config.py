from pathlib import Path

from shared.runtime_storage import PROJECT_DATA_DIR, PROJECT_ROOT, ensure_runtime_subdirs, get_runtime_storage_plan


ROOT_DIR = PROJECT_ROOT
STATIC_DATA_DIR = PROJECT_DATA_DIR
REFERENCE_DATA_DIR = STATIC_DATA_DIR / "reference"
ADAPTATIONS_DIR = ROOT_DIR / "adaptations"
WORKHOME_DIR = ROOT_DIR.parent.parent
LEGACY_FRONTEND_DIR = ROOT_DIR / "frontend"
WEB_APP_DIR = ROOT_DIR / "web"
WEB_DIST_DIR = WEB_APP_DIR / "dist"

RUNTIME_STORAGE_PLAN = get_runtime_storage_plan()
RUNTIME_ROOT = RUNTIME_STORAGE_PLAN.runtime_root
DATA_DIR = RUNTIME_ROOT
DB_PATH = DATA_DIR / "platform.db"
ARTIFACTS_DIR = DATA_DIR / "artifacts"
PROVIDER_USAGE_DIR = DATA_DIR / "provider_usage"
MODEL_BUDGET_CONFIG_PATH = PROVIDER_USAGE_DIR / "model_budget_config.json"
USAGE_LEDGER_PATH = PROVIDER_USAGE_DIR / "usage_ledger.json"
REQUIREMENTS_DIR = DATA_DIR / "requirements"
SOURCE_SESSIONS_DIR = DATA_DIR / "source_sessions"
BACKEND_LOG_PATH = DATA_DIR / "backend.log"
BACKEND_ERROR_LOG_PATH = DATA_DIR / "backend-error.log"
PROVIDER_TEST_VIDEO_PATH = DATA_DIR / "provider_test_i2v.mp4"

ensure_runtime_subdirs(
    DATA_DIR,
    [
        "artifacts",
        "provider_usage",
        "requirements",
        "source_sessions",
    ],
)
REFERENCE_DATA_DIR.mkdir(parents=True, exist_ok=True)
ADAPTATIONS_DIR.mkdir(parents=True, exist_ok=True)
