from urllib.parse import quote, unquote, urlparse
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import json

from backend.adaptation_packs import (
    build_adaptation_job_payload,
    build_batch_job_payloads,
    get_adaptation_pack,
    list_adaptation_packs,
)
from backend.config import ADAPTATIONS_DIR, ARTIFACTS_DIR, PROVIDER_USAGE_DIR, REFERENCE_DATA_DIR, ROOT_DIR, RUNTIME_STORAGE_PLAN
from backend.config import LEGACY_FRONTEND_DIR, WEB_DIST_DIR
from backend.executor import JobExecutor
from backend.schemas import (
    AdaptationBatchRequest,
    AdaptationBatchResponse,
    AdaptationJobRequest,
    ArtifactInventoryItemResponse,
    ArtifactInventoryResponse,
    ArtifactSyncProviderResponse,
    ArtifactSyncStatusResponse,
    AdaptationPackLatestResultResponse,
    AdaptationPackResponse,
    BatchSyncStorageRequest,
    BatchSyncStorageResponse,
    BatchJobResponse,
    BatchRetryRequest,
    BatchRetryResponse,
    CloudSyncOverviewProviderResponse,
    CloudSyncOverviewResponse,
    CloudSyncTaskListResponse,
    CloudSyncTaskResponse,
    JobCreate,
    JobListResponse,
    JobResponse,
    JobSyncTriggerItemResponse,
    JobSyncTriggerRequest,
    JobSyncTriggerResponse,
    JobSyncProviderResponse,
    JobSyncStatusResponse,
    JobSummaryBucketResponse,
    JobSummaryResponse,
    ProviderUsageResponse,
    StageModelPlanResponse,
    ProjectCreate,
    ProjectResponse,
    UiPreferencesResponse,
    UiPreferencesUpdate,
)
from backend.storage import PlatformStore
from modules.registry import CapabilityRegistry
from shared.aliyun_pan_sync import sync_business_outputs_to_aliyundrive
from shared.providers.model_usage import ModelUsageManager
from shared.quark_pan_sync import sync_business_outputs_to_quark
from shared.result_depository import get_latest_pack_result
from shared.runtime_storage import load_runtime_storage_config


store = PlatformStore()
registry = CapabilityRegistry()
executor = JobExecutor(store=store, registry=registry)
executor.reconcile_orphaned_jobs()
usage_manager = ModelUsageManager()
app = FastAPI(title="AI Manga Factory", version="1.0.0")
SYNC_TASKS_FILE = PROVIDER_USAGE_DIR / "cloud_sync_tasks.json"
SYNC_TASKS_LOCK = Lock()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
ADAPTATIONS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/adaptation-files", StaticFiles(directory=ADAPTATIONS_DIR), name="adaptation-files")
if LEGACY_FRONTEND_DIR.exists():
    app.mount("/legacy-static", StaticFiles(directory=LEGACY_FRONTEND_DIR), name="legacy-static")
if WEB_DIST_DIR.exists():
    app.mount("/app", StaticFiles(directory=WEB_DIST_DIR, html=True), name="app")


def _resolve_artifact_file(artifact_path: str):
    candidate = (ARTIFACTS_DIR / artifact_path).resolve()
    artifacts_root = ARTIFACTS_DIR.resolve()
    if candidate != artifacts_root and artifacts_root not in candidate.parents:
        raise HTTPException(status_code=404, detail="Artifact not found")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return candidate


