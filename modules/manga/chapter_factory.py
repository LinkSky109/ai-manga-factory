from __future__ import annotations

import csv
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import imageio_ffmpeg

from backend.config import ADAPTATIONS_DIR, ARTIFACTS_DIR, ROOT_DIR
from backend.schemas import ArtifactPreview
from modules.base import ExecutionContext, ExecutionResult, PlannedJob
from shared.asset_lock import AssetLock, asset_lock_from_payload, load_asset_cards, split_character_tokens
from shared.adaptation_quality import build_quality_markdown, qa_max_rounds, qa_thresholds
from shared.providers.ark import ArkProvider
from shared.requirement_mining import RequirementMiner
from shared.source_materials import load_chapter_sources
from shared.storyboard_reference import load_storyboard_profile

from modules.manga.chapter_factory_constants import (
    DEFAULT_KEYFRAME_COUNT,
    DEFAULT_SHOT_COUNT,
    DEFAULT_SMOKE_TEST_TARGET_DURATION_SECONDS,
    DEFAULT_TTS_VOICE,
)
from modules.manga.chapter_factory_phase_audio import ChapterFactoryAudioPhaseMixin
from modules.manga.chapter_factory_phase_qa import ChapterFactoryQAPhaseMixin
from modules.manga.chapter_factory_phase_render import ChapterFactoryRenderPhaseMixin
from modules.manga.chapter_factory_phase_storyboard import ChapterFactoryStoryboardPhaseMixin


