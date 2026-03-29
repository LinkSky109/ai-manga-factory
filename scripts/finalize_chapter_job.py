#!/usr/bin/env python3
"""替换返工章节并重建章节工厂整包交付。"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import ADAPTATIONS_DIR, ARTIFACTS_DIR
from backend.schemas import ArtifactPreview, WorkflowStep
from backend.storage import PlatformStore
from shared.adaptation_quality import build_quality_markdown
from shared.result_depository import record_job_result
from shared.storyboard_reference import load_storyboard_profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="替换返工章节并重建章节工厂整包交付。")
    parser.add_argument("--job-id", type=int, required=True)
    parser.add_argument(
        "--replace-chapter",
        action="append",
        default=[],
        help="格式：章节号=来源任务号，例如 13=13 表示用 job_13 的 chapter_13 替换目标任务中的 chapter_13。",
    )
    return parser.parse_args()


def parse_replacements(items: list[str]) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for item in items:
        chapter_text, job_text = item.split("=", 1)
        mapping[int(chapter_text)] = int(job_text)
    return mapping


def chapter_dir(job_dir: Path, chapter_no: int) -> Path:
    return job_dir / "chapters" / f"chapter_{chapter_no:02d}"


def replace_chapter(target_job_dir: Path, chapter_no: int, source_job_dir: Path) -> None:
    src = chapter_dir(source_job_dir, chapter_no)
    dst = chapter_dir(target_job_dir, chapter_no)
    if not src.exists():
        raise FileNotFoundError(f"来源章节不存在：{src}")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def load_chapter_package(target_job_dir: Path, chapter_no: int) -> dict:
    current_dir = chapter_dir(target_job_dir, chapter_no)
    storyboard_path = current_dir / "storyboard" / "storyboard.json"
    qa_snapshot_path = current_dir / "qa" / "qa_snapshot.json"
    storyboard_payload = json.loads(storyboard_path.read_text(encoding="utf-8"))
    qa_payload = json.loads(qa_snapshot_path.read_text(encoding="utf-8"))
    artifact_paths = [
        str(path.relative_to(ARTIFACTS_DIR)).replace("\\", "/")
        for path in sorted(current_dir.rglob("*"))
        if path.is_file()
    ]
    return {
        "chapter": chapter_no,
        "title": storyboard_payload["title"],
        "storyboard": storyboard_payload,
        "artifact_paths": artifact_paths,
        "preview_video": str(current_dir / "preview" / "chapter_preview.mp4"),
        "delivery_video": str(current_dir / "delivery" / "chapter_final_cut.mp4"),
        "image_prompts": [],
        "qa": qa_payload["final"],
    }


def concat_videos(video_paths: list[Path], output_path: Path) -> None:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    concat_file = output_path.with_suffix(".txt")
    concat_file.write_text("\n".join(f"file '{path.as_posix()}'" for path in video_paths), encoding="utf-8")
    command = [ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(output_path)]
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    concat_file.unlink(missing_ok=True)


def build_preview_html(source_title: str, chapter_packages: list[dict]) -> str:
    cards = []
    for item in chapter_packages:
        chapter = item["chapter"]
        cards.append(
            f"<li><a href=\"../chapters/chapter_{chapter:02d}/preview/index.html\">第{chapter:02d}章：{item['title']}</a> | "
            f"<a href=\"../chapters/chapter_{chapter:02d}/delivery/chapter_final_cut.mp4\">交付视频</a></li>"
        )
    return (
        f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>{source_title} 漫剧预览</title></head>'
        f'<body><h1>{source_title}</h1><video src="preview.mp4" controls style="width:100%;max-width:1080px"></video>'
        f"<h2>章节交付</h2><ol>{''.join(cards)}</ol></body></html>"
    )


def build_qa_overview(chapter_packages: list[dict]) -> str:
    passed = sum(1 for item in chapter_packages if item["qa"]["passed"])
    lines = ["# QA 总览", "", f"- 章节通过：{passed}/{len(chapter_packages)}", ""]
    lines.extend([f"- 第{item['chapter']:02d}章 {item['title']}：{item['qa']['summary']}" for item in chapter_packages])
    return "\n".join(lines)


def collect_storyboard_scenes(target_job_dir: Path, chapter_packages: list[dict]) -> None:
    storyboard_dir = target_job_dir / "storyboard"
    storyboard_dir.mkdir(parents=True, exist_ok=True)
    for path in storyboard_dir.glob("scene_*.png"):
        path.unlink(missing_ok=True)
    for index, item in enumerate(chapter_packages, start=1):
        source_image = chapter_dir(target_job_dir, item["chapter"]) / "images" / "keyframe_01.png"
        if source_image.exists():
            shutil.copyfile(source_image, storyboard_dir / f"scene_{index:02d}.png")


def build_prompts_payload(chapter_packages: list[dict], replacements: dict[int, int]) -> dict:
    provider_notes = [f"章节 {chapter:02d} 使用 job_{job_id} 的返工结果重建整包。" for chapter, job_id in sorted(replacements.items())]
    return {
        "quality_constitution": build_quality_markdown(),
        "storyboard_profile": load_storyboard_profile(),
        "chapter_prompt_overview": [
            {"chapter": item["chapter"], "title": item["title"], "image_prompts": item.get("image_prompts", [])}
            for item in chapter_packages
        ],
        "provider_notes": provider_notes,
    }


def build_artifacts(target_job_dir: Path, chapter_packages: list[dict]) -> list[ArtifactPreview]:
    artifacts = [
        ArtifactPreview(artifact_type="markdown", label="题材研究", path_hint=str((target_job_dir / "research.md").relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
        ArtifactPreview(artifact_type="markdown", label="章节脚本", path_hint=str((target_job_dir / "screenplay.md").relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
        ArtifactPreview(artifact_type="markdown", label="美术设定", path_hint=str((target_job_dir / "art_direction.md").relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
        ArtifactPreview(artifact_type="json", label="提示词包", path_hint=str((target_job_dir / "prompts.json").relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
        ArtifactPreview(artifact_type="json", label="总分镜 JSON", path_hint=str((target_job_dir / "storyboard" / "storyboard.json").relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
        ArtifactPreview(artifact_type="json", label="章节索引", path_hint=str((target_job_dir / "chapters_index.json").relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
        ArtifactPreview(artifact_type="markdown", label="QA 总览", path_hint=str((target_job_dir / "qa_overview.md").relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
        ArtifactPreview(artifact_type="image", label="主角立绘", path_hint=str((target_job_dir / "characters" / "lead_character.png").relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
        ArtifactPreview(artifact_type="html", label="预览页面", path_hint=str((target_job_dir / "preview" / "index.html").relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
        ArtifactPreview(artifact_type="video", label="预览视频", path_hint=str((target_job_dir / "preview" / "preview.mp4").relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
        ArtifactPreview(artifact_type="video", label="交付视频", path_hint=str((target_job_dir / "delivery" / "final_cut.mp4").relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
    ]
    for item in chapter_packages:
        chapter = item["chapter"]
        artifacts.extend(
            [
                ArtifactPreview(artifact_type="video", label=f"第{chapter:02d}章预览视频", path_hint=str((chapter_dir(target_job_dir, chapter) / "preview" / "chapter_preview.mp4").relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
                ArtifactPreview(artifact_type="video", label=f"第{chapter:02d}章交付视频", path_hint=str((chapter_dir(target_job_dir, chapter) / "delivery" / "chapter_final_cut.mp4").relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
                ArtifactPreview(artifact_type="markdown", label=f"第{chapter:02d}章 QA 报告", path_hint=str((chapter_dir(target_job_dir, chapter) / "qa" / "qa_report.md").relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
            ]
        )
    return artifacts


def mark_workflow_completed(workflow: list[WorkflowStep]) -> list[WorkflowStep]:
    updated: list[WorkflowStep] = []
    for step in workflow:
        payload = step.model_dump()
        payload["status"] = "completed"
        if not payload.get("details"):
            payload["details"] = "章节返工替换后已完成整包重建。"
        updated.append(WorkflowStep(**payload))
    return updated


def main() -> int:
    args = parse_args()
    replacements = parse_replacements(args.replace_chapter)
    store = PlatformStore()
    job = store.get_job(args.job_id)
    project = store.get_project(job.project_id)
    target_job_dir = ARTIFACTS_DIR / f"job_{job.id}"

    for chapter_no, source_job_id in sorted(replacements.items()):
        replace_chapter(target_job_dir, chapter_no, ARTIFACTS_DIR / f"job_{source_job_id}")

    chapter_dirs = sorted(path for path in (target_job_dir / "chapters").glob("chapter_*") if path.is_dir())
    chapter_numbers = [int(path.name.split("_")[1]) for path in chapter_dirs]
    chapter_packages = [load_chapter_package(target_job_dir, chapter_no) for chapter_no in chapter_numbers]

    source_title = str(job.input.get("source_title", "Untitled")).strip() or "Untitled"
    chapter_range = str(job.input.get("chapter_range", "TBD")).strip() or "TBD"
    storyboard_payload = {
        "source_title": source_title,
        "chapter_range": chapter_range,
        "episode_count": len(chapter_packages),
        "quality_constitution": build_quality_markdown(),
        "storyboard_profile": load_storyboard_profile(),
        "chapters": [item["storyboard"] for item in chapter_packages],
    }
    (target_job_dir / "storyboard").mkdir(parents=True, exist_ok=True)
    (target_job_dir / "storyboard" / "storyboard.json").write_text(json.dumps(storyboard_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    collect_storyboard_scenes(target_job_dir, chapter_packages)

    (target_job_dir / "chapters_index.json").write_text(json.dumps(chapter_packages, ensure_ascii=False, indent=2), encoding="utf-8")
    (target_job_dir / "qa_overview.md").write_text(build_qa_overview(chapter_packages), encoding="utf-8")
    (target_job_dir / "prompts.json").write_text(json.dumps(build_prompts_payload(chapter_packages, replacements), ensure_ascii=False, indent=2), encoding="utf-8")

    preview_videos = [Path(item["preview_video"]) for item in chapter_packages]
    final_videos = [Path(item["delivery_video"]) for item in chapter_packages]
    concat_videos(preview_videos, target_job_dir / "preview" / "preview.mp4")
    concat_videos(final_videos, target_job_dir / "delivery" / "final_cut.mp4")
    (target_job_dir / "preview" / "index.html").write_text(build_preview_html(source_title, chapter_packages), encoding="utf-8")

    manifest_artifacts: list[str] = []
    for item in chapter_packages:
        manifest_artifacts.extend(item["artifact_paths"])
    manifest_payload = {
        "job_id": job.id,
        "project_id": job.project_id,
        "capability": "manga",
        "chapter_count": len(chapter_packages),
        "chapter_keyframe_count": int(job.input.get("chapter_keyframe_count", 0) or 0),
        "chapter_shot_count": int(job.input.get("chapter_shot_count", 0) or 0),
        "artifacts": sorted(set(manifest_artifacts)),
    }
    (target_job_dir / "manifest.json").write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    real_image_count = sum(1 for path in target_job_dir.glob("chapters/chapter_*/images/keyframe_*.png"))
    output_video_count = len(chapter_packages) * 2 + 2
    summary = (
        f"已按章节工厂模式完成《{source_title}》{chapter_range} 的漫剧交付，共 {len(chapter_packages)} 章。"
        f"每章均输出分镜 JSON/CSV/XLSX、音频方案、章节预览视频、章节交付视频与 QA 报告。"
        f"真图数量 {real_image_count}，输出视频数量 {output_video_count}。"
    )
    if replacements:
        summary += " 已用返工章节结果重建整包交付。"

    artifacts = build_artifacts(target_job_dir, chapter_packages)
    workflow = mark_workflow_completed(job.workflow)
    updated_job = store.update_job(job.id, "completed", workflow, artifacts, summary, None)
    record_job_result(updated_job, project.name)

    print(f"重建完成：job_{job.id}")
    print(f"章节数：{len(chapter_packages)}")
    print(f"替换章节：{json.dumps(replacements, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
