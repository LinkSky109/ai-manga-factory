from __future__ import annotations

import json
import re
from typing import Any
from pathlib import Path

from backend.config import ADAPTATIONS_DIR, ARTIFACTS_DIR
from backend.schemas import ArtifactPreview, JobResponse


LATEST_POINTER_NAME = "latest_result_pointer.json"


def record_job_result(job: JobResponse, project_name: str) -> list[ArtifactPreview]:
    job_dir = ARTIFACTS_DIR / f"job_{job.id}"
    job_dir.mkdir(parents=True, exist_ok=True)

    checks = _collect_checks(job=job, job_dir=job_dir)
    passed = sum(1 for _, _, ok in checks if ok)
    total = len(checks)
    validation_status = "PASS" if job.status == "completed" and total > 0 and passed == total else "FAIL"

    summary_path = job_dir / "result_summary.md"
    snapshot_path = job_dir / "result_snapshot.json"
    validation_path = job_dir / "validation_report.md"

    artifact_paths = [item.path_hint for item in job.artifacts if item.path_hint]
    summary_text = _build_summary_markdown(
        job=job,
        project_name=project_name,
        validation_status=validation_status,
        passed=passed,
        total=total,
        artifact_paths=artifact_paths,
    )
    validation_text = _build_validation_markdown(job=job, validation_status=validation_status, passed=passed, total=total, checks=checks)
    snapshot_payload = {
        "job_id": job.id,
        "project_name": project_name,
        "capability_id": job.capability_id,
        "status": job.status,
        "source_title": str(job.input.get("source_title", "")),
        "chapter_range": str(job.input.get("chapter_range", "")),
        "adaptation_pack": str(job.input.get("adaptation_pack", "")),
        "summary": job.summary,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "validation": {
            "status": validation_status,
            "passed": passed,
            "total": total,
            "missing": [path for _, path, ok in checks if not ok],
        },
        "artifacts": artifact_paths,
    }

    summary_path.write_text(summary_text, encoding="utf-8")
    validation_path.write_text(validation_text, encoding="utf-8")
    snapshot_path.write_text(json.dumps(snapshot_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    _write_pack_reports(
        job=job,
        project_name=project_name,
        validation_status=validation_status,
        passed=passed,
        total=total,
        summary_text=summary_text,
        validation_text=validation_text,
    )

    return [
        ArtifactPreview(
            artifact_type="markdown",
            label="结果摘要",
            path_hint=_artifact_hint(summary_path),
        ),
        ArtifactPreview(
            artifact_type="markdown",
            label="校验报告",
            path_hint=_artifact_hint(validation_path),
        ),
        ArtifactPreview(
            artifact_type="json",
            label="结果快照",
            path_hint=_artifact_hint(snapshot_path),
        ),
    ]


def _collect_checks(job: JobResponse, job_dir: Path) -> list[tuple[str, str, bool]]:
    if job.capability_id == "manga":
        chapter_numbers = _resolve_chapter_numbers(job.input)
        paths = [
            ("research.md", job_dir / "research.md"),
            ("screenplay.md", job_dir / "screenplay.md"),
            ("art_direction.md", job_dir / "art_direction.md"),
            ("prompts.json", job_dir / "prompts.json"),
            ("manifest.json", job_dir / "manifest.json"),
            ("chapters_index.json", job_dir / "chapters_index.json"),
            ("qa_overview.md", job_dir / "qa_overview.md"),
            ("characters/lead_character.png", job_dir / "characters" / "lead_character.png"),
            ("storyboard/storyboard.json", job_dir / "storyboard" / "storyboard.json"),
            ("preview/index.html", job_dir / "preview" / "index.html"),
            ("preview/preview.mp4", job_dir / "preview" / "preview.mp4"),
            ("delivery/final_cut.mp4", job_dir / "delivery" / "final_cut.mp4"),
        ]
        for chapter_no in chapter_numbers:
            chapter_dir = job_dir / "chapters" / f"chapter_{chapter_no:02d}"
            paths.extend(
                [
                    (f"chapters/chapter_{chapter_no:02d}/storyboard/storyboard.json", chapter_dir / "storyboard" / "storyboard.json"),
                    (f"chapters/chapter_{chapter_no:02d}/storyboard/storyboard.csv", chapter_dir / "storyboard" / "storyboard.csv"),
                    (f"chapters/chapter_{chapter_no:02d}/storyboard/storyboard.xlsx", chapter_dir / "storyboard" / "storyboard.xlsx"),
                    (f"chapters/chapter_{chapter_no:02d}/video/video_plan.json", chapter_dir / "video" / "video_plan.json"),
                    (f"chapters/chapter_{chapter_no:02d}/audio/audio_plan.json", chapter_dir / "audio" / "audio_plan.json"),
                    (f"chapters/chapter_{chapter_no:02d}/audio/narration_script.txt", chapter_dir / "audio" / "narration_script.txt"),
                    (f"chapters/chapter_{chapter_no:02d}/audio/voice_script.txt", chapter_dir / "audio" / "voice_script.txt"),
                    (f"chapters/chapter_{chapter_no:02d}/audio/voiceover.mp3", chapter_dir / "audio" / "voiceover.mp3"),
                    (f"chapters/chapter_{chapter_no:02d}/audio/ambience.wav", chapter_dir / "audio" / "ambience.wav"),
                    (f"chapters/chapter_{chapter_no:02d}/preview/index.html", chapter_dir / "preview" / "index.html"),
                    (f"chapters/chapter_{chapter_no:02d}/preview/chapter_preview.mp4", chapter_dir / "preview" / "chapter_preview.mp4"),
                    (f"chapters/chapter_{chapter_no:02d}/delivery/chapter_final_cut.mp4", chapter_dir / "delivery" / "chapter_final_cut.mp4"),
                    (f"chapters/chapter_{chapter_no:02d}/qa/qa_report.md", chapter_dir / "qa" / "qa_report.md"),
                    (f"chapters/chapter_{chapter_no:02d}/qa/qa_snapshot.json", chapter_dir / "qa" / "qa_snapshot.json"),
                ]
            )
        scene_dir = job_dir / "storyboard"
        for path in sorted(scene_dir.glob("scene_*.png")):
            paths.append((path.relative_to(job_dir).as_posix(), path))
        checks = [(label, path.as_posix(), path.exists()) for label, path in paths]
        for chapter_no in chapter_numbers:
            chapter_dir = job_dir / "chapters" / f"chapter_{chapter_no:02d}"
            checks.extend(_collect_manga_content_checks(chapter_dir=chapter_dir, chapter_no=chapter_no))
        return checks

    checks: list[tuple[str, str, bool]] = []
    for artifact in job.artifacts:
        if not artifact.path_hint:
            continue
        path = _resolve_artifact_path(job_dir=job_dir, path_hint=artifact.path_hint)
        checks.append((artifact.label, path.as_posix(), path.exists()))
    return checks


def _collect_manga_content_checks(*, chapter_dir: Path, chapter_no: int) -> list[tuple[str, str, bool]]:
    checks: list[tuple[str, str, bool]] = []
    storyboard_path = chapter_dir / "storyboard" / "storyboard.json"
    audio_plan_path = chapter_dir / "audio" / "audio_plan.json"
    meaningful_speakers: set[str] = set()
    if storyboard_path.exists():
        try:
            storyboard_payload = json.loads(storyboard_path.read_text(encoding="utf-8"))
            rows = storyboard_payload.get("rows") or []
            has_narration = any(str(row.get("旁白") or "").strip() not in {"", "-", "—", "null"} for row in rows if isinstance(row, dict))
            has_dialogue = any(str(row.get("对白") or "").strip() not in {"", "-", "—", "null"} for row in rows if isinstance(row, dict))
            has_audio_design = all(str(row.get("音频设计") or "").strip() not in {"", "null"} for row in rows if isinstance(row, dict))
            unique_speakers = {
                str(row.get("对白角色") or "").strip()
                for row in rows
                if isinstance(row, dict) and str(row.get("对白") or "").strip() not in {"", "-", "—", "null"}
            }
            meaningful_speakers = {speaker for speaker in unique_speakers if speaker and speaker not in {"旁白", "无", "—"}}
            no_scene_pollution = all(
                not re.search(r"第\d+章|第\d+组|\d+秒|scene|chapter", str(row.get("场景/时间") or ""), flags=re.IGNORECASE)
                for row in rows
                if isinstance(row, dict)
            )
            checks.extend(
                [
                    (f"chapter_{chapter_no:02d} storyboard narration populated", storyboard_path.as_posix(), has_narration),
                    (f"chapter_{chapter_no:02d} storyboard dialogue populated", storyboard_path.as_posix(), has_dialogue),
                    (f"chapter_{chapter_no:02d} storyboard dialogue speakers varied", storyboard_path.as_posix(), len(meaningful_speakers) >= 1),
                    (f"chapter_{chapter_no:02d} storyboard audio design populated", storyboard_path.as_posix(), has_audio_design),
                    (f"chapter_{chapter_no:02d} storyboard scene labels clean", storyboard_path.as_posix(), no_scene_pollution),
                ]
            )
        except Exception:
            checks.extend(
                [
                    (f"chapter_{chapter_no:02d} storyboard narration populated", storyboard_path.as_posix(), False),
                    (f"chapter_{chapter_no:02d} storyboard dialogue populated", storyboard_path.as_posix(), False),
                    (f"chapter_{chapter_no:02d} storyboard dialogue speakers varied", storyboard_path.as_posix(), False),
                    (f"chapter_{chapter_no:02d} storyboard audio design populated", storyboard_path.as_posix(), False),
                    (f"chapter_{chapter_no:02d} storyboard scene labels clean", storyboard_path.as_posix(), False),
                ]
            )

    if audio_plan_path.exists():
        try:
            audio_plan = json.loads(audio_plan_path.read_text(encoding="utf-8"))
            cue_sheet = audio_plan.get("cue_sheet") or []
            narration_tracks = audio_plan.get("narration_tracks") or []
            dialogue_tracks = audio_plan.get("dialogue_tracks") or []
            voice_script = str(audio_plan.get("voice_script") or "").strip()
            voice_script_has_narration = "旁白：" in voice_script
            voice_script_has_dialogue = any(f"{speaker}：" in voice_script for speaker in meaningful_speakers)
            checks.extend(
                [
                    (f"chapter_{chapter_no:02d} audio cue sheet populated", audio_plan_path.as_posix(), len(cue_sheet) > 0),
                    (f"chapter_{chapter_no:02d} audio narration tracks populated", audio_plan_path.as_posix(), len(narration_tracks) > 0),
                    (f"chapter_{chapter_no:02d} audio dialogue tracks populated", audio_plan_path.as_posix(), len(dialogue_tracks) > 0),
                    (f"chapter_{chapter_no:02d} audio voice script populated", audio_plan_path.as_posix(), bool(voice_script)),
                    (f"chapter_{chapter_no:02d} audio voice script has narration", audio_plan_path.as_posix(), voice_script_has_narration),
                    (f"chapter_{chapter_no:02d} audio voice script has character dialogue", audio_plan_path.as_posix(), voice_script_has_dialogue),
                ]
            )
        except Exception:
            checks.extend(
                [
                    (f"chapter_{chapter_no:02d} audio cue sheet populated", audio_plan_path.as_posix(), False),
                    (f"chapter_{chapter_no:02d} audio narration tracks populated", audio_plan_path.as_posix(), False),
                    (f"chapter_{chapter_no:02d} audio dialogue tracks populated", audio_plan_path.as_posix(), False),
                    (f"chapter_{chapter_no:02d} audio voice script populated", audio_plan_path.as_posix(), False),
                    (f"chapter_{chapter_no:02d} audio voice script has narration", audio_plan_path.as_posix(), False),
                    (f"chapter_{chapter_no:02d} audio voice script has character dialogue", audio_plan_path.as_posix(), False),
                ]
            )
    return checks


def _build_summary_markdown(
    *,
    job: JobResponse,
    project_name: str,
    validation_status: str,
    passed: int,
    total: int,
    artifact_paths: list[str],
) -> str:
    lines = [
        f"# Job {job.id} 结果沉淀",
        "",
        f"- 项目名: {project_name}",
        f"- 能力: {job.capability_id}",
        f"- 状态: {job.status}",
        f"- 适配包: {job.input.get('adaptation_pack', '未指定')}",
        f"- 原作: {job.input.get('source_title', '未指定')}",
        f"- 章节范围: {job.input.get('chapter_range', '未指定')}",
        f"- 创建时间: {job.created_at.isoformat()}",
        f"- 更新时间: {job.updated_at.isoformat()}",
        "",
        "## 执行摘要",
        job.summary or "无摘要。",
        "",
        "## 自动校验",
        f"- 结论: {validation_status}",
        f"- 通过: {passed}/{total}",
    ]
    if job.error:
        lines.extend(["", "## 错误信息", job.error])
    if artifact_paths:
        lines.extend(["", "## 关键产物", *[f"- {path}" for path in artifact_paths]])
    return "\n".join(lines) + "\n"


def _build_validation_markdown(
    *,
    job: JobResponse,
    validation_status: str,
    passed: int,
    total: int,
    checks: list[tuple[str, str, bool]],
) -> str:
    lines = [
        f"# Job {job.id} 自动校验报告",
        "",
        f"- 状态: {job.status}",
        f"- 校验结论: {validation_status}",
        f"- 通过: {passed}/{total}",
        "",
        "## 详情",
    ]
    for label, path, ok in checks:
        lines.append(f"- [{'PASS' if ok else 'FAIL'}] {label} -> {path}")
    return "\n".join(lines) + "\n"


def get_latest_pack_result(pack_name: str) -> dict[str, Any]:
    reports_dir = ADAPTATIONS_DIR / pack_name / "reports"
    if not reports_dir.exists():
        raise FileNotFoundError(f"Pack reports not found: {pack_name}")

    pointer_path = reports_dir / LATEST_POINTER_NAME
    if pointer_path.exists():
        payload = json.loads(pointer_path.read_text(encoding="utf-8-sig"))
        resolved_payload = _enrich_pack_result_payload(payload)
        if _payload_matches_current_files(resolved_payload):
            return resolved_payload

    latest_job_id = _find_latest_job_id(reports_dir)
    if latest_job_id is None:
        raise FileNotFoundError(f"No job reports found for pack: {pack_name}")

    rebuilt_payload = _build_pack_result_payload(
        pack_name=pack_name,
        job_id=latest_job_id,
        project_name=None,
        capability_id=None,
        status=None,
        created_at=None,
        updated_at=None,
        validation_status=None,
        passed=None,
        total=None,
        source="scan-fallback",
    )
    return _enrich_pack_result_payload(rebuilt_payload)


def _write_pack_reports(
    *,
    job: JobResponse,
    project_name: str,
    validation_status: str,
    passed: int,
    total: int,
    summary_text: str,
    validation_text: str,
) -> None:
    pack_name = str(job.input.get("adaptation_pack", "")).strip()
    if not pack_name:
        return

    reports_dir = ADAPTATIONS_DIR / pack_name / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    summary_copy = reports_dir / f"job_{job.id}_summary.md"
    validation_copy = reports_dir / f"job_{job.id}_validation.md"
    latest_path = reports_dir / "latest_result.md"
    latest_validation_path = reports_dir / "latest_validation.md"
    pointer_path = reports_dir / LATEST_POINTER_NAME
    journal_path = reports_dir / "result_journal.md"

    summary_copy.write_text(summary_text, encoding="utf-8")
    validation_copy.write_text(validation_text, encoding="utf-8")
    latest_path.write_text(summary_text, encoding="utf-8")
    latest_validation_path.write_text(validation_text, encoding="utf-8")

    pointer_payload = _build_pack_result_payload(
        pack_name=pack_name,
        job_id=job.id,
        project_name=project_name,
        capability_id=job.capability_id,
        status=job.status,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        validation_status=validation_status,
        passed=passed,
        total=total,
        source="pointer",
    )
    pointer_path.write_text(json.dumps(pointer_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    entries = []
    for path in sorted(reports_dir.glob("job_*_summary.md"), key=_job_summary_sort_key, reverse=True):
        match = re.search(r"job_(\d+)_summary\.md$", path.name)
        if not match:
            continue
        job_id = match.group(1)
        title = _extract_summary_line(path)
        entries.append(f"- [Job {job_id}]({path.name}) {title}".rstrip())

    journal_lines = [
        "# 自动沉淀索引",
        "",
        "每次任务出结果后，系统会自动更新这里。",
        "",
        *entries,
        "",
    ]
    journal_path.write_text("\n".join(journal_lines), encoding="utf-8")


def _build_pack_result_payload(
    *,
    pack_name: str,
    job_id: int,
    project_name: str | None,
    capability_id: str | None,
    status: str | None,
    created_at: str | None,
    updated_at: str | None,
    validation_status: str | None,
    passed: int | None,
    total: int | None,
    source: str,
) -> dict[str, Any]:
    return {
        "pack_name": pack_name,
        "job_id": job_id,
        "project_name": project_name,
        "capability_id": capability_id,
        "status": status,
        "created_at": created_at,
        "updated_at": updated_at,
        "validation_status": validation_status,
        "validation_passed": passed,
        "validation_total": total,
        "source": source,
    }


def _enrich_pack_result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    pack_name = str(payload["pack_name"])
    job_id = int(payload["job_id"])
    job_prefix = f"job_{job_id}"
    reports_dir = ADAPTATIONS_DIR / pack_name / "reports"

    summary_rel = f"{job_prefix}/result_summary.md"
    validation_rel = f"{job_prefix}/validation_report.md"
    snapshot_rel = f"{job_prefix}/result_snapshot.json"
    pack_summary_name = f"{job_prefix}_summary.md"
    pack_validation_name = f"{job_prefix}_validation.md"

    resolved = dict(payload)
    resolved.update(
        {
            "artifact_summary_url": f"/artifacts/{summary_rel}",
            "artifact_validation_url": f"/artifacts/{validation_rel}",
            "artifact_snapshot_url": f"/artifacts/{snapshot_rel}",
            "pack_summary_url": f"/adaptation-files/{pack_name}/reports/{pack_summary_name}",
            "pack_validation_url": f"/adaptation-files/{pack_name}/reports/{pack_validation_name}",
            "shared_summary_url": None,
            "shared_validation_url": None,
        }
    )

    snapshot_path = ARTIFACTS_DIR / snapshot_rel
    if snapshot_path.exists():
        snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8-sig"))
        validation_payload = snapshot_payload.get("validation", {})
        resolved["project_name"] = resolved.get("project_name") or snapshot_payload.get("project_name")
        resolved["capability_id"] = resolved.get("capability_id") or snapshot_payload.get("capability_id")
        resolved["status"] = resolved.get("status") or snapshot_payload.get("status")
        resolved["created_at"] = resolved.get("created_at") or snapshot_payload.get("created_at")
        resolved["updated_at"] = resolved.get("updated_at") or snapshot_payload.get("updated_at")
        resolved["validation_status"] = resolved.get("validation_status") or validation_payload.get("status")
        resolved["validation_passed"] = resolved.get("validation_passed")
        if resolved["validation_passed"] is None:
            resolved["validation_passed"] = validation_payload.get("passed")
        resolved["validation_total"] = resolved.get("validation_total")
        if resolved["validation_total"] is None:
            resolved["validation_total"] = validation_payload.get("total")

    shared_summary_path = reports_dir / "latest_result.md"
    shared_validation_path = reports_dir / "latest_validation.md"
    if _shared_report_matches_job(shared_summary_path, job_id):
        resolved["shared_summary_url"] = f"/adaptation-files/{pack_name}/reports/latest_result.md"
    if _shared_report_matches_job(shared_validation_path, job_id):
        resolved["shared_validation_url"] = f"/adaptation-files/{pack_name}/reports/latest_validation.md"

    return resolved


def _payload_matches_current_files(payload: dict[str, Any]) -> bool:
    pack_name = str(payload["pack_name"])
    job_id = int(payload["job_id"])
    reports_dir = ADAPTATIONS_DIR / pack_name / "reports"

    required_paths = [
        ARTIFACTS_DIR / f"job_{job_id}" / "result_summary.md",
        ARTIFACTS_DIR / f"job_{job_id}" / "validation_report.md",
        ARTIFACTS_DIR / f"job_{job_id}" / "result_snapshot.json",
        reports_dir / f"job_{job_id}_summary.md",
        reports_dir / f"job_{job_id}_validation.md",
    ]
    return all(path.exists() for path in required_paths)


def _find_latest_job_id(reports_dir: Path) -> int | None:
    job_ids = [
        _job_summary_sort_key(path)
        for path in reports_dir.glob("job_*_summary.md")
    ]
    job_ids = [job_id for job_id in job_ids if job_id > 0]
    return max(job_ids) if job_ids else None


def _shared_report_matches_job(path: Path, job_id: int) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8-sig")
    return f"# Job {job_id} " in text or f"# Job {job_id}\n" in text


def _extract_summary_line(path: Path) -> str:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("- 状态:"):
            return f"| {line.replace('- ', '')}"
    return ""


def _job_summary_sort_key(path: Path) -> int:
    match = re.search(r"job_(\d+)_summary\.md$", path.name)
    return int(match.group(1)) if match else 0


def _artifact_hint(path: Path) -> str:
    return str(path.relative_to(ARTIFACTS_DIR)).replace("\\", "/")


def _resolve_artifact_path(*, job_dir: Path, path_hint: str) -> Path:
    raw_path = Path(path_hint)
    if raw_path.is_absolute():
        return raw_path

    normalized = Path(path_hint.replace("\\", "/"))
    if normalized.parts and normalized.parts[0].startswith("job_"):
        return ARTIFACTS_DIR.joinpath(*normalized.parts)
    return job_dir.joinpath(*normalized.parts)


def _resolve_chapter_numbers(payload: dict) -> list[int]:
    chapter_numbers: list[int] = []
    for item in payload.get("chapter_briefs", []):
        try:
            chapter_numbers.append(int(item.get("chapter")))
        except (TypeError, ValueError, AttributeError):
            continue
    if chapter_numbers:
        return sorted(set(chapter_numbers))

    start = int(payload.get("chapter_start", 0) or 0)
    end = int(payload.get("chapter_end", 0) or 0)
    if start > 0 and end >= start:
        return list(range(start, end + 1))

    chapter_count = int(payload.get("episode_count", 0) or 0)
    return list(range(1, chapter_count + 1))
