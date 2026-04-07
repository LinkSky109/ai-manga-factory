#!/usr/bin/env python3
"""为已完成任务重新生成校验文件和结果摘要。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import ARTIFACTS_DIR
from backend.storage import PlatformStore
from shared.result_depository import record_job_result


def pick_target_job(store: PlatformStore, job_id: int | None, pack_name: str | None, project_name: str | None):
    if job_id is not None:
        return store.get_job(job_id)

    jobs = [job for job in store.list_jobs() if job.capability_id == "manga"]
    if pack_name:
        jobs = [job for job in jobs if str(job.input.get("adaptation_pack", "")).strip() == pack_name]
    if project_name:
        project_ids = {project.id for project in store.list_projects() if project.name == project_name}
        jobs = [job for job in jobs if job.project_id in project_ids]

    if jobs:
        return max(jobs, key=lambda item: item.id)
    raise RuntimeError("没有找到匹配的漫剧任务")


def main() -> int:
    parser = argparse.ArgumentParser(description="重新生成漫剧任务的校验文件。")
    parser.add_argument("--job-id", type=int, default=None)
    parser.add_argument("--pack-name", default=None)
    parser.add_argument("--project-name", default=None)
    args = parser.parse_args()

    store = PlatformStore()
    job = pick_target_job(store, args.job_id, args.pack_name, args.project_name)
    project = store.get_project(job.project_id)
    record_job_result(job, project.name)

    snapshot_path = ARTIFACTS_DIR / f"job_{job.id}" / "result_snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    print(f"校验报告：{ARTIFACTS_DIR / f'job_{job.id}' / 'validation_report.md'}")
    print(f"沉淀摘要：{ARTIFACTS_DIR / f'job_{job.id}' / 'result_summary.md'}")
    print(f"结果：{snapshot['validation']['status']}")
    return 0 if snapshot["validation"]["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
