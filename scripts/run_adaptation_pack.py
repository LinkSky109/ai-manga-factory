#!/usr/bin/env python3
"""根据适配包执行一次漫剧任务。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.adaptation_packs import build_adaptation_job_payload, get_adaptation_pack
from backend.config import ARTIFACTS_DIR
from backend.executor import JobExecutor
from backend.storage import PlatformStore
from modules.registry import CapabilityRegistry
from shared.providers.ark import ArkProvider


def write_stage_report(
    report_path: Path,
    *,
    source_title: str,
    project_name: str,
    job_id: int,
    chapter_range: str,
    scene_count: int,
    summary: str,
    artifacts: list[str],
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 阶段产出报告",
        "",
        f"- 原作：{source_title}",
        f"- 项目名：{project_name}",
        f"- Job ID：{job_id}",
        f"- 章节范围：{chapter_range}",
        f"- 分镜图数量：{scene_count}",
        "",
        "## 执行摘要",
        summary,
        "",
        "## 产物路径",
        *[f"- {artifact}" for artifact in artifacts],
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="运行一个小说适配包。")
    parser.add_argument("--pack-name", required=True)
    parser.add_argument("--project-name", default=None)
    parser.add_argument("--scene-count", type=int, default=None)
    parser.add_argument("--chapter-keyframe-count", type=int, default=4)
    parser.add_argument("--chapter-shot-count", type=int, default=10)
    parser.add_argument("--use-model-storyboard", action="store_true")
    parser.add_argument("--chapter-start", type=int, default=None)
    parser.add_argument("--chapter-end", type=int, default=None)
    parser.add_argument("--real-images", action="store_true")
    parser.add_argument("--image-model", default=ArkProvider.DEFAULT_IMAGE_MODEL)
    parser.add_argument("--video-model", default=ArkProvider.DEFAULT_VIDEO_MODEL)
    args = parser.parse_args()

    pack = get_adaptation_pack(args.pack_name)
    scene_count = args.scene_count or pack.default_scene_count
    job_payload = build_adaptation_job_payload(
        pack=pack,
        project_name=args.project_name,
        scene_count=scene_count,
        chapter_keyframe_count=args.chapter_keyframe_count,
        chapter_shot_count=args.chapter_shot_count,
        use_model_storyboard=args.use_model_storyboard,
        use_real_images=args.real_images,
        image_model=args.image_model,
        video_model=args.video_model,
        chapter_start=args.chapter_start,
        chapter_end=args.chapter_end,
    )

    store = PlatformStore()
    registry = CapabilityRegistry()
    executor = JobExecutor(store=store, registry=registry)
    module = registry.get("manga")
    project = store.get_or_create_project(job_payload.project_name or pack.default_project_name)
    planned = module.plan_job(job_payload.input)
    job = store.create_job(
        project_id=project.id,
        capability_id="manga",
        status="planned",
        input_payload=job_payload.input,
        workflow=planned.workflow,
        artifacts=planned.artifacts,
        summary=planned.summary,
    )
    executor.execute(job.id)
    final_job = store.get_job(job.id)

    artifact_paths = [
        str((ARTIFACTS_DIR / item.path_hint).resolve()) if item.path_hint else "(无路径)"
        for item in final_job.artifacts
    ]
    report_path = pack.root_dir / "reports" / "stage_report.md"
    write_stage_report(
        report_path,
        source_title=pack.source_title,
        project_name=project.name,
        job_id=final_job.id,
        chapter_range=str(final_job.input.get("chapter_range", pack.chapter_range)),
        scene_count=scene_count,
        summary=final_job.summary,
        artifacts=artifact_paths,
    )

    print(f"任务已完成：{final_job.id}")
    print(f"任务状态：{final_job.status}")
    print(f"阶段报告：{report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