def _should_redirect_artifact_to_app(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept or "*/*" in accept


def _get_artifact_kind(url: str) -> str:
    path = url.lower()
    if path.endswith(".md"):
        return "markdown"
    if path.endswith(".json"):
        return "json"
    if path.endswith((".txt", ".log", ".csv")):
        return "text"
    if path.endswith((".png", ".jpg", ".jpeg", ".webp", ".svg")):
        return "image"
    if path.endswith((".mp4", ".webm")):
        return "video"
    if path.endswith((".mp3", ".wav")):
        return "audio"
    if path.endswith((".html", ".htm")):
        return "html"
    if path.endswith(".pdf"):
        return "pdf"
    return "file"


def _safe_json_load(path: Path) -> dict:
    if not path.exists() or not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def _normalize_path_value(path: Path | str | None) -> str:
    if not path:
        return ""
    try:
        resolved = Path(path).expanduser().resolve()
    except OSError:
        return str(path).replace("\\", "/").lower()
    return str(resolved).replace("\\", "/").lower()


def _resolve_local_file_from_artifact_url(artifact_url: str) -> Path | None:
    parsed = urlparse(artifact_url)
    path = unquote(parsed.path)

    if path.startswith("/artifacts/"):
        try:
            return _resolve_artifact_file(path.removeprefix("/artifacts/"))
        except HTTPException:
            return None

    if path.startswith("/adaptation-files/"):
        relative = path.removeprefix("/adaptation-files/")
        candidate = (ADAPTATIONS_DIR / relative).resolve()
        adaptations_root = ADAPTATIONS_DIR.resolve()
        if candidate != adaptations_root and adaptations_root not in candidate.parents:
            return None
        if not candidate.exists() or not candidate.is_file():
            return None
        return candidate

    return None


def _provider_sync_meta() -> dict[str, dict[str, str | Path]]:
    return {
        "quark_pan": {
            "display_name": "夸克网盘",
            "report_path": PROVIDER_USAGE_DIR / "quark_pan_last_sync.json",
            "provider_home_url": "https://pan.quark.cn/",
        },
        "aliyundrive": {
            "display_name": "阿里云盘",
            "report_path": PROVIDER_USAGE_DIR / "aliyundrive_last_sync.json",
            "provider_home_url": "https://www.alipan.com/drive",
        },
    }


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat()


def _report_entries(report: dict, *keys: str) -> list[dict]:
    items: list[dict] = []
    for key in keys:
        value = report.get(key, [])
        if isinstance(value, list):
            items.extend(item for item in value if isinstance(item, dict))
    return items


def _load_sync_tasks() -> list[dict]:
    payload = _safe_json_load(SYNC_TASKS_FILE)
    items = payload.get("items", [])
    return [item for item in items if isinstance(item, dict)]


def _save_sync_tasks(items: list[dict]) -> None:
    SYNC_TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SYNC_TASKS_FILE.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")


def _list_sync_tasks() -> list[dict]:
    with SYNC_TASKS_LOCK:
        items = _load_sync_tasks()
    items.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return items[:20]


def _enqueue_sync_task(*, scope: str, job_ids: list[int], provider: str, dry_run: bool = False) -> dict:
    task = {
        "id": f"sync-{uuid4().hex[:12]}",
        "scope": scope,
        "provider": provider,
        "job_ids": job_ids,
        "status": "queued",
        "dry_run": dry_run,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "note": "已加入后台同步队列",
        "items": [],
        "error": None,
    }
    with SYNC_TASKS_LOCK:
        items = _load_sync_tasks()
        items.insert(0, task)
        _save_sync_tasks(items[:50])
    return task


def _update_sync_task(task_id: str, **changes) -> dict | None:
    with SYNC_TASKS_LOCK:
        items = _load_sync_tasks()
        updated = None
        for item in items:
            if item.get("id") == task_id:
                item.update(changes)
                item["updated_at"] = _now_iso()
                updated = item
                break
        _save_sync_tasks(items[:50])
    return updated


def _serialize_sync_task(item: dict) -> CloudSyncTaskResponse:
    return CloudSyncTaskResponse(
        id=str(item.get("id") or ""),
        scope=str(item.get("scope") or "job"),  # type: ignore[arg-type]
        provider=str(item.get("provider") or "all"),  # type: ignore[arg-type]
        job_ids=[int(job_id) for job_id in item.get("job_ids", []) if isinstance(job_id, int)],
        status=str(item.get("status") or "queued"),  # type: ignore[arg-type]
        dry_run=bool(item.get("dry_run", False)),
        created_at=str(item.get("created_at") or ""),
        updated_at=str(item.get("updated_at") or ""),
        note=item.get("note"),
        items=[JobSyncTriggerItemResponse(**entry) for entry in item.get("items", []) if isinstance(entry, dict)],
        error=item.get("error"),
    )


def _job_related_local_roots(job_id: int) -> list[Path]:
    roots: list[Path] = []
    job_root = ARTIFACTS_DIR / f"job_{job_id}"
    if job_root.exists():
        roots.append(job_root.resolve())

    snapshot_path = job_root / "result_snapshot.json"
    snapshot = _safe_json_load(snapshot_path)
    pack_name = str(snapshot.get("adaptation_pack") or "").strip()
    if pack_name:
        pack_reports = ARTIFACTS_DIR / "pack_reports" / pack_name / "reports"
        if not pack_reports.exists():
            pack_reports = ADAPTATIONS_DIR / pack_name / "reports"
        if pack_reports.exists():
            roots.append(pack_reports.resolve())

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        normalized = _normalize_path_value(root)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(root)
    return unique


def _matches_roots(local_path: str, roots: list[Path]) -> bool:
    normalized = _normalize_path_value(local_path)
    if not normalized:
        return False
    for root in roots:
        root_value = _normalize_path_value(root)
        if normalized == root_value or normalized.startswith(f"{root_value}/"):
            return True
    return False


def _build_artifact_sync_status(artifact_url: str) -> ArtifactSyncStatusResponse:
    local_path = _resolve_local_file_from_artifact_url(artifact_url)
    normalized_local_path = _normalize_path_value(local_path)
    providers: list[ArtifactSyncProviderResponse] = []

    for provider, meta in _provider_sync_meta().items():
        report = _safe_json_load(Path(meta["report_path"]))
        provider_home_url = str(meta["provider_home_url"])
        display_name = str(meta["display_name"])

        if not report:
            providers.append(
                ArtifactSyncProviderResponse(
                    provider=provider,
                    display_name=display_name,
                    status="missing",
                    provider_home_url=provider_home_url,
                    note="暂无同步报告",
                )
            )
            continue

        matched_entry = None
        matched_status = "missing"
        for bucket, status in (("uploaded", "uploaded"), ("skipped", "synced")):
            for entry in report.get(bucket, []):
                if _normalize_path_value(entry.get("local_path")) == normalized_local_path:
                    matched_entry = entry
                    matched_status = status
                    break
            if matched_entry:
                break

        remote_path = None
        remote_dir = None
        file_web_url = None
        note = "最近一次同步报告未包含该产物"
        if matched_entry:
            remote_path = str(matched_entry.get("remote_path") or "") or None
            remote_dir = remote_path.rsplit("/", 1)[0] if remote_path and "/" in remote_path else remote_path
            upload_result = matched_entry.get("upload_result")
            if isinstance(upload_result, dict):
                file_web_url = upload_result.get("preview_url")
            note = "本次同步已上传到网盘" if matched_status == "uploaded" else "本次同步未变更，沿用云端已有文件"

        providers.append(
            ArtifactSyncProviderResponse(
                provider=provider,
                display_name=display_name,
                status=matched_status,
                updated_at=report.get("updated_at"),
                dry_run=bool(report.get("dry_run", False)),
                remote_path=remote_path,
                remote_dir=remote_dir,
                provider_home_url=provider_home_url,
                file_web_url=file_web_url,
                note=note,
                root_folder=report.get("root_folder"),
            )
        )

    return ArtifactSyncStatusResponse(
        artifact_url=artifact_url,
        local_path=str(local_path) if local_path else None,
        providers=providers,
    )


def _build_cloud_sync_overview() -> CloudSyncOverviewResponse:
    providers: list[CloudSyncOverviewProviderResponse] = []
    for provider, meta in _provider_sync_meta().items():
        report = _safe_json_load(Path(meta["report_path"]))
        if not report:
            providers.append(
                CloudSyncOverviewProviderResponse(
                    provider=provider,
                    display_name=str(meta["display_name"]),
                    provider_home_url=str(meta["provider_home_url"]),
                    note="暂无同步报告",
                )
            )
            continue

        providers.append(
            CloudSyncOverviewProviderResponse(
                provider=provider,
                display_name=str(meta["display_name"]),
                updated_at=report.get("updated_at"),
                dry_run=bool(report.get("dry_run", False)),
                root_folder=report.get("root_folder"),
                business_folder=report.get("business_folder"),
                pack_reports_folder=report.get("pack_reports_folder"),
                uploaded_count=len(_report_entries(report, "uploaded")),
                synced_count=len(_report_entries(report, "skipped")),
                pending_count=int(report.get("pending", 0) or 0),
                provider_home_url=str(meta["provider_home_url"]),
                note="最近一次同步已完成" if not bool(report.get("dry_run", False)) else "最近一次是 dry-run 计划",
            )
        )

    return CloudSyncOverviewResponse(
        runtime_provider=RUNTIME_STORAGE_PLAN.runtime_provider,
        remote_sync_enabled=RUNTIME_STORAGE_PLAN.remote_sync_enabled,
        remote_sync_provider=RUNTIME_STORAGE_PLAN.remote_sync_provider,
        providers=providers,
    )


def _build_job_sync_status(job_id: int) -> JobSyncStatusResponse:
    roots = _job_related_local_roots(job_id)
    providers: list[JobSyncProviderResponse] = []

    for provider, meta in _provider_sync_meta().items():
        report = _safe_json_load(Path(meta["report_path"]))
        display_name = str(meta["display_name"])
        home_url = str(meta["provider_home_url"])
        if not report:
            providers.append(
                JobSyncProviderResponse(
                    provider=provider,
                    display_name=display_name,
                    status="missing",
                    provider_home_url=home_url,
                    note="暂无同步报告",
                )
            )
            continue

        uploaded_entries = [entry for entry in _report_entries(report, "uploaded") if _matches_roots(str(entry.get("local_path") or ""), roots)]
        synced_entries = [entry for entry in _report_entries(report, "skipped") if _matches_roots(str(entry.get("local_path") or ""), roots)]
        remote_dirs = sorted(
            {
                str(entry.get("remote_path") or "").rsplit("/", 1)[0]
                for entry in [*uploaded_entries, *synced_entries]
                if str(entry.get("remote_path") or "").strip()
            }
        )

        status = "missing"
        note = "最近一次同步未包含该任务"
        if uploaded_entries:
            status = "uploaded"
            note = f"最近一次同步覆盖了 {len(uploaded_entries)} 个任务产物"
        elif synced_entries:
            status = "synced"
            note = f"最近一次同步复用了 {len(synced_entries)} 个云端文件"

        providers.append(
            JobSyncProviderResponse(
                provider=provider,
                display_name=display_name,
                status=status,
                updated_at=report.get("updated_at"),
                matched_files=len(uploaded_entries) + len(synced_entries),
                remote_dirs=remote_dirs,
                provider_home_url=home_url,
                note=note,
            )
        )

    return JobSyncStatusResponse(
        job_id=job_id,
        local_roots=[str(root) for root in roots],
        providers=providers,
    )


def _run_sync_for_job_ids(job_ids: set[int], provider: str, dry_run: bool) -> list[JobSyncTriggerItemResponse]:
    config = load_runtime_storage_config(RUNTIME_STORAGE_PLAN.config_path)
    remote_sync = config.get("remote_sync", {})
    providers = ["quark_pan", "aliyundrive"] if provider == "all" else [provider]
    items: list[JobSyncTriggerItemResponse] = []

    for current_provider in providers:
        if current_provider == "quark_pan":
            report = sync_business_outputs_to_quark(
                config=remote_sync.get("quark_pan", {}),
                dry_run=dry_run,
                job_ids=job_ids,
            )
        elif current_provider == "aliyundrive":
            report = sync_business_outputs_to_aliyundrive(
                config=remote_sync.get("aliyundrive", {}),
                dry_run=dry_run,
                job_ids=job_ids,
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {current_provider}")

        items.append(
            JobSyncTriggerItemResponse(
                provider=current_provider,
                dry_run=bool(report.get("dry_run", False)),
                planned=int(report.get("planned", 0) or 0),
                pending=int(report.get("pending", 0) or 0),
                uploaded=len(report.get("uploaded", [])),
                skipped=len(report.get("skipped", [])),
                updated_at=report.get("updated_at"),
                note="已执行 dry-run 计划" if bool(report.get("dry_run", False)) else "已完成网盘同步",
            )
        )

    return items


def _trigger_job_sync(job_id: int, provider: str, dry_run: bool) -> JobSyncTriggerResponse:
    items = _run_sync_for_job_ids(job_ids={job_id}, provider=provider, dry_run=dry_run)
    return JobSyncTriggerResponse(job_id=job_id, items=items)


def _trigger_batch_job_sync(job_ids: list[int], provider: str, dry_run: bool) -> BatchSyncStorageResponse:
    items = _run_sync_for_job_ids(job_ids=set(job_ids), provider=provider, dry_run=dry_run)
    return BatchSyncStorageResponse(job_ids=job_ids, items=items)


def _execute_sync_task(task_id: str) -> None:
    with SYNC_TASKS_LOCK:
        tasks = _load_sync_tasks()
        task = next((item for item in tasks if item.get("id") == task_id), None)
    if not task:
        return

    _update_sync_task(task_id, status="running", note="后台同步执行中", error=None)
    try:
        job_ids = {int(job_id) for job_id in task.get("job_ids", []) if isinstance(job_id, int)}
        items = _run_sync_for_job_ids(job_ids=job_ids, provider=str(task.get("provider") or "all"), dry_run=bool(task.get("dry_run", False)))
        _update_sync_task(
            task_id,
            status="completed",
            note="后台同步已完成",
            items=[item.model_dump() for item in items],
            error=None,
        )
    except Exception as exc:
        _update_sync_task(
            task_id,
            status="failed",
            note="后台同步失败",
            error=str(exc),
        )


def _build_artifact_inventory() -> ArtifactInventoryResponse:
    items: list[ArtifactInventoryItemResponse] = []
    seen: set[str] = set()

    def push(item: ArtifactInventoryItemResponse) -> None:
        if item.key in seen:
            return
        seen.add(item.key)
        items.append(item)

    def file_meta_from_path(file_path: Path | None) -> tuple[str | None, int | None]:
        if file_path is None or not file_path.exists() or not file_path.is_file():
            return None, None
        return file_path.name, file_path.stat().st_size

    for job in store.list_jobs():
        for artifact in job.artifacts:
            if not artifact.path_hint:
                continue
            normalized = artifact.path_hint.replace("\\", "/")
            artifact_path = normalized if normalized.startswith("job_") else f"job_{job.id}/{normalized}"
            artifact_file = ARTIFACTS_DIR / artifact_path
            if not artifact_file.exists() or not artifact_file.is_file():
                continue
            url = f"/artifacts/{artifact_path}"
            file_name, byte_size = file_meta_from_path(artifact_file)
            push(
                ArtifactInventoryItemResponse(
                    key=f"job-{job.id}-{url}",
                    url=url,
                    label=artifact.label,
                    file_name=file_name or Path(artifact_path).name,
                    kind=_get_artifact_kind(url),
                    source="job",
                    source_label=f"{job.capability_id} #{job.id}",
                    path_hint=artifact_path,
                    byte_size=byte_size,
                    updated_at=job.updated_at.isoformat(),
                    status=job.status,
                )
            )

    for pack in list_adaptation_packs():
        try:
            latest = get_latest_pack_result(pack.pack_name)
        except FileNotFoundError:
            continue
        latest_updated_at = latest.get("updated_at")
        latest_status = latest.get("validation_status") or latest.get("status")
        for url, label in [
            (latest.get("artifact_summary_url"), "结果摘要"),
            (latest.get("artifact_validation_url"), "校验报告"),
            (latest.get("artifact_snapshot_url"), "运行快照"),
            (latest.get("pack_summary_url"), "适配包摘要"),
            (latest.get("pack_validation_url"), "适配包校验"),
            (latest.get("shared_summary_url"), "共享摘要"),
            (latest.get("shared_validation_url"), "共享校验"),
        ]:
            if not url:
                continue
            file_name = Path(str(url)).name
            push(
                ArtifactInventoryItemResponse(
                    key=f"pack-{pack.pack_name}-{url}-{label}",
                    url=url,
                    label=label,
                    file_name=file_name,
                    kind=_get_artifact_kind(url),
                    source="pack",
                    source_label=pack.pack_name,
                    updated_at=latest_updated_at,
                    status=latest_status,
                )
            )

    items.sort(key=lambda item: item.updated_at or "", reverse=True)
    return ArtifactInventoryResponse(items=items)


def _build_job_summary() -> JobSummaryResponse:
    jobs = store.list_jobs()
    totals = {
        "total": len(jobs),
        "running": sum(1 for job in jobs if job.status == "running"),
        "failed": sum(1 for job in jobs if job.status == "failed"),
        "completed": sum(1 for job in jobs if job.status == "completed"),
    }
    status_counts: dict[str, int] = {}
    capability_counts: dict[str, int] = {}
    for job in jobs:
        status_counts[job.status] = status_counts.get(job.status, 0) + 1
        capability_counts[job.capability_id] = capability_counts.get(job.capability_id, 0) + 1

    return JobSummaryResponse(
        totals=totals,
        by_status=[
            JobSummaryBucketResponse(key=key, label=key, count=count)
            for key, count in sorted(status_counts.items(), key=lambda item: item[0])
        ],
        by_capability=[
            JobSummaryBucketResponse(key=key, label=key, count=count)
            for key, count in sorted(capability_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
    )


@app.get("/")
def root():
    if (WEB_DIST_DIR / "index.html").exists():
        return FileResponse(WEB_DIST_DIR / "index.html")
    if (LEGACY_FRONTEND_DIR / "index.html").exists():
        return FileResponse(LEGACY_FRONTEND_DIR / "index.html")
    return {
        "service": "ai-manga-factory-api",
        "status": "ok",
        "frontend": "build web app under web/ to enable the new separated frontend",
    }


@app.get("/legacy")
def legacy_console():
    if not (LEGACY_FRONTEND_DIR / "index.html").exists():
        raise HTTPException(status_code=404, detail="Legacy frontend not found")
    return FileResponse(LEGACY_FRONTEND_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/artifacts/{artifact_path:path}")
def get_artifact(artifact_path: str, request: Request, raw: int = 0):
    artifact_file = _resolve_artifact_file(artifact_path)
    if raw:
        return FileResponse(artifact_file)

    if _should_redirect_artifact_to_app(request):
        artifact_url = f"/artifacts/{artifact_path}"
        redirect_url = (
            f"/?page=artifact&artifact={quote(artifact_url, safe='/')}"
            f"&artifactLabel={quote(artifact_file.name)}"
        )
        return RedirectResponse(url=redirect_url, status_code=307)

    return FileResponse(artifact_file)


@app.get("/capabilities")
def list_capabilities():
    return {"items": registry.list_capabilities()}


@app.get("/provider-usage", response_model=ProviderUsageResponse)
def get_provider_usage():
    return usage_manager.get_provider_usage_snapshot(provider="ark")


@app.get("/runtime-storage")
def get_runtime_storage():
    return RUNTIME_STORAGE_PLAN.to_dict()


@app.get("/cloud-sync-overview", response_model=CloudSyncOverviewResponse)
def get_cloud_sync_overview():
    return _build_cloud_sync_overview()


@app.get("/cloud-sync-tasks", response_model=CloudSyncTaskListResponse)
def get_cloud_sync_tasks():
    return CloudSyncTaskListResponse(items=[_serialize_sync_task(item) for item in _list_sync_tasks()])


@app.get("/model-stage-plan", response_model=StageModelPlanResponse)
def get_model_stage_plan():
    path = REFERENCE_DATA_DIR / "model_stage_plan.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Model stage plan not found")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/projects", response_model=list[ProjectResponse])
def list_projects():
    return store.list_projects()


@app.get("/ui-preferences", response_model=UiPreferencesResponse)
def get_ui_preferences():
    return store.get_ui_preferences()


@app.put("/ui-preferences", response_model=UiPreferencesResponse)
def update_ui_preferences(payload: UiPreferencesUpdate):
    return store.update_ui_preferences(density_mode=payload.density_mode)


@app.post("/projects", response_model=ProjectResponse)
def create_project(payload: ProjectCreate):
    try:
        return store.create_project(name=payload.name, description=payload.description)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/jobs", response_model=JobListResponse)
def list_jobs():
    return JobListResponse(items=store.list_jobs())


@app.get("/jobs/summary", response_model=JobSummaryResponse)
def get_job_summary():
    return _build_job_summary()


@app.get("/artifacts-index", response_model=ArtifactInventoryResponse)
def get_artifacts_index():
    return _build_artifact_inventory()


@app.get("/artifact-sync-status", response_model=ArtifactSyncStatusResponse)
def get_artifact_sync_status(artifact: str):
    if not artifact.strip():
        raise HTTPException(status_code=400, detail="Artifact url is required")
    return _build_artifact_sync_status(artifact_url=artifact)


@app.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: int):
    try:
        return store.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/jobs/{job_id}/sync-status", response_model=JobSyncStatusResponse)
def get_job_sync_status(job_id: int):
    try:
        store.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _build_job_sync_status(job_id)


@app.post("/jobs/{job_id}/sync-storage", response_model=JobSyncTriggerResponse)
def sync_job_storage(job_id: int, payload: JobSyncTriggerRequest, background_tasks: BackgroundTasks):
    try:
        job = store.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if job.status == "running":
        raise HTTPException(status_code=400, detail="Running jobs cannot be synced yet")

    try:
        if not payload.dry_run:
            providers = ["quark_pan", "aliyundrive"] if payload.provider == "all" else [payload.provider]
            task = _enqueue_sync_task(scope="job", job_ids=[job_id], provider=payload.provider, dry_run=False)
            background_tasks.add_task(_execute_sync_task, task["id"])
            return JobSyncTriggerResponse(
                job_id=job_id,
                items=[
                    JobSyncTriggerItemResponse(
                        provider=current_provider,
                        dry_run=False,
                        note="已加入后台同步，稍后刷新查看结果",
                    )
                    for current_provider in providers
                ],
            )
        return _trigger_job_sync(job_id=job_id, provider=payload.provider, dry_run=payload.dry_run)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/retry", response_model=JobResponse)
def retry_job(job_id: int, background_tasks: BackgroundTasks):
    try:
        original_job = store.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if original_job.status == "running":
        raise HTTPException(status_code=400, detail="Running jobs cannot be retried")

    payload = JobCreate(
        capability_id=original_job.capability_id,
        project_id=original_job.project_id,
        input=original_job.input,
    )
    try:
        return _create_job_record(payload=payload, background_tasks=background_tasks)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/jobs/batch-retry", response_model=BatchRetryResponse)
def batch_retry_jobs(payload: BatchRetryRequest, background_tasks: BackgroundTasks):
    created_items: list[JobResponse] = []
    for job_id in payload.job_ids:
        try:
            original_job = store.get_job(job_id)
        except KeyError:
            continue
        if original_job.status == "running":
            continue
        job_payload = JobCreate(
            capability_id=original_job.capability_id,
            project_id=original_job.project_id,
            input=original_job.input,
        )
        created_items.append(_create_job_record(payload=job_payload, background_tasks=background_tasks))

    return BatchRetryResponse(
        requested=len(payload.job_ids),
        created=len(created_items),
        items=created_items,
    )


@app.post("/jobs/batch-sync-storage", response_model=BatchSyncStorageResponse)
def batch_sync_jobs_storage(payload: BatchSyncStorageRequest, background_tasks: BackgroundTasks):
    existing_jobs: list[int] = []
    for job_id in payload.job_ids:
        try:
            job = store.get_job(job_id)
        except KeyError:
            continue
        if job.status == "running":
            continue
        existing_jobs.append(job_id)

    if not existing_jobs:
        raise HTTPException(status_code=400, detail="No eligible jobs to sync")

    try:
        if not payload.dry_run:
            providers = ["quark_pan", "aliyundrive"] if payload.provider == "all" else [payload.provider]
            task = _enqueue_sync_task(scope="batch", job_ids=existing_jobs, provider=payload.provider, dry_run=False)
            background_tasks.add_task(_execute_sync_task, task["id"])
            return BatchSyncStorageResponse(
                job_ids=existing_jobs,
                items=[
                    JobSyncTriggerItemResponse(
                        provider=current_provider,
                        dry_run=False,
                        note="已加入后台同步，稍后刷新查看结果",
                    )
                    for current_provider in providers
                ],
            )
        return _trigger_batch_job_sync(job_ids=existing_jobs, provider=payload.provider, dry_run=payload.dry_run)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/cloud-sync-tasks/{task_id}/retry", response_model=CloudSyncTaskResponse)
def retry_cloud_sync_task(task_id: str, background_tasks: BackgroundTasks):
    task = next((item for item in _list_sync_tasks() if str(item.get("id")) == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Sync task not found")

    retry_task = _enqueue_sync_task(
        scope=str(task.get("scope") or "job"),
        job_ids=[int(job_id) for job_id in task.get("job_ids", []) if isinstance(job_id, int)],
        provider=str(task.get("provider") or "all"),
        dry_run=False,
    )
    background_tasks.add_task(_execute_sync_task, retry_task["id"])
    return _serialize_sync_task(retry_task)


def _create_job_record(payload: JobCreate, background_tasks: BackgroundTasks) -> JobResponse:
    try:
        module = registry.get(payload.capability_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if payload.project_id is not None:
        try:
            project = store.get_project(payload.project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    else:
        project_name = payload.project_name or f"{payload.capability_id}-workspace"
        project = store.get_or_create_project(project_name)

    planned = module.plan_job(payload.input)
    job = store.create_job(
        project_id=project.id,
        capability_id=payload.capability_id,
        status="planned",
        input_payload=payload.input,
        workflow=planned.workflow,
        artifacts=planned.artifacts,
        summary=planned.summary,
    )
    background_tasks.add_task(executor.execute, job.id)
    return job


@app.post("/jobs", response_model=JobResponse)
def create_job(payload: JobCreate, background_tasks: BackgroundTasks):
    try:
        return _create_job_record(payload=payload, background_tasks=background_tasks)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/adaptation-packs", response_model=list[AdaptationPackResponse])
def get_adaptation_packs():
    packs = list_adaptation_packs()
    return [
        AdaptationPackResponse(
            pack_name=pack.pack_name,
            source_title=pack.source_title,
            chapter_range=pack.chapter_range,
            chapter_count=len(pack.chapter_briefs),
            default_project_name=pack.default_project_name,
            default_scene_count=pack.default_scene_count,
        )
        for pack in packs
    ]


@app.get("/adaptation-packs/{pack_name}/latest-result", response_model=AdaptationPackLatestResultResponse)
def get_adaptation_pack_latest_result(pack_name: str):
    try:
        get_adaptation_pack(pack_name)
        return get_latest_pack_result(pack_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/adaptation-packs/{pack_name}/jobs", response_model=JobResponse)
def create_adaptation_job(pack_name: str, payload: AdaptationJobRequest, background_tasks: BackgroundTasks):
    try:
        pack = get_adaptation_pack(pack_name)
        job_payload = build_adaptation_job_payload(
            pack=pack,
            project_name=payload.project_name,
            scene_count=payload.scene_count,
            target_duration_seconds=payload.target_duration_seconds,
            chapter_keyframe_count=payload.chapter_keyframe_count,
            chapter_shot_count=payload.chapter_shot_count,
            use_model_storyboard=payload.use_model_storyboard,
            use_real_images=payload.use_real_images,
            image_model=payload.image_model,
            video_model=payload.video_model,
            chapter_start=payload.chapter_start,
            chapter_end=payload.chapter_end,
        )
        return _create_job_record(payload=job_payload, background_tasks=background_tasks)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/adaptation-packs/{pack_name}/batches", response_model=AdaptationBatchResponse)
def create_adaptation_batches(pack_name: str, payload: AdaptationBatchRequest, background_tasks: BackgroundTasks):
    try:
        pack = get_adaptation_pack(pack_name)
        items: list[BatchJobResponse] = []
        job_batches = build_batch_job_payloads(
            pack=pack,
            project_name=payload.project_name,
            batch_size=payload.batch_size,
            scene_count=payload.scene_count,
            target_duration_seconds=payload.target_duration_seconds,
            chapter_keyframe_count=payload.chapter_keyframe_count,
            chapter_shot_count=payload.chapter_shot_count,
            use_model_storyboard=payload.use_model_storyboard,
            use_real_images=payload.use_real_images,
            image_model=payload.image_model,
            video_model=payload.video_model,
        )
        for item in job_batches:
            job = _create_job_record(payload=item["job_payload"], background_tasks=background_tasks)
            items.append(
                BatchJobResponse(
                    job_id=job.id,
                    chapter_range=item["chapter_range"],
                    chapter_count=item["chapter_count"],
                    status=job.status,
                )
            )
        project_name = payload.project_name or pack.default_project_name
        return AdaptationBatchResponse(
            pack_name=pack.pack_name,
            source_title=pack.source_title,
            project_name=project_name,
            total_batches=len(items),
            items=items,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