class ChapterFactoryRunner(
    ChapterFactoryQAPhaseMixin,
    ChapterFactoryRenderPhaseMixin,
    ChapterFactoryAudioPhaseMixin,
    ChapterFactoryStoryboardPhaseMixin,
):
    def __init__(
        self,
        *,
        payload: dict[str, Any],
        context: ExecutionContext,
        plan: PlannedJob,
        normalize_chapter_briefs,
        build_prompts,
        format_research_brief,
        write_placeholder_image,
        load_font,
    ) -> None:
        self.payload = payload
        self.context = context
        self.plan = plan
        self.job_dir = context.job_dir
        self.normalize_chapter_briefs = normalize_chapter_briefs
        self.build_prompts = build_prompts
        self.format_research_brief = format_research_brief
        self.write_placeholder_image = write_placeholder_image
        self.load_font = load_font
        self.source_title = str(payload.get("source_title", "Untitled")).strip() or "Untitled"
        self.chapter_range = str(payload.get("chapter_range", "TBD")).strip() or "TBD"
        self.visual_style = str(payload.get("visual_style", "东方奇幻漫剧")).strip() or "东方奇幻漫剧"
        requested_episodes = int(payload.get("episode_count", 1) or 1)
        self.chapter_briefs = self.normalize_chapter_briefs(payload=payload, fallback_episode_count=requested_episodes)
        self.episode_count = len(self.chapter_briefs)
        self.keyframe_count = self._resolve_keyframe_count(payload)
        self.shot_count = self._resolve_shot_count(payload)
        default_duration_source = "auto" if isinstance(payload.get("chapter_duration_plan"), dict) else ("request" if payload.get("target_duration_seconds") not in (None, "") else "auto")
        self.target_duration_source = str(payload.get("target_duration_source") or default_duration_source).strip() or "auto"
        self.explicit_target_duration = self.target_duration_source == "request"
        self.explicit_keyframe_count = payload.get("chapter_keyframe_count") not in (None, "")
        self.explicit_shot_count = payload.get("chapter_shot_count") not in (None, "")
        self.use_model_storyboard = bool(payload.get("use_model_storyboard", False))
        self.use_real_images = bool(payload.get("use_real_images", False))
        self.image_model = str(payload.get("image_model", ArkProvider.DEFAULT_IMAGE_MODEL)).strip() or ArkProvider.DEFAULT_IMAGE_MODEL
        self.video_model = str(payload.get("video_model", ArkProvider.DEFAULT_VIDEO_MODEL)).strip() or ArkProvider.DEFAULT_VIDEO_MODEL
        self.storyboard_text_model = (
            str(payload.get("storyboard_text_model", ArkProvider.DEFAULT_STORYBOARD_TEXT_MODEL)).strip()
            or ArkProvider.DEFAULT_STORYBOARD_TEXT_MODEL
        )
        self.lead_image_model = (
            str(payload.get("lead_image_model", ArkProvider.DEFAULT_LEAD_IMAGE_MODEL)).strip()
            or ArkProvider.DEFAULT_LEAD_IMAGE_MODEL
        )
        self.keyframe_image_model = (
            str(payload.get("keyframe_image_model", ArkProvider.DEFAULT_KEYFRAME_IMAGE_MODEL)).strip()
            or ArkProvider.DEFAULT_KEYFRAME_IMAGE_MODEL
        )
        self.storyboard_profile = load_storyboard_profile()
        self.target_duration_seconds = self._resolve_target_duration(payload)
        self.chapter_duration_plan = self._resolve_chapter_duration_plan(payload)
        self.qa_threshold = qa_thresholds()
        self.ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        self.ffprobe_exe = str(Path(self.ffmpeg_exe).with_name("ffprobe.exe"))
        self.provider = (
            ArkProvider.from_local_secrets(
                ROOT_DIR,
                image_model=self.keyframe_image_model,
                video_model=self.video_model,
                text_model=self.storyboard_text_model,
            )
            if self.use_real_images
            else None
        )
        self.text_provider = ArkProvider.from_local_secrets(
            ROOT_DIR,
            image_model=self.keyframe_image_model,
            video_model=self.video_model,
            text_model=self.storyboard_text_model,
        )
        self.provider_notes: list[str] = []
        self.real_image_count = 0
        self.real_video_count = 0
        self.requirement_miner = RequirementMiner()
        self.chapter_artifacts: list[ArtifactPreview] = []
        self.chapter_packages: list[dict[str, Any]] = []
        self.asset_lock: AssetLock = asset_lock_from_payload(payload.get("asset_lock"))
        self.asset_cards = self._load_asset_cards()
        self.source_map = self._load_source_map()

    def run(self) -> ExecutionResult:
        characters_dir = self.job_dir / "characters"
        storyboard_dir = self.job_dir / "storyboard"
        preview_dir = self.job_dir / "preview"
        delivery_dir = self.job_dir / "delivery"
        chapters_dir = self.job_dir / "chapters"
        for path in (characters_dir, storyboard_dir, preview_dir, delivery_dir, chapters_dir):
            path.mkdir(parents=True, exist_ok=True)
        self._report_progress("asset_lock", self._build_asset_lock_progress_details())
        self._report_progress("research", f"研究并初始化《{self.source_title}》 {self.chapter_range} 的章节工厂任务")

        research_path = self.job_dir / "research.md"
        screenplay_path = self.job_dir / "screenplay.md"
        art_path = self.job_dir / "art_direction.md"
        prompts_path = self.job_dir / "prompts.json"
        storyboard_path = storyboard_dir / "storyboard.json"
        manifest_path = self.job_dir / "manifest.json"
        chapters_index_path = self.job_dir / "chapters_index.json"
        qa_overview_path = self.job_dir / "qa_overview.md"
        asset_lock_snapshot_path = self.job_dir / "asset_lock_snapshot.json"
        lead_image_path = characters_dir / "lead_character.png"
        preview_path = preview_dir / "index.html"
        preview_video_path = preview_dir / "preview.mp4"
        delivery_video_path = delivery_dir / "final_cut.mp4"

        prompt_bundle = self.build_prompts(
            source_title=self.source_title,
            visual_style=self.visual_style,
            chapter_briefs=self.chapter_briefs,
            scene_count=max(self.episode_count, 2),
            asset_lock=self.payload.get("asset_lock"),
        )
        self._write_lead_character(prompt_bundle["lead_character"], lead_image_path)
        self._write_top_level_docs(research_path, screenplay_path, art_path)
        self._report_progress("story_breakdown", f"已完成顶层研究文档，准备拆解 {self.episode_count} 个章节包")

        for index, brief in enumerate(self.chapter_briefs, start=1):
            self._report_progress(
                "storyboard_design",
                f"正在生成第 {index}/{self.episode_count} 章《{brief['title']}》的分镜与对白/旁白方案",
            )
            self.chapter_packages.append(self._build_chapter_package(chapters_dir=chapters_dir, brief=brief))
        self._report_progress("chapter_packaging", f"正在封装 {len(self.chapter_packages)} 个章节视频并汇总总预览")
        self._write_job_level_outputs(
            prompt_bundle=prompt_bundle,
            storyboard_dir=storyboard_dir,
            prompts_path=prompts_path,
            storyboard_path=storyboard_path,
            chapters_index_path=chapters_index_path,
            qa_overview_path=qa_overview_path,
            preview_path=preview_path,
            preview_video_path=preview_video_path,
            delivery_video_path=delivery_video_path,
            manifest_path=manifest_path,
            asset_lock_snapshot_path=asset_lock_snapshot_path,
        )
        failed_chapters = [item for item in self.chapter_packages if not item["qa"]["passed"]]
        if failed_chapters:
            failed_ids = ", ".join(f"第{item['chapter']:02d}章" for item in failed_chapters)
            raise RuntimeError(f"QA 未通过，需继续返工：{failed_ids}")
        self._report_progress("qa_loop", f"已完成章节交付与 QA 汇总，共 {self.episode_count} 章")
        artifacts = self._build_artifacts(
            research_path,
            screenplay_path,
            art_path,
            prompts_path,
            storyboard_path,
            chapters_index_path,
            qa_overview_path,
            asset_lock_snapshot_path,
            lead_image_path,
            preview_path,
            preview_video_path,
            delivery_video_path,
            manifest_path,
        )
        output_video_count = self.episode_count * 2 + 2
        summary = f"已按章节工厂模式完成《{self.source_title}》{self.chapter_range} 的漫剧交付，共 {self.episode_count} 章。每章均输出分镜 JSON/CSV/XLSX、音频方案、章节预览视频、章节交付视频与 QA 报告。真图数量 {self.real_image_count}，输出视频数量 {output_video_count}。"
        if self.provider_notes:
            summary += f" 供应商备注：{' | '.join(self.provider_notes)}"
        return ExecutionResult(workflow=self.plan.workflow, artifacts=artifacts, summary=summary)

    def _build_chapter_package(self, *, chapters_dir: Path, brief: dict[str, Any]) -> dict[str, Any]:
        chapter_no = int(brief["chapter"])
        chapter_dir = chapters_dir / f"chapter_{chapter_no:02d}"
        storyboard_dir = chapter_dir / "storyboard"
        images_dir = chapter_dir / "images"
        audio_dir = chapter_dir / "audio"
        video_dir = chapter_dir / "video"
        preview_dir = chapter_dir / "preview"
        delivery_dir = chapter_dir / "delivery"
        qa_dir = chapter_dir / "qa"
        for path in (storyboard_dir, images_dir, audio_dir, video_dir, preview_dir, delivery_dir, qa_dir):
            path.mkdir(parents=True, exist_ok=True)

        qa_rounds: list[dict[str, Any]] = []
        feedback: list[str] = []
        chapter_source = self.source_map.get(chapter_no, "")
        story_grounding = self._build_story_grounding(brief, chapter_source)
        storyboard_blueprint = self._build_storyboard_blueprint(brief, story_grounding)
        storyboard_rows = self._fallback_storyboard_from_blueprint(brief, storyboard_blueprint)
        for round_no in range(1, qa_max_rounds() + 1):
            self._report_progress(
                "storyboard_design",
                f"第 {chapter_no:02d} 章《{brief['title']}》第 {round_no} 轮分镜与音频脚本生成中",
            )
            storyboard_blueprint = self._build_storyboard_blueprint(brief, story_grounding, feedback=feedback)
            storyboard_rows = self._generate_storyboard(
                brief,
                chapter_source,
                feedback,
                grounding=story_grounding,
                blueprint=storyboard_blueprint,
                fallback=storyboard_rows,
            )
            audio_plan = self._build_audio_plan(brief, storyboard_rows)
            review = self._review_plan(brief, storyboard_rows, audio_plan)
            review["round"] = round_no
            qa_rounds.append(review)
            if review["passed"]:
                break
            feedback = [*review["issues"], *review["blockers"]]

        storyboard_json_path = storyboard_dir / "storyboard.json"
        story_grounding_path = storyboard_dir / "story_grounding.json"
        storyboard_blueprint_path = storyboard_dir / "storyboard_blueprint.json"
        storyboard_csv_path = storyboard_dir / "storyboard.csv"
        storyboard_xlsx_path = storyboard_dir / "storyboard.xlsx"
        screenplay_path = chapter_dir / "screenplay.md"
        preview_html_path = preview_dir / "index.html"
        preview_video_path = preview_dir / "chapter_preview.mp4"
        delivery_video_path = delivery_dir / "chapter_final_cut.mp4"
        video_plan_path = video_dir / "video_plan.json"
        audio_plan_path = audio_dir / "audio_plan.json"
        narration_path = audio_dir / "narration_script.txt"
        voice_script_path = audio_dir / "voice_script.txt"
        voiceover_path = audio_dir / "voiceover.mp3"
        ambience_path = audio_dir / "ambience.wav"
        qa_report_path = qa_dir / "qa_report.md"
        qa_snapshot_path = qa_dir / "qa_snapshot.json"
        keyframe_rows = self._select_keyframe_rows(storyboard_rows)
        audio_plan["story_grounding_summary"] = {
            "character_names": story_grounding.get("character_names", []),
            "scene": story_grounding.get("scene", {}),
        }
        audio_plan["storyboard_blueprint_summary"] = {
            "shot_count": storyboard_blueprint.get("shot_count"),
            "keyframe_count": storyboard_blueprint.get("keyframe_count"),
            "target_duration_seconds": storyboard_blueprint.get("target_duration_seconds"),
        }
        self._report_progress(
            "chapter_packaging",
            f"第 {chapter_no:02d} 章《{brief['title']}》正在生成关键帧、配音与视频",
        )
        image_prompts, keyframe_images = self._generate_keyframes(images_dir, brief, keyframe_rows)
        screenplay_path.write_text(self._build_chapter_script_markdown(brief, storyboard_rows, audio_plan), encoding="utf-8")
        story_grounding_path.write_text(json.dumps(story_grounding, ensure_ascii=False, indent=2), encoding="utf-8")
        storyboard_blueprint_path.write_text(json.dumps(storyboard_blueprint, ensure_ascii=False, indent=2), encoding="utf-8")
        storyboard_payload = {
            "chapter": chapter_no,
            "title": brief["title"],
            "summary": brief["summary"],
            "key_scene": brief["key_scene"],
            "story_grounding_summary": {
                "character_names": story_grounding.get("character_names", []),
                "scene": story_grounding.get("scene", {}),
            },
            "storyboard_blueprint_summary": {
                "shot_count": storyboard_blueprint.get("shot_count"),
                "keyframe_count": storyboard_blueprint.get("keyframe_count"),
                "target_duration_seconds": storyboard_blueprint.get("target_duration_seconds"),
            },
            "rows": storyboard_rows,
            "audio": {
                "render_mode": audio_plan.get("render_mode"),
                "cue_sheet": audio_plan.get("cue_sheet", []),
                "narration_tracks": audio_plan.get("narration_tracks", []),
                "dialogue_tracks": audio_plan.get("dialogue_tracks", []),
                "voice_tracks": audio_plan.get("voice_tracks", []),
            },
        }
        storyboard_json_path.write_text(json.dumps(storyboard_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._write_storyboard_csv(storyboard_rows, storyboard_csv_path)
        self._write_storyboard_xlsx(storyboard_rows, storyboard_xlsx_path)
        narration_text = audio_plan["narration_script"]
        voice_script = audio_plan.get("voice_script", narration_text)
        narration_path.write_text(narration_text, encoding="utf-8")
        voice_script_path.write_text(voice_script, encoding="utf-8")
        self._synthesize_voiceover(audio_plan, voiceover_path, audio_plan.get("voice_style", DEFAULT_TTS_VOICE))
        audio_plan_path.write_text(json.dumps(audio_plan, ensure_ascii=False, indent=2), encoding="utf-8")
        total_duration = sum(float(row["时长(s)"]) for row in storyboard_rows)
        self._generate_ambience(ambience_path, total_duration, storyboard_rows)
        video_plan = self._build_video_plan(
            brief=brief,
            storyboard_rows=storyboard_rows,
            keyframe_rows=keyframe_rows,
            keyframe_images=keyframe_images,
            total_duration=total_duration,
            video_dir=video_dir,
        )
        video_plan_path.write_text(json.dumps(video_plan, ensure_ascii=False, indent=2), encoding="utf-8")
        self._render_chapter_video(video_plan, preview_video_path, brief, voiceover_path, ambience_path)
        video_plan_path.write_text(json.dumps(video_plan, ensure_ascii=False, indent=2), encoding="utf-8")
        shutil.copyfile(preview_video_path, delivery_video_path)

        self._report_progress(
            "qa_loop",
            f"第 {chapter_no:02d} 章《{brief['title']}》进入最终 QA 复核",
        )
        final_review = self._review_final(
            brief,
            storyboard_rows,
            qa_rounds[-1],
            preview_video_path,
            delivery_video_path,
            voiceover_path,
            storyboard_xlsx_path,
            video_plan_path,
            video_plan,
        )
        qa_report_path.write_text(self._build_chapter_qa_markdown(brief, qa_rounds, final_review), encoding="utf-8")
        qa_snapshot_path.write_text(json.dumps({"rounds": qa_rounds, "final": final_review}, ensure_ascii=False, indent=2), encoding="utf-8")
        preview_html_path.write_text(self._build_chapter_preview_html(brief, storyboard_rows, keyframe_images, video_plan), encoding="utf-8")

        artifact_paths = [str(path.relative_to(ARTIFACTS_DIR)).replace("\\", "/") for path in [story_grounding_path, storyboard_blueprint_path, storyboard_json_path, storyboard_csv_path, storyboard_xlsx_path, screenplay_path, preview_html_path, preview_video_path, delivery_video_path, video_plan_path, audio_plan_path, narration_path, voice_script_path, voiceover_path, ambience_path, qa_report_path, qa_snapshot_path]]
        artifact_paths.extend(str(path.relative_to(ARTIFACTS_DIR)).replace("\\", "/") for path in keyframe_images)
        self.chapter_artifacts.extend(
            [
                ArtifactPreview(artifact_type="video", label=f"第{chapter_no:02d}章预览视频", path_hint=str(preview_video_path.relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
                ArtifactPreview(artifact_type="video", label=f"第{chapter_no:02d}章交付视频", path_hint=str(delivery_video_path.relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
                ArtifactPreview(artifact_type="markdown", label=f"第{chapter_no:02d}章 QA 报告", path_hint=str(qa_report_path.relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
            ]
        )
        return {
            "chapter": chapter_no,
            "title": brief["title"],
            "storyboard": storyboard_payload,
            "story_grounding": story_grounding,
            "storyboard_blueprint": storyboard_blueprint,
            "audio_plan": audio_plan,
            "artifact_paths": artifact_paths,
            "preview_video": str(preview_video_path),
            "delivery_video": str(delivery_video_path),
            "video_plan": video_plan,
            "image_prompts": image_prompts,
            "qa": final_review,
        }

    def _report_progress(self, step_key: str, details: str) -> None:
        if not details:
            return
        try:
            self.context.report_progress(step_key, details)
        except Exception:
            return

    def _build_asset_lock_progress_details(self) -> str:
        asset_lock = self._current_asset_lock()
        if not asset_lock.exists:
            return "未检测到适配包资产锁，当前按兼容模式继续执行。"
        baseline = "已配置" if asset_lock.scene_baseline_prompt else "未配置"
        validation = "；存在待修复引用" if asset_lock.validation_errors else ""
        return f"已加载资产锁：角色 {len(asset_lock.characters)} 个，场景基线{baseline}，音色映射将用于分镜、音频与 QA{validation}。"

    def _asset_lock_summary(self) -> dict[str, Any]:
        return self._current_asset_lock().to_summary()

    def _current_asset_lock(self) -> AssetLock:
        asset_lock = getattr(self, "asset_lock", None)
        if isinstance(asset_lock, AssetLock):
            return asset_lock
        return AssetLock.empty(pack_root=Path("."))

    def _load_asset_cards(self) -> dict[str, Any]:
        pack_name = str(self.payload.get("adaptation_pack", "")).strip()
        pack_root = self._current_asset_lock().pack_root
        if pack_name:
            pack_root = ADAPTATIONS_DIR / pack_name
        return load_asset_cards(pack_root, source_title=self.source_title, asset_lock=self._current_asset_lock())

    def _story_role_characters(self) -> dict[str, Any]:
        asset_lock = self._current_asset_lock()
        characters = list(asset_lock.characters)
        narrator = asset_lock.narrator_character()
        non_narrators = [character for character in characters if narrator is None or character.name != narrator.name]
        lead = asset_lock.lead_character() or (non_narrators[0] if non_narrators else None)
        support = next((character for character in non_narrators if lead is None or character.name != lead.name), None)
        rival = next(
            (
                character
                for character in non_narrators
                if (lead is None or character.name != lead.name)
                and (support is None or character.name != support.name)
            ),
            None,
        )
        return {
            "lead": lead,
            "support": support,
            "rival": rival,
            "narrator": narrator,
        }

    def _canonicalize_character_name(self, raw_name: str | None) -> str:
        token = str(raw_name or "").strip()
        if not token:
            return ""
        character = self._current_asset_lock().resolve_character(token)
        return character.name if character is not None else token

    # Phase 1: grounding source text into structured chapter facts.














    def _write_top_level_docs(self, research_path: Path, screenplay_path: Path, art_path: Path) -> None:
        research_lines = [f"# 题材研究：{self.source_title}", "", f"- 章节范围：{self.chapter_range}", f"- 章节数：{self.episode_count}", f"- 每章关键帧：{self.keyframe_count}", "", "## 改编质量宪章", "", build_quality_markdown(), "", "## 章节摘要"]
        research_lines.extend(self.format_research_brief(item) for item in self.chapter_briefs)
        research_path.write_text("\n".join(research_lines), encoding="utf-8")
        screenplay_lines = [f"# 章节总脚本：{self.source_title}", "", f"章节范围：{self.chapter_range}", ""]
        screenplay_lines.extend(
            self._build_chapter_script_markdown(
                item,
                fallback_rows,
                self._build_audio_plan(item, fallback_rows),
            )
            for item in self.chapter_briefs
            for fallback_rows in [self._fallback_storyboard(item, self.source_map.get(int(item["chapter"]), ""))]
        )
        screenplay_path.write_text("\n\n".join(screenplay_lines), encoding="utf-8")
        asset_lock_summary = self._asset_lock_summary()
        art_lines = [
            f"# 美术设定：{self.source_title}",
            "",
            f"- 主视觉风格：{self.visual_style}",
            "- 所有章节必须保持人设一致、色彩统一、关键场面有明确视觉符号。",
            "- 分镜遵循节奏组块化设计，每章必须有开场钩子、冲突升级、高潮和尾钩。",
            "- 章节视频必须含画面、旁白/配音、配乐底噪与字幕信息层。",
            "",
            "## 资产锁摘要",
            "",
            f"- 场景基线：{asset_lock_summary['scene']['baseline_prompt'] or '未配置'}",
        ]
        art_lines.extend(
            f"- 角色 {item['name']}：voice_id={item['voice_id'] or '未配置'}；fixed_prompt={item['fixed_prompt'] or '未配置'}"
            for item in asset_lock_summary["characters"]
        )
        if asset_lock_summary["validation_errors"]:
            art_lines.append("- 待修复引用：")
            art_lines.extend(f"- {item}" for item in asset_lock_summary["validation_errors"])
        art_path.write_text("\n".join(art_lines), encoding="utf-8")

    def _write_lead_character(self, prompt: str, output_path: Path) -> None:
        if self.provider is not None:
            try:
                self.provider.generate_image_to_file(
                    prompt=prompt,
                    output_path=output_path,
                    width=1024,
                    height=1024,
                    image_model=self.lead_image_model,
                )
                self.real_image_count += 1
                return
            except Exception as exc:
                self.provider_notes.append(f"主角图回退：{exc}")
        self.write_placeholder_image(output_path=output_path, title=f"{self.source_title} 主角立绘", subtitle=self.visual_style, size=(1024, 1024))

























    # Phase 2: convert approved storyboard rows into timeline-aware audio plans.
















    def _write_storyboard_csv(self, rows: list[dict[str, Any]], output_path: Path) -> None:
        headers = self._collect_storyboard_headers(rows)
        with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

    def _write_storyboard_xlsx(self, rows: list[dict[str, Any]], output_path: Path) -> None:
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "分镜表"
        headers = self._collect_storyboard_headers(rows)
        sheet.append(headers)
        for row in rows:
            sheet.append([row.get(header, "") for header in headers])
        workbook.save(output_path)

    def _collect_storyboard_headers(self, rows: list[dict[str, Any]]) -> list[str]:
        headers: list[str] = []
        for row in rows:
            for key in row.keys():
                if key not in headers:
                    headers.append(key)
        return headers

    def _build_chapter_script_markdown(self, brief: dict[str, Any], rows: list[dict[str, Any]], audio_plan: dict[str, Any]) -> str:
        lines = [f"## 第{brief['chapter']:02d}章：{brief['title']}", "", f"- 剧情摘要：{brief['summary']}", f"- 关键场面：{brief['key_scene']}", f"- 情绪基调：{brief['emotion']}"]
        if brief.get("memorable_line"):
            lines.append(f"- 名台词：{brief['memorable_line']}")
        if brief.get("world_rule"):
            lines.append(f"- 世界观规则：{brief['world_rule']}")
        lines.append("")
        lines.append("### 音频策略")
        lines.append(f"- 配音风格：{audio_plan.get('voice_style', DEFAULT_TTS_VOICE)}")
        lines.append(f"- 配乐情绪：{audio_plan.get('music_mood', brief['emotion'])}")
        lines.append(f"- 旁白条数：{len(audio_plan.get('narration_tracks', []))}")
        lines.append(f"- 对白条数：{len(audio_plan.get('dialogue_tracks', []))}")
        lines.append("")
        lines.append("### 镜头表")
        for row in rows:
            lines.append(
                f"- 镜头{self._row_shot_no(row):02d} | {self._row_pace(row)} | "
                f"画面：{self._row_content(row)} | 旁白：{self._row_narration(row) or '—'} | "
                f"对白：{self._row_dialogue_speaker(row)} / {self._row_dialogue(row) or '—'}"
            )
        return "\n".join(lines)

    def _build_preview_html(self) -> str:
        cards = []
        for item in self.chapter_packages:
            chapter = item["chapter"]
            cards.append(f"<li><a href=\"../chapters/chapter_{chapter:02d}/preview/index.html\">第{chapter:02d}章：{item['title']}</a> | <a href=\"../chapters/chapter_{chapter:02d}/delivery/chapter_final_cut.mp4\">交付视频</a></li>")
        return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>{self.source_title} 漫剧预览</title></head><body><h1>{self.source_title}</h1><video src="preview.mp4" controls style="width:100%;max-width:1080px"></video><h2>章节交付</h2><ol>{''.join(cards)}</ol></body></html>"""

    def _build_qa_overview(self) -> str:
        passed = sum(1 for item in self.chapter_packages if item["qa"]["passed"])
        lines = ["# QA 总览", "", f"- 章节通过：{passed}/{len(self.chapter_packages)}", ""]
        lines.extend([f"- 第{item['chapter']:02d}章 {item['title']}：{item['qa']['summary']}" for item in self.chapter_packages])
        return "\n".join(lines)

    def _write_job_level_outputs(
        self,
        *,
        prompt_bundle: dict[str, Any],
        storyboard_dir: Path,
        prompts_path: Path,
        storyboard_path: Path,
        chapters_index_path: Path,
        qa_overview_path: Path,
        preview_path: Path,
        preview_video_path: Path,
        delivery_video_path: Path,
        manifest_path: Path,
        asset_lock_snapshot_path: Path,
    ) -> None:
        asset_lock_summary = self._asset_lock_summary()
        storyboard_path.write_text(
            json.dumps(
                {
                    "source_title": self.source_title,
                    "chapter_range": self.chapter_range,
                    "episode_count": self.episode_count,
                    "quality_constitution": build_quality_markdown(),
                    "storyboard_profile": self.storyboard_profile,
                    "asset_lock": asset_lock_summary,
                    "asset_cards": self.asset_cards,
                    "story_pipeline": {
                        "transport": "json",
                        "chapter_artifacts": ["story_grounding.json", "storyboard_blueprint.json", "storyboard.json", "audio_plan.json"],
                    },
                    "chapters": [item["storyboard"] for item in self.chapter_packages],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        chapters_index_path.write_text(json.dumps(self.chapter_packages, ensure_ascii=False, indent=2), encoding="utf-8")
        qa_overview_path.write_text(self._build_qa_overview(), encoding="utf-8")
        asset_lock_snapshot_path.write_text(json.dumps(asset_lock_summary, ensure_ascii=False, indent=2), encoding="utf-8")
        prompts_path.write_text(
            json.dumps(
                {
                    **prompt_bundle,
                    "quality_constitution": build_quality_markdown(),
                    "storyboard_profile": self.storyboard_profile,
                    "asset_lock": asset_lock_summary,
                    "asset_cards": self.asset_cards,
                    "chapter_prompt_overview": [
                        {
                            "chapter": item["chapter"],
                            "title": item["title"],
                            "image_prompts": item["image_prompts"],
                        }
                        for item in self.chapter_packages
                    ],
                    "provider_notes": self.provider_notes,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        chapter_preview_videos = [Path(item["preview_video"]) for item in self.chapter_packages]
        chapter_final_videos = [Path(item["delivery_video"]) for item in self.chapter_packages]
        self._concat_videos(chapter_preview_videos, preview_video_path)
        self._concat_videos(chapter_final_videos, delivery_video_path)
        preview_path.write_text(self._build_preview_html(), encoding="utf-8")

        aggregate_scene_images = self._collect_aggregate_scene_images(limit=max(self.episode_count, 2))
        for index, image_path in enumerate(aggregate_scene_images, start=1):
            target = storyboard_dir / f"scene_{index:02d}.png"
            shutil.copyfile(image_path, target)
            self.chapter_artifacts.append(
                ArtifactPreview(
                    artifact_type="image",
                    label=f"分镜图 {index:02d}",
                    path_hint=str(target.relative_to(ARTIFACTS_DIR)).replace("\\", "/"),
                )
            )

        self._write_manifest(manifest_path)

    def _build_artifacts(self, research_path: Path, screenplay_path: Path, art_path: Path, prompts_path: Path, storyboard_path: Path, chapters_index_path: Path, qa_overview_path: Path, asset_lock_snapshot_path: Path, lead_image_path: Path, preview_path: Path, preview_video_path: Path, delivery_video_path: Path, manifest_path: Path) -> list[ArtifactPreview]:
        artifacts = [
            ArtifactPreview(artifact_type="markdown", label="题材研究", path_hint=str(research_path.relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
            ArtifactPreview(artifact_type="markdown", label="章节脚本", path_hint=str(screenplay_path.relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
            ArtifactPreview(artifact_type="markdown", label="美术设定", path_hint=str(art_path.relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
            ArtifactPreview(artifact_type="json", label="提示词包", path_hint=str(prompts_path.relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
            ArtifactPreview(artifact_type="json", label="总分镜 JSON", path_hint=str(storyboard_path.relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
            ArtifactPreview(artifact_type="json", label="章节索引", path_hint=str(chapters_index_path.relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
            ArtifactPreview(artifact_type="markdown", label="QA 总览", path_hint=str(qa_overview_path.relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
            ArtifactPreview(artifact_type="json", label="资产锁快照", path_hint=str(asset_lock_snapshot_path.relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
            ArtifactPreview(artifact_type="image", label="主角立绘", path_hint=str(lead_image_path.relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
            ArtifactPreview(artifact_type="html", label="预览页面", path_hint=str(preview_path.relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
            ArtifactPreview(artifact_type="video", label="预览视频", path_hint=str(preview_video_path.relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
            ArtifactPreview(artifact_type="video", label="交付视频", path_hint=str(delivery_video_path.relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
            ArtifactPreview(artifact_type="json", label="任务清单", path_hint=str(manifest_path.relative_to(ARTIFACTS_DIR)).replace("\\", "/")),
        ]
        artifacts.extend(self.chapter_artifacts)
        return artifacts

    def _load_source_map(self) -> dict[int, str]:
        pack_name = str(self.payload.get("adaptation_pack", "")).strip()
        if not pack_name:
            return {}
        pack_root = ADAPTATIONS_DIR / pack_name / "source"
        if not pack_root.exists():
            return {}
        chapter_numbers = [int(item["chapter"]) for item in self.chapter_briefs]
        loaded = load_chapter_sources(pack_root, chapter_numbers=chapter_numbers, max_chars=1800)
        return {key: value.content for key, value in loaded.items()}

    def _collect_aggregate_scene_images(self, *, limit: int) -> list[Path]:
        images: list[Path] = []
        for item in self.chapter_packages:
            chapter_dir = self.job_dir / "chapters" / f"chapter_{int(item['chapter']):02d}" / "images"
            images.extend(sorted(chapter_dir.glob("keyframe_*.png")))
            if len(images) >= limit:
                break
        return images[:limit]

    def _resolve_keyframe_count(self, payload: dict[str, Any]) -> int:
        raw = payload.get("chapter_keyframe_count", DEFAULT_KEYFRAME_COUNT)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = DEFAULT_KEYFRAME_COUNT
        return min(max(value, 3), 6)

    def _resolve_shot_count(self, payload: dict[str, Any]) -> int:
        raw = payload.get("chapter_shot_count", DEFAULT_SHOT_COUNT)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = DEFAULT_SHOT_COUNT
        return min(max(value, 8), 12)

    def _generate_silence_mp3(self, output_path: Path, duration_seconds: int) -> None:
        command = [self.ffmpeg_exe, "-y", "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=22050", "-t", str(duration_seconds), "-q:a", "9", "-acodec", "libmp3lame", str(output_path)]
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _parse_json_array(self, raw: str) -> list[dict[str, Any]]:
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        data = json.loads(text[text.find("["): text.rfind("]") + 1] if "[" in text else text)
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def _find_row_value(self, row: dict[str, Any], candidates: list[str], default: Any = "") -> Any:
        for key in candidates:
            if key in row and row.get(key) not in (None, ""):
                return row.get(key)
        return default

    def _row_shot_no(self, row: dict[str, Any]) -> int:
        value = self._find_row_value(row, ["镜头号", "shot_no", "shot"], 1)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 1

    def _row_duration(self, row: dict[str, Any]) -> float:
        value = self._find_row_value(row, ["时长(s)", "duration", "duration_seconds"], 3.0)
        try:
            return float(value)
        except (TypeError, ValueError):
            return 3.0

    def _row_scene(self, row: dict[str, Any]) -> str:
        return str(self._find_row_value(row, ["场景/时间", "scene"], "")).strip()

    def _row_size(self, row: dict[str, Any]) -> str:
        return str(self._find_row_value(row, ["镜头景别", "shot_size"], "中景")).strip()

    def _row_movement(self, row: dict[str, Any]) -> str:
        return str(self._find_row_value(row, ["镜头运动", "camera_move"], "缓推")).strip()

    def _row_content(self, row: dict[str, Any]) -> str:
        return str(self._find_row_value(row, ["画面内容", "content"], "")).strip()

    def _row_performance(self, row: dict[str, Any]) -> str:
        return str(self._find_row_value(row, ["人物动作/神态", "performance"], "")).strip()

    def _row_narration(self, row: dict[str, Any]) -> str:
        return str(self._find_row_value(row, ["旁白", "narration"], "")).strip()

    def _row_dialogue_speaker(self, row: dict[str, Any]) -> str:
        raw = str(self._find_row_value(row, ["对白角色", "speaker", "dialogue_speaker"], "")).strip()
        return self._canonicalize_character_name(raw)

    def _row_dialogue(self, row: dict[str, Any]) -> str:
        return str(self._find_row_value(row, ["对白", "台词对白", "dialogue"], "")).strip()

    def _row_present_characters(self, row: dict[str, Any]) -> list[str]:
        tokens = split_character_tokens(str(self._find_row_value(row, ["出镜角色", "present_characters"], "")).strip())
        resolved: list[str] = []
        for token in tokens:
            canonical = self._canonicalize_character_name(token)
            if canonical and canonical not in resolved:
                resolved.append(canonical)
        return resolved

    def _row_pace(self, row: dict[str, Any]) -> str:
        return str(self._find_row_value(row, ["节奏目的", "beat"], "")).strip()

    def _row_priority(self, row: dict[str, Any]) -> int:
        value = self._find_row_value(row, ["关键帧优先级", "priority"], 3)
        return self._coerce_priority(value, default=3)







    # Phase 3: render chapter media from storyboard/audio/video plans.
















    def _build_chapter_preview_html(
        self,
        brief: dict[str, Any],
        rows: list[dict[str, Any]],
        keyframe_images: list[Path],
        video_plan: dict[str, Any],
    ) -> str:
        image_tiles = "\n".join(
            f"<li><img src=\"../images/{path.name}\" alt=\"{path.name}\" style=\"width:100%\"></li>"
            for path in keyframe_images
        )
        shot_items = "\n".join(
            (
                f"<li><strong>镜头{self._row_shot_no(row):02d}</strong> · {self._row_duration(row)}s · {self._row_content(row)}"
                f"<br><small>旁白：{self._row_narration(row) or '—'}</small>"
                f"<br><small>对白：{self._row_dialogue_speaker(row)} / {self._row_dialogue(row) or '—'}</small>"
                f"<br><small>音频设计：{row.get('音频设计', '—')}</small></li>"
            )
            for row in rows
        )
        summary = video_plan.get("summary", {})
        summary_items = "\n".join(
            [
                f"<li>真实视频资产：{summary.get('real_asset_success_count', 0)}/{summary.get('asset_count', 0)}</li>",
                f"<li>真实视频镜头：{summary.get('real_segment_count', 0)}</li>",
                f"<li>本地动画镜头：{summary.get('local_segment_count', 0)}</li>",
                f"<li>回退比例：{summary.get('fallback_ratio', 0.0):.0%}</li>",
            ]
        )
        return (
            "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            f"<title>第{int(brief['chapter']):02d}章预览</title></head><body>"
            f"<h1>第{int(brief['chapter']):02d}章：{brief['title']}</h1>"
            "<video src=\"chapter_preview.mp4\" controls style=\"width:100%;max-width:960px\"></video>"
            "<h2>视频执行摘要</h2>"
            f"<ul>{summary_items}</ul>"
            "<h2>关键帧</h2>"
            f"<ul style=\"display:grid;grid-template-columns:repeat(2,1fr);gap:16px;list-style:none;padding:0\">{image_tiles}</ul>"
            "<h2>镜头清单</h2>"
            f"<ol>{shot_items}</ol>"
            "</body></html>"
        )

    # Override historical mojibake variants so the active QA gate uses clean checks.
    # Phase 4: QA and delivery gating.

















    def _write_manifest(self, manifest_path: Path) -> None:
        artifact_paths = []
        for item in self.chapter_packages:
            artifact_paths.extend(item["artifact_paths"])
        manifest_path.write_text(
            json.dumps(
                {
                    "job_id": self.context.job_id,
                    "project_id": self.context.project_id,
                    "capability": "manga",
                    "chapter_count": self.episode_count,
                    "chapter_keyframe_count": self.keyframe_count,
                    "chapter_shot_count": self.shot_count,
                    "real_image_count": self.real_image_count,
                    "real_video_count": self.real_video_count,
                    "asset_lock": self._asset_lock_summary(),
                    "asset_cards": self.asset_cards,
                    "story_pipeline": {
                        "transport": "json",
                        "chapter_artifacts": ["story_grounding.json", "storyboard_blueprint.json", "storyboard.json", "audio_plan.json"],
                    },
                    "artifacts": sorted(set(artifact_paths)),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def run_manga_job(*, payload: dict[str, Any], context: ExecutionContext, plan: PlannedJob, normalize_chapter_briefs, build_prompts, format_research_brief, write_placeholder_image, load_font) -> ExecutionResult:
    runner = ChapterFactoryRunner(payload=payload, context=context, plan=plan, normalize_chapter_briefs=normalize_chapter_briefs, build_prompts=build_prompts, format_research_brief=format_research_brief, write_placeholder_image=write_placeholder_image, load_font=load_font)
    return runner.run()
