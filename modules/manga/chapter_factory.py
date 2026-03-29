from __future__ import annotations

import asyncio
import csv
import json
import math
import re
import shutil
import struct
import subprocess
import textwrap
import wave
from pathlib import Path
from typing import Any

import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw

from backend.config import ADAPTATIONS_DIR, ARTIFACTS_DIR, ROOT_DIR
from backend.schemas import ArtifactPreview
from modules.base import ExecutionContext, ExecutionResult, PlannedJob
from shared.asset_lock import AssetLock, asset_lock_from_payload, load_asset_cards, split_character_tokens
from shared.adaptation_quality import build_quality_markdown, build_quality_prompt, qa_max_rounds, qa_thresholds
from shared.providers.ark import ArkProvider
from shared.requirement_mining import RequirementMiner
from shared.source_materials import load_chapter_sources
from shared.storyboard_reference import build_fallback_shot_distribution, load_storyboard_profile


DEFAULT_SHOT_COUNT = 10
DEFAULT_KEYFRAME_COUNT = 4
DEFAULT_FPS = 12
DEFAULT_TTS_VOICE = "zh-CN-YunxiNeural"
REAL_VIDEO_SEGMENT_SECONDS = 5
REAL_VIDEO_ASSET_MAX_WAIT_SECONDS = 120
REAL_VIDEO_ASSET_POLL_INTERVAL_SECONDS = 6
VIDEO_MOTION_SCORE_THRESHOLD = 0.0025
REAL_VIDEO_FALLBACK_WARNING_RATIO = 0.6
DEFAULT_SMOKE_TEST_TARGET_DURATION_SECONDS = 60.0
MIN_CHAPTER_DURATION_SECONDS = 24.0
MAX_CHAPTER_DURATION_SECONDS = 120.0


class ChapterFactoryRunner:
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

    def _build_story_grounding(self, brief: dict[str, Any], source_text: str) -> dict[str, Any]:
        asset_lock = self._current_asset_lock()
        cards = self.asset_cards
        cleaned_source_lines = self._clean_source_lines(source_text or brief.get("summary") or "")
        source_excerpt = "\n".join(cleaned_source_lines)[:1800]
        lowered_source = "\n".join(cleaned_source_lines).lower()
        detected_characters: list[dict[str, Any]] = []
        for card in cards.get("character_cards", []):
            if not isinstance(card, dict):
                continue
            name = str(card.get("name") or "").strip()
            if not name:
                continue
            aliases = [name, *[str(alias).strip() for alias in card.get("aliases", []) if str(alias).strip()]]
            matched_aliases = [alias for alias in aliases if alias and alias.lower() in lowered_source]
            if matched_aliases or not source_excerpt:
                detected_characters.append(
                    {
                        "name": name,
                        "voice_id": str(card.get("voice_id") or "").strip(),
                        "aliases": aliases,
                        "fixed_prompt": str(card.get("fixed_prompt") or "").strip(),
                        "reference_image_path": card.get("reference_image_path"),
                        "dramatic_role": str(card.get("dramatic_role") or "").strip() or ("narrator" if name == "旁白" else "primary"),
                        "matched_aliases": matched_aliases,
                    }
                )
        if not detected_characters:
            detected_characters = [card for card in cards.get("character_cards", []) if isinstance(card, dict)]

        scene_card = next((card for card in cards.get("scene_cards", []) if isinstance(card, dict)), {})
        dialogue_candidates_detailed = self._extract_dialogue_candidates(cleaned_source_lines, detected_characters, brief)
        dialogue_candidates = self._unique_texts(
            [str(item.get("text") or "").strip() for item in dialogue_candidates_detailed]
            + [str(brief.get("memorable_line") or "").strip()]
        )
        scene_anchors = self._extract_scene_anchors(cleaned_source_lines, brief, scene_card)
        conflict_points = self._extract_conflict_points(cleaned_source_lines, brief)
        character_relationships = self._extract_character_relationships(cleaned_source_lines, detected_characters)
        story_chunks = self._build_story_chunks("\n".join(cleaned_source_lines), brief)
        narration_candidates = self._unique_texts(
            [
                str(brief.get("world_rule") or "").strip(),
                *scene_anchors[:1],
                *conflict_points[:1],
            ]
        )
        return {
            "chapter": int(brief["chapter"]),
            "title": brief["title"],
            "source_title": self.source_title,
            "scene": {
                "scene_id": str(scene_card.get("scene_id") or "primary_world"),
                "name": str(scene_card.get("name") or f"{self.source_title} 主场景基线"),
                "baseline_prompt": str(scene_card.get("baseline_prompt") or asset_lock.scene_baseline_prompt).strip(),
                "reference_image_path": scene_card.get("reference_image_path"),
            },
            "characters": detected_characters,
            "character_names": [str(item.get("name") or "").strip() for item in detected_characters if str(item.get("name") or "").strip()],
            "source_excerpt": source_excerpt,
            "cleaned_source_lines": cleaned_source_lines,
            "scene_anchors": scene_anchors,
            "conflict_points": conflict_points,
            "dialogue_candidates_detailed": dialogue_candidates_detailed,
            "character_relationships": character_relationships,
            "story_chunks": story_chunks,
            "dialogue_candidates": dialogue_candidates,
            "narration_candidates": narration_candidates,
            "world_rules": [str(brief.get("world_rule") or "").strip()] if str(brief.get("world_rule") or "").strip() else [],
            "facts": self._unique_texts(
                [
                    str(brief.get("summary") or "").strip(),
                    str(brief.get("key_scene") or "").strip(),
                    *scene_anchors,
                    *conflict_points,
                ]
            ),
        }

    def _clean_source_lines(self, source_text: str) -> list[str]:
        raw_lines = re.split(r"[\r\n]+", str(source_text or ""))
        cleaned: list[str] = []
        for raw_line in raw_lines:
            line = re.sub(r"\s+", " ", str(raw_line or "")).strip()
            line = re.sub(r"\s*\d+\s*$", "", line)
            line = line.strip(" \t-—")
            if not line:
                continue
            if len(line) <= 2 and not re.search(r"[“\"「『].+[”\"」』]", line):
                continue
            if re.fullmatch(r"[级別等级：: ]+", line):
                continue
            cleaned.append(line)
        return cleaned

    def _unique_texts(self, values: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = self._condense_text(str(value or "").strip(), limit=48)
            if not item or item in seen:
                continue
            seen.add(item)
            unique.append(item)
        return unique

    def _extract_line_characters(self, line: str, detected_characters: list[dict[str, Any]]) -> list[str]:
        lowered_line = str(line or "").lower()
        names: list[str] = []
        for character in detected_characters:
            canonical = str(character.get("name") or "").strip()
            aliases = [canonical, *[str(alias).strip() for alias in character.get("aliases", []) if str(alias).strip()]]
            if any(alias and alias.lower() in lowered_line for alias in aliases):
                if canonical and canonical not in names:
                    names.append(canonical)
        return names

    def _extract_dialogue_candidates(self, cleaned_source_lines: list[str], detected_characters: list[dict[str, Any]], brief: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        quote_pattern = re.compile(r"[“\"「『](.+?)[”\"」』]")
        for index, line in enumerate(cleaned_source_lines, start=1):
            matches = [self._condense_text(item, limit=36) for item in quote_pattern.findall(line)]
            matches = [item for item in matches if item and len(item) >= 4]
            if not matches:
                continue
            line_characters = self._extract_line_characters(line, detected_characters)
            speaker = line_characters[0] if line_characters else ""
            for text in matches:
                candidates.append(
                    {
                        "text": text,
                        "speaker": speaker,
                        "source": "quoted_dialogue",
                        "line_index": index,
                        "context": line,
                    }
                )
        memorable_line = self._normalize_dialogue_text(str(brief.get("memorable_line") or "").strip())
        if memorable_line and memorable_line not in {item["text"] for item in candidates}:
            candidates.append(
                {
                    "text": memorable_line,
                    "speaker": self._default_dialogue_speaker("高潮"),
                    "source": "brief_memorable_line",
                    "line_index": 0,
                    "context": str(brief.get("summary") or "").strip(),
                }
            )
        return candidates

    def _extract_scene_anchors(self, cleaned_source_lines: list[str], brief: dict[str, Any], scene_card: dict[str, Any]) -> list[str]:
        keywords = ("广场", "台", "席", "大殿", "宿舍", "走廊", "石碑", "洞府", "擂台", "房间", "门外")
        anchors = [
            self._condense_text(line, limit=42)
            for line in cleaned_source_lines
            if any(keyword in line for keyword in keywords)
        ]
        anchors.extend(
            [
                self._condense_text(str(scene_card.get("name") or "").strip(), limit=42),
                self._condense_text(str(brief.get("key_scene") or "").strip(), limit=42),
            ]
        )
        return self._unique_texts(anchors)

    def _extract_conflict_points(self, cleaned_source_lines: list[str], brief: dict[str, Any]) -> list[str]:
        keywords = ("哄笑", "嘲", "冷声", "压住", "逼", "怒", "羞辱", "失控", "拳", "发白", "三段")
        points = [
            self._condense_text(line, limit=42)
            for line in cleaned_source_lines
            if any(keyword in line for keyword in keywords)
        ]
        points.append(self._condense_text(str(brief.get("summary") or "").strip(), limit=42))
        return self._unique_texts(points)

    def _extract_character_relationships(self, cleaned_source_lines: list[str], detected_characters: list[dict[str, Any]]) -> list[str]:
        relationships: list[str] = []
        for line in cleaned_source_lines:
            mentioned = self._extract_line_characters(line, detected_characters)
            if len(mentioned) >= 2:
                relationships.append(f"{mentioned[0]} 与 {mentioned[1]}：{self._condense_text(line, limit=36)}")
            elif "哥哥" in line and mentioned:
                relationships.append(f"{mentioned[0]}：{self._condense_text(line, limit=36)}")
        return self._unique_texts(relationships)

    def _derive_blueprint_target_duration(self, brief: dict[str, Any], grounding: dict[str, Any]) -> float:
        chapter_target = self._chapter_target_duration(brief)
        if chapter_target is not None:
            return round(chapter_target, 1)
        source_excerpt = str(grounding.get("source_excerpt") or "")
        character_count = len(grounding.get("character_names", []))
        complexity = (
            character_count
            + len(grounding.get("conflict_points", []))
            + min(2, len(grounding.get("dialogue_candidates", [])))
            + (1 if grounding.get("world_rules") else 0)
        )
        estimated = 42.0 + min(36.0, len(source_excerpt) / 65.0) + complexity * 3.5
        return round(max(45.0, min(90.0, estimated)), 1)

    def _derive_blueprint_shot_count(self, grounding: dict[str, Any]) -> int:
        if self.explicit_shot_count:
            return max(6, min(12, int(self.shot_count)))
        source_excerpt = str(grounding.get("source_excerpt") or "")
        character_count = len(grounding.get("character_names", []))
        estimated = 6 + min(4, max(0, len(source_excerpt) // 220)) + min(2, max(0, character_count - 1))
        return max(6, min(12, int(estimated)))

    def _derive_blueprint_keyframe_count(self, shot_count: int) -> int:
        if self.explicit_keyframe_count:
            return max(3, min(5, int(self.keyframe_count)))
        return max(3, min(5, math.ceil(shot_count / 3)))

    def _blueprint_present_characters(self, beat: str, roles: dict[str, Any], detected_names: list[str]) -> list[str]:
        lead = roles.get("lead")
        support = roles.get("support")
        rival = roles.get("rival")
        present: list[str] = []
        if "关系建立" in beat and support is not None:
            present = [character.name for character in (lead, support) if character is not None]
        elif ("冲突" in beat or "高潮" in beat) and rival is not None:
            present = [character.name for character in (lead, rival) if character is not None]
        elif lead is not None:
            present = [lead.name]
        if not present:
            present = [name for name in detected_names if name and name != "旁白"][:2]
        deduped: list[str] = []
        for item in present:
            if item and item not in deduped:
                deduped.append(item)
        return deduped

    def _blueprint_speaker(self, beat: str, shot_index: int, shot_count: int, roles: dict[str, Any], present_characters: list[str]) -> str:
        narrator = roles.get("narrator")
        lead = roles.get("lead")
        support = roles.get("support")
        rival = roles.get("rival")
        if "高潮前停顿" in beat:
            return ""
        if "关系建立" in beat and support is not None:
            return support.name if shot_index % 2 == 0 else (lead.name if lead is not None else support.name)
        if ("冲突" in beat or "高潮" in beat) and rival is not None:
            return lead.name if shot_index < max(1, shot_count - 1) else rival.name
        if narrator is not None and "结尾" in beat and not present_characters:
            return narrator.name
        return lead.name if lead is not None else (present_characters[0] if present_characters else "")

    def _blueprint_narration(self, *, brief: dict[str, Any], beat: str, content: str, has_dialogue: bool, shot_index: int, total_shots: int) -> str:
        if has_dialogue and shot_index not in {1, total_shots} and "世界规则" not in content:
            return ""
        if shot_index == 1 or "开场钩子" in beat:
            return self._compose_compact_text(str(brief.get("summary") or "").strip(), content, limit=36)
        if "高潮前停顿" in beat and str(brief.get("world_rule") or "").strip():
            return str(brief.get("world_rule") or "").strip()
        if shot_index == total_shots:
            return self._compose_compact_text(content, "余波未散，新的悬念已经落下。", limit=34)
        return ""

    def _build_storyboard_blueprint(self, brief: dict[str, Any], grounding: dict[str, Any], feedback: list[str] | None = None) -> dict[str, Any]:
        profile_blocks = self.storyboard_profile.get("group_style_blocks", [])
        beats = [str(block.get("beat") or "") for block in profile_blocks if str(block.get("beat") or "").strip()]
        if not beats:
            beats = ["开场钩子", "关系建立", "冲突升级", "高潮前停顿", "高潮", "结尾反转/尾钩"]
        shot_count = self._derive_blueprint_shot_count(grounding)
        keyframe_count = self._derive_blueprint_keyframe_count(shot_count)
        target_duration_seconds = self._derive_blueprint_target_duration(grounding)
        roles = self._story_role_characters()
        detected_names = list(grounding.get("character_names", []))
        durations = build_fallback_shot_distribution(
            group_durations=[target_duration_seconds / len(beats)] * len(beats),
            shot_count=shot_count,
        )
        story_chunks = list(grounding.get("story_chunks", [])) or self._build_story_chunks(str(grounding.get("source_excerpt") or ""), brief)
        shots: list[dict[str, Any]] = []
        cursor = 0.0
        shot_no = 1
        for beat_index, beat in enumerate(beats, start=1):
            local_count = durations[beat_index - 1] if beat_index - 1 < len(durations) else 1
            beat_shot_count = max(1, int(local_count))
            duration_per_shot = round((target_duration_seconds / shot_count), 1)
            for local_index in range(beat_shot_count):
                chunk = story_chunks[min(len(story_chunks) - 1, shot_no - 1)] if story_chunks else str(brief.get("summary") or "")
                stage_block = profile_blocks[min(beat_index - 1, len(profile_blocks) - 1)] if profile_blocks else {}
                present_characters = self._blueprint_present_characters(beat, roles, detected_names)
                speaker = self._blueprint_speaker(beat, local_index, beat_shot_count, roles, present_characters)
                dialogue = ""
                if speaker:
                    if "高潮" in beat and str(brief.get("memorable_line") or "").strip():
                        dialogue = str(brief.get("memorable_line") or "").strip()
                    elif "关系建立" in beat and roles.get("support") is not None:
                        dialogue = "先别急着出手，让我确认这里到底哪里不对。"
                    elif "冲突" in beat:
                        dialogue = "再退一步，局面就真的压不住了。"
                    elif shot_no == 1:
                        dialogue = "这火不对劲。"
                    elif shot_no == shot_count:
                        dialogue = "这件事，还没结束。"
                content = self._compose_compact_text(
                    chunk,
                    str(stage_block.get("focus") or brief.get("key_scene") or brief.get("summary") or "").strip(),
                    limit=42,
                )
                narration = self._blueprint_narration(
                    brief=brief,
                    beat=beat,
                    content=content,
                    has_dialogue=bool(dialogue),
                    shot_index=shot_no,
                    total_shots=shot_count,
                )
                shots.append(
                    {
                        "shot": shot_no,
                        "beat": beat,
                        "scene": self._build_stage_scene_label(brief, beat_index, beat),
                        "duration_seconds": duration_per_shot,
                        "start_seconds": round(cursor, 1),
                        "end_seconds": round(cursor + duration_per_shot, 1),
                        "speaker": speaker,
                        "present_characters": present_characters,
                        "content": content,
                        "performance": self._build_group_performance(brief, stage_block, beat_index, local_index),
                        "dialogue": dialogue,
                        "narration": narration,
                        "audio_design": self._build_group_audio_beat(beat),
                        "music": self._build_group_music(brief, stage_block, beat_index),
                        "shot_size": self._pick_group_value(stage_block.get("size_candidates", ["中景"]), local_index, fallback="中景"),
                        "camera_move": self._pick_group_value(stage_block.get("movement_candidates", ["缓推"]), local_index, fallback="缓推"),
                        "priority": max(1, 6 - local_index),
                    }
                )
                cursor += duration_per_shot
                shot_no += 1
                if shot_no > shot_count:
                    break
            if shot_no > shot_count:
                break
        return {
            "chapter": int(brief["chapter"]),
            "title": brief["title"],
            "target_duration_seconds": target_duration_seconds,
            "shot_count": shot_count,
            "keyframe_count": keyframe_count,
            "feedback": list(feedback or []),
            "scene": grounding.get("scene", {}),
            "character_names": detected_names,
            "shots": shots,
        }

    def _fallback_storyboard_from_blueprint(self, brief: dict[str, Any], blueprint: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for shot in blueprint.get("shots", []):
            if not isinstance(shot, dict):
                continue
            rows.append(
                {
                    "分组": f"第{max(1, math.ceil(int(shot['shot']) / 2))}组",
                    "15秒段": f"{shot['start_seconds']}-{shot['end_seconds']}秒",
                    "镜头号": int(shot["shot"]),
                    "时长(s)": float(shot["duration_seconds"]),
                    "起始时间": float(shot["start_seconds"]),
                    "结束时间": float(shot["end_seconds"]),
                    "场景/时间": str(shot.get("scene") or ""),
                    "镜头景别": str(shot.get("shot_size") or "中景"),
                    "镜头运动": str(shot.get("camera_move") or "缓推"),
                    "画面内容": str(shot.get("content") or ""),
                    "人物动作/神态": str(shot.get("performance") or brief.get("emotion") or ""),
                    "旁白": str(shot.get("narration") or ""),
                    "对白角色": str(shot.get("speaker") or ""),
                    "对白": str(shot.get("dialogue") or ""),
                    "台词对白": str(shot.get("dialogue") or ""),
                    "角色": "、".join(shot.get("present_characters", [])),
                    "出镜角色": "、".join(shot.get("present_characters", [])),
                    "音效": str(shot.get("audio_design") or self._build_group_audio_beat(str(shot.get("beat") or ""))),
                    "音频设计": str(shot.get("audio_design") or ""),
                    "音乐": str(shot.get("music") or brief.get("emotion") or ""),
                    "节奏目的": str(shot.get("beat") or ""),
                    "关键帧优先级": int(shot.get("priority") or 3),
                    "blueprint_shot_count": int(blueprint.get("shot_count") or self.shot_count),
                    "blueprint_keyframe_count": int(blueprint.get("keyframe_count") or self.keyframe_count),
                }
            )
        return self._normalize_storyboard_rows(rows, brief)

    def _generate_storyboard(
        self,
        brief: dict[str, Any],
        source_text: str,
        feedback: list[str],
        *,
        grounding: dict[str, Any],
        blueprint: dict[str, Any],
        fallback: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        candidate_rows = fallback
        if not self.use_model_storyboard or self.text_provider is None:
            return self._apply_storyboard_feedback(brief, candidate_rows, feedback)
        payload = {
            "任务": "把单章小说内容改编成可执行的章节分镜表",
            "质量宪章": build_quality_prompt(),
            "章节摘要": brief,
            "原文节选": source_text[:1800] if source_text else "无",
            "story_grounding": grounding,
            "storyboard_blueprint": blueprint,
            "参考模板": self.storyboard_profile,
            "返工意见": feedback or ["无"],
            "输出要求": {
                "shot_count": int(blueprint.get("shot_count") or self.shot_count),
                "fields": self.storyboard_profile["required_fields"] + ["旁白", "对白角色", "对白", "音频设计", "音乐", "节奏目的", "关键帧优先级"],
                "notes": "只返回 JSON 数组，不要解释；按章节内容可支撑的时长出片，默认以 60 秒为最小 smoke test 单元，不为凑时长重复镜头；必须保留名台词、世界观规则和关键场面；不要在场景字段里写第几章、第几组、时间卡或场景标题污染；对白角色和出镜角色只能使用 story_grounding / storyboard_blueprint 已确认的真实角色名，不能输出主角、同伴、对手这类槽位词。",
            },
        }
        try:
            raw = self.text_provider.generate_text(
                messages=[
                    {"role": "system", "content": build_quality_prompt()},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
                ],
                text_model=self.storyboard_text_model,
                max_tokens=3500,
            )
            rows = self._parse_json_array(raw)
            if rows:
                candidate_rows = self._normalize_storyboard_rows(rows, brief)
        except Exception as exc:
            self.provider_notes.append(f"章节 {brief['chapter']} 分镜改用回退模板：{exc}")
        return self._apply_storyboard_feedback(brief, candidate_rows, feedback)

    def _select_keyframe_rows(self, storyboard_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ranked = sorted(
            storyboard_rows,
            key=lambda item: (
                self._row_priority(item),
                self._row_duration(item),
            ),
            reverse=True,
        )
        selected = ranked[: self.keyframe_count]
        return selected or storyboard_rows[: self.keyframe_count]

    def _generate_keyframes(self, images_dir: Path, brief: dict[str, Any], keyframe_rows: list[dict[str, Any]]) -> tuple[list[str], list[Path]]:
        prompts: list[str] = []
        paths: list[Path] = []
        for index, row in enumerate(keyframe_rows, start=1):
            prompt = (
                f"Chinese cinematic manga keyframe for {self.source_title}: "
                f"{row['画面内容']}. "
                f"Shot size {row['镜头景别']}. "
                f"Camera cue {row['镜头运动']}. "
                f"Acting {row['人物动作/神态']}. "
                f"Style {self.visual_style}. Preserve original character motivations and world rules. "
                "Do not render chapter labels, scene captions, timestamps, or storyboard text in the image."
            )
            output_path = images_dir / f"keyframe_{index:02d}.png"
            if self.provider is not None:
                try:
                    self.provider.generate_image_to_file(
                        prompt=prompt,
                        output_path=output_path,
                        width=1024,
                        height=1024,
                        image_model=self.keyframe_image_model,
                    )
                    self.real_image_count += 1
                except Exception as exc:
                    self.provider_notes.append(f"章节 {brief['chapter']} 关键帧回退：{exc}")
                    self.write_placeholder_image(output_path=output_path, title=self.source_title, subtitle=row["画面内容"], size=(1024, 1024))
            else:
                self.write_placeholder_image(output_path=output_path, title=self.source_title, subtitle=row["画面内容"], size=(1024, 1024))
            prompts.append(prompt)
            paths.append(output_path)
        return prompts, paths

    def _review_plan(self, brief: dict[str, Any], storyboard_rows: list[dict[str, Any]], audio_plan: dict[str, Any]) -> dict[str, Any]:
        asset_lock = self._current_asset_lock()
        joined = json.dumps(storyboard_rows, ensure_ascii=False)
        blockers: list[str] = []
        issues: list[str] = []
        dialogue_count = len(audio_plan.get("dialogue_tracks", []))
        narration_count = len(audio_plan.get("narration_tracks", []))
        cue_sheet = audio_plan.get("cue_sheet", [])
        meaningful_speakers = {
            str(track.get("speaker") or "").strip()
            for track in audio_plan.get("dialogue_tracks", [])
            if str(track.get("speaker") or "").strip() not in {"", "无", "—", "旁白"}
        }
        voice_script = str(audio_plan.get("voice_script") or "").strip()
        if brief.get("memorable_line") and brief["memorable_line"] not in joined:
            blockers.append("名台词没有进入章节分镜")
        if brief.get("world_rule") and brief["world_rule"] not in joined:
            issues.append("世界观规则表达偏弱")
        if not cue_sheet:
            blockers.append("音频 cue sheet 缺失")
        if dialogue_count <= 0:
            blockers.append("章节对白缺失")
        if narration_count <= 0:
            blockers.append("章节旁白缺失")
        if dialogue_count > 0 and not meaningful_speakers:
            blockers.append("章节对白没有有效角色承载")
        if narration_count > 0 and "旁白：" not in voice_script:
            blockers.append("voice_script 缺少旁白台本")
        if dialogue_count > 0 and not any(f"{speaker}：" in voice_script for speaker in meaningful_speakers):
            blockers.append("voice_script 缺少角色对白台本")
        polluted_scene_rows = [
            self._row_shot_no(row)
            for row in storyboard_rows
            if re.search(r"第\d+章|第\d+组|\d+秒|scene|chapter", self._row_scene(row), flags=re.IGNORECASE)
        ]
        if polluted_scene_rows:
            blockers.append("分镜场景字段仍包含章节或时间字卡污染")
        total_duration = sum(float(row["时长(s)"]) for row in storyboard_rows)
        scores = {
            "fidelity": 9.0 if not blockers else 6.8,
            "pacing": 8.8 if 90 <= total_duration <= 120 else 6.5,
            "production": 8.6 if audio_plan.get("voice_style") and dialogue_count > 0 and narration_count > 0 and cue_sheet else 6.4,
            "adaptation": 8.4 if storyboard_rows else 6.5,
        }
        overall = round(sum(scores.values()) / 4, 2)
        passed = all(scores[key] >= self.qa_threshold[key] for key in ("fidelity", "pacing", "production", "adaptation")) and overall >= self.qa_threshold["overall"] and not blockers
        if not passed:
            issues.extend(["加强情绪铺垫", "增加章节钩子与结尾反转"])
        return {"passed": passed, "scores": scores, "overall": overall, "issues": issues, "blockers": blockers}

    def _review_final(self, brief: dict[str, Any], storyboard_rows: list[dict[str, Any]], plan_review: dict[str, Any], preview_video: Path, delivery_video: Path, voiceover: Path, storyboard_xlsx: Path) -> dict[str, Any]:
        blockers = list(plan_review["blockers"])
        if not preview_video.exists() or not delivery_video.exists():
            blockers.append("章节视频缺失")
        if not storyboard_xlsx.exists():
            blockers.append("章节分镜交付缺失")
        if not voiceover.exists():
            blockers.append("章节旁白缺失")
        passed = not blockers and plan_review["passed"]
        return {"passed": passed, "overall": plan_review["overall"], "scores": plan_review["scores"], "blockers": blockers, "summary": f"第{brief['chapter']:02d}章 {'通过' if passed else '未通过'} QA"}

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

    def _fallback_storyboard(self, brief: dict[str, Any], source_text: str) -> list[dict[str, Any]]:
        group_durations = self.storyboard_profile["group_durations"]
        shots_per_group = build_fallback_shot_distribution(group_durations=group_durations, shot_count=self.shot_count)
        stage_blocks = self.storyboard_profile.get("group_style_blocks", [])
        rows: list[dict[str, Any]] = []
        shot_no = 1
        cursor = 0.0
        story_chunks = self._build_story_chunks(source_text, brief)
        for group_index, group_duration in enumerate(group_durations, start=1):
            count = shots_per_group[group_index - 1] if group_index - 1 < len(shots_per_group) else 1
            shot_duration = round(group_duration / count, 1)
            stage_block = stage_blocks[min(group_index - 1, len(stage_blocks) - 1)] if stage_blocks else {
                "beat": ["开场钩子", "关系建立", "冲突升级", "高潮前停顿", "高潮", "尾钩"][min(group_index - 1, 5)],
                "size_candidates": ["大全景", "中景", "近景", "特写"],
                "movement_candidates": ["缓推", "平移", "定镜", "微摇"],
                "focus": brief["summary"],
                "audio_focus": "氛围环境声",
            }
            for local_index in range(count):
                end_time = round(cursor + shot_duration, 1)
                pace_label = stage_block.get("beat", "收束")
                scene_label = self._build_stage_scene_label(brief, group_index, pace_label)
                size = self._pick_group_value(stage_block.get("size_candidates", ["中景"]), local_index, fallback="中景")
                movement = self._pick_group_value(stage_block.get("movement_candidates", ["定镜"]), local_index, fallback="定镜")
                dialogue_payload = self._build_group_dialogue_payload(brief, stage_block, group_index, local_index, count)
                rows.append(
                    {
                        "分组": f"第{group_index}组",
                        "15秒段": f"{round(cursor,1)}-{end_time}秒",
                        "镜头号": shot_no,
                        "时长(s)": shot_duration,
                        "起始时间": round(cursor, 1),
                        "结束时间": end_time,
                        "场景/时间": scene_label,
                        "镜头景别": size,
                        "镜头运动": movement,
                        "画面内容": self._build_group_content(brief, story_chunks, stage_block, group_index, local_index),
                        "人物动作/神态": self._build_group_performance(brief, stage_block, group_index, local_index),
                        "旁白": dialogue_payload["narration"],
                        "对白角色": dialogue_payload["speaker"],
                        "对白": dialogue_payload["dialogue"],
                        "台词对白": dialogue_payload["dialogue"],
                        "角色": self._build_group_roles(brief, stage_block),
                        "音效": self._build_group_audio(stage_block, group_index, local_index),
                        "音频设计": dialogue_payload["audio_design"],
                        "音乐": self._build_group_music(brief, stage_block, group_index),
                        "节奏目的": pace_label,
                        "关键帧优先级": max(1, 5 - local_index),
                    }
                )
                cursor = end_time
                shot_no += 1
        return rows

    def _normalize_storyboard_rows(self, rows: list[dict[str, Any]], brief: dict[str, Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        cursor = 0.0
        shot_limit = next(
            (
                int(row.get("blueprint_shot_count") or 0)
                for row in rows
                if int(row.get("blueprint_shot_count") or 0) > 0
            ),
            int(self.shot_count),
        )
        for index, row in enumerate(rows[: shot_limit], start=1):
            duration = max(0.8, float(row.get("时长(s)", row.get("duration", 1.2)) or 1.2))
            end_time = round(cursor + duration, 1)
            beat = str(row.get("节奏目的", "冲突推进"))
            scene_value = str(row.get("场景/时间", "")).strip()
            if not scene_value or re.search(r"第\d+章|第\d+组|\d+秒|scene|chapter", scene_value, flags=re.IGNORECASE):
                scene_value = self._build_stage_scene_label(brief, min(6, math.ceil(index / 2)), beat)
            dialogue = str(row.get("对白", row.get("台词对白", "—"))).strip() or "—"
            narration = str(row.get("旁白", "")).strip()
            if not narration and dialogue in {"", "—"} and index == 1:
                narration = self._build_group_narration(brief, beat, str(row.get("画面内容", brief["key_scene"])))
            speaker = self._canonicalize_character_name(
                str(row.get("对白角色", row.get("角色", self._default_dialogue_speaker(beat)))).strip()
                or self._default_dialogue_speaker(beat)
            )
            present_characters = self._normalize_present_characters(row=row, speaker=speaker, beat=beat)
            canonical_role_text = "、".join(present_characters) if present_characters else str(row.get("角色", self.source_title))
            normalized.append(
                {
                    "分组": str(row.get("分组", f"第{min(6, math.ceil(index / 2))}组")),
                    "15秒段": str(row.get("15秒段", f"{cursor}-{end_time}秒")),
                    "镜头号": index,
                    "时长(s)": round(duration, 1),
                    "起始时间": round(cursor, 1),
                    "结束时间": end_time,
                    "场景/时间": scene_value,
                    "镜头景别": str(row.get("镜头景别", "中景")),
                    "镜头运动": str(row.get("镜头运动", "缓推")),
                    "画面内容": str(row.get("画面内容", brief["key_scene"])),
                    "人物动作/神态": str(row.get("人物动作/神态", brief["emotion"])),
                    "旁白": narration,
                    "对白角色": speaker,
                    "对白": dialogue,
                    "台词对白": dialogue,
                    "角色": canonical_role_text,
                    "出镜角色": "、".join(present_characters),
                    "音效": str(row.get("音效", "氛围环境声")),
                    "音频设计": str(row.get("音频设计", self._build_group_audio_beat(beat))),
                    "音乐": str(row.get("音乐", brief["emotion"])),
                    "节奏目的": beat,
                    "关键帧优先级": self._coerce_priority(row.get("关键帧优先级", 3), default=3),
                    "blueprint_shot_count": int(row.get("blueprint_shot_count") or shot_limit),
                    "blueprint_keyframe_count": int(row.get("blueprint_keyframe_count") or self.keyframe_count),
                }
            )
            cursor = end_time
        return normalized or self._fallback_storyboard(brief, "")

    def _normalize_present_characters(self, *, row: dict[str, Any], speaker: str, beat: str) -> list[str]:
        asset_lock = self._current_asset_lock()
        explicit_tokens = split_character_tokens(str(row.get("出镜角色", "")).strip())
        inferred_tokens = split_character_tokens(str(row.get("角色", "")).strip())
        if speaker and speaker not in {"", "—", "无", "旁白"}:
            inferred_tokens.append(speaker)
        candidates = explicit_tokens or inferred_tokens
        if not candidates and asset_lock.lead_character() is not None:
            candidates = [asset_lock.lead_character().name]

        if asset_lock.exists:
            resolved = asset_lock.resolve_many(candidates)
            if resolved:
                return [character.name for character in resolved]
            if explicit_tokens or candidates:
                return []
            return self._default_present_characters_for_beat(asset_lock=asset_lock, beat=beat, speaker=speaker)

        deduped: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            token = str(candidate).strip()
            if not token or token in seen:
                continue
            seen.add(token)
            deduped.append(token)
        return deduped

    def _default_present_characters_for_beat(self, *, asset_lock: AssetLock, beat: str, speaker: str) -> list[str]:
        speaker_character = asset_lock.resolve_character(speaker)
        if speaker_character is not None and speaker_character.name != "旁白":
            return [speaker_character.name]

        roles = self._story_role_characters()
        lead = roles.get("lead")
        support = roles.get("support")
        rival = roles.get("rival")

        candidates: list[str] = []
        if "关系建立" in beat:
            candidates = [character.name for character in (lead, support) if character is not None]
        elif "冲突" in beat or "高潮" in beat:
            candidates = [character.name for character in (lead, rival) if character is not None]
        else:
            candidates = [lead.name] if lead is not None else []

        deduped: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            deduped.append(candidate)
        return deduped

    def _coerce_priority(self, value: Any, default: int = 3) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            normalized = str(value or "").strip()
            mapping = {
                "高": 5,
                "中": 3,
                "低": 1,
                "一": 1,
                "二": 2,
                "三": 3,
                "四": 4,
                "五": 5,
                "六": 6,
            }
            return mapping.get(normalized, default)

    def _apply_storyboard_feedback(self, brief: dict[str, Any], rows: list[dict[str, Any]], feedback: list[str]) -> list[dict[str, Any]]:
        working_rows = self._normalize_storyboard_rows([dict(item) for item in rows], brief)
        self._rebalance_storyboard_durations(working_rows)
        self._diversify_storyboard_rows(brief, working_rows)
        self._ensure_storyboard_quality_anchors(brief, working_rows)
        if feedback:
            self._apply_feedback_notes(brief, working_rows, feedback)
            self._rebalance_storyboard_durations(working_rows)
            self._diversify_storyboard_rows(brief, working_rows)
            self._ensure_storyboard_quality_anchors(brief, working_rows)
        return working_rows

    def _rebalance_storyboard_durations(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        target_duration = float(self.storyboard_profile.get("target_duration_seconds", 96.0) or 96.0)
        durations = [max(3.0, float(row.get("时长(s)", 3.0) or 3.0)) for row in rows]
        current_total = sum(durations)
        if not (90 <= current_total <= 120):
            scale = target_duration / max(current_total, 1.0)
            durations = [round(max(3.0, duration * scale), 1) for duration in durations]
            delta = round(target_duration - sum(durations), 1)
            durations[-1] = round(max(3.0, durations[-1] + delta), 1)
        self._reflow_storyboard_timing(rows, durations)

    def _reflow_storyboard_timing(self, rows: list[dict[str, Any]], durations: list[float]) -> None:
        cursor = 0.0
        for row, duration in zip(rows, durations):
            end_time = round(cursor + duration, 1)
            row["时长(s)"] = round(duration, 1)
            row["起始时间"] = round(cursor, 1)
            row["结束时间"] = end_time
            row["15秒段"] = f"{round(cursor, 1)}-{end_time}秒"
            cursor = end_time

    def _ensure_storyboard_quality_anchors(self, brief: dict[str, Any], rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        rows[0]["节奏目的"] = "开场钩子"
        rows[0]["画面内容"] = self._append_unique_text(str(rows[0].get("画面内容", "")), brief["key_scene"])
        rows[-1]["节奏目的"] = "结尾反转/尾钩"
        rows[-1]["画面内容"] = self._append_unique_text(str(rows[-1].get("画面内容", "")), f"尾钩：{brief['summary']}")

        memorable_line = str(brief.get("memorable_line", "")).strip()
        if memorable_line and memorable_line not in json.dumps(rows, ensure_ascii=False):
            anchor_index = 1 if len(rows) > 1 else 0
            rows[anchor_index]["对白"] = memorable_line
            rows[anchor_index]["台词对白"] = memorable_line
            rows[anchor_index]["对白角色"] = str(rows[anchor_index].get("对白角色", "主角")).strip() or "主角"
            rows[anchor_index]["画面内容"] = self._append_unique_text(str(rows[anchor_index].get("画面内容", "")), f"名台词爆点：{memorable_line}")
            rows[anchor_index]["节奏目的"] = self._append_unique_text(str(rows[anchor_index].get("节奏目的", "")), "名台词爆点")

        world_rule = str(brief.get("world_rule", "")).strip()
        if world_rule and world_rule not in json.dumps(rows, ensure_ascii=False):
            anchor_index = min(len(rows) - 1, max(1, len(rows) // 2))
            rows[anchor_index]["画面内容"] = self._append_unique_text(str(rows[anchor_index].get("画面内容", "")), world_rule)
            if str(rows[anchor_index].get("台词对白", "")).strip() in {"", "—"}:
                rows[anchor_index]["对白"] = world_rule
                rows[anchor_index]["台词对白"] = world_rule
                rows[anchor_index]["对白角色"] = str(rows[anchor_index].get("对白角色", "旁白")).strip() or "旁白"
            rows[anchor_index]["节奏目的"] = self._append_unique_text(str(rows[anchor_index].get("节奏目的", "")), "规则落地")
            rows[anchor_index]["旁白"] = self._append_unique_text(str(rows[anchor_index].get("旁白", "")), world_rule)

    def _apply_feedback_notes(self, brief: dict[str, Any], rows: list[dict[str, Any]], feedback: list[str]) -> None:
        if not rows:
            return
        feedback_text = " ".join(feedback)
        if "情绪铺垫" in feedback_text:
            rows[0]["人物动作/神态"] = self._append_unique_text(str(rows[0].get("人物动作/神态", "")), brief["emotion"])
            focus_index = 1 if len(rows) > 1 else 0
            rows[focus_index]["画面内容"] = self._append_unique_text(str(rows[focus_index].get("画面内容", "")), f"情绪铺垫：{brief['summary']}")
            rows[focus_index]["节奏目的"] = self._append_unique_text(str(rows[focus_index].get("节奏目的", "")), "情绪铺垫")
        if "章节钩子" in feedback_text or "结尾反转" in feedback_text:
            rows[0]["节奏目的"] = "开场钩子"
            rows[-1]["节奏目的"] = "结尾反转/尾钩"
            if str(rows[-1].get("台词对白", "")).strip() in {"", "—"}:
                rows[-1]["对白"] = str(brief.get("memorable_line", "")).strip() or "未完待续"
                rows[-1]["台词对白"] = str(brief.get("memorable_line", "")).strip() or "未完待续"
            rows[-1]["画面内容"] = self._append_unique_text(str(rows[-1].get("画面内容", "")), "冲突余波与悬念停顿收束")
        if "名台词没有进入章节分镜" in feedback_text or "世界观规则表达偏弱" in feedback_text:
            self._ensure_storyboard_quality_anchors(brief, rows)

    def _append_unique_text(self, original: str, extra: str) -> str:
        base = (original or "").strip()
        addition = (extra or "").strip()
        if not addition:
            return base
        if not base:
            return addition
        if addition in base:
            return base
        return f"{base}；{addition}"

    def _condense_text(self, text: str, *, limit: int = 36) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip(" ，,；;。！？!?“”\"'")
        if not normalized:
            return ""
        parts = [item.strip(" ，,；;。！？!?“”\"'") for item in re.split(r"[。！？!?；;]+", normalized) if item.strip()]
        candidate = parts[0] if parts else normalized
        candidate = re.sub(r"\s+", " ", candidate).strip(" ，,；;。！？!?“”\"'")
        if len(candidate) <= limit:
            return candidate
        clause_parts = [item.strip(" ，,；;。！？!?：:\"'") for item in re.split(r"[，,：:、]+", candidate) if item.strip()]
        if clause_parts:
            candidate = clause_parts[0]
        if len(candidate) <= limit:
            return candidate
        return f"{candidate[: max(1, limit - 1)].rstrip(' ，,；;。！？!?')}…"

    def _compose_compact_text(self, *parts: str, limit: int = 40, max_parts: int = 2) -> str:
        items: list[str] = []
        for part in parts:
            compact = self._condense_text(part, limit=limit)
            if compact and compact not in items:
                items.append(compact)
            if len(items) >= max_parts:
                break
        joined = "，".join(items)
        if not joined:
            return ""
        if len(joined) <= limit:
            return joined
        return self._condense_text(joined, limit=limit)

    def _summarize_focus(self, text: str, *, fallback: str = "") -> str:
        compact = self._condense_text(text, limit=18)
        return compact or fallback

    def _build_story_chunks(self, source_text: str, brief: dict[str, Any]) -> list[str]:
        raw_text = source_text or brief["summary"]
        normalized = re.sub(r"\s+", " ", raw_text).strip()
        parts = [item.strip() for item in re.split(r"[。！？!?；;…]+", normalized) if item.strip()]
        chunks = [self._condense_text(item, limit=34) for item in parts[:8]]
        if brief.get("summary"):
            chunks.insert(0, self._condense_text(brief["summary"], limit=34))
        if brief.get("key_scene"):
            chunks.insert(0, self._condense_text(brief["key_scene"], limit=34))
        unique_chunks: list[str] = []
        for item in chunks:
            if item and item not in unique_chunks:
                unique_chunks.append(item)
        return unique_chunks[:6] or [self._condense_text(brief["summary"], limit=34)]

    def _pick_group_value(self, values: list[str], index: int, *, fallback: str) -> str:
        clean_values = [str(item).strip() for item in values if str(item).strip()]
        if not clean_values:
            return fallback
        return clean_values[index % len(clean_values)]

    def _build_stage_scene_label(self, brief: dict[str, Any], group_index: int, beat: str) -> str:
        focus = self._summarize_focus(str(brief.get("key_scene", "")).strip(), fallback=str(brief.get("summary", "")).strip())
        beat_label = self._summarize_focus(beat, fallback="关键段落")
        if beat_label and focus:
            return f"{beat_label} / {focus}"
        return beat_label or focus or "关键段落"

    def _build_group_content(self, brief: dict[str, Any], story_chunks: list[str], stage_block: dict[str, Any], group_index: int, local_index: int) -> str:
        beat = str(stage_block.get("beat", "推进"))
        chunk = story_chunks[min(group_index - 1 + local_index, len(story_chunks) - 1)]
        focus = self._summarize_focus(str(stage_block.get("focus", "")).strip(), fallback=beat)
        if beat == "开场钩子":
            return self._compose_compact_text(brief["key_scene"], focus, limit=38)
        if beat == "关系建立":
            return self._compose_compact_text(chunk, focus, limit=40)
        if beat == "冲突升级":
            base = brief.get("fidelity_notes") or chunk
            return self._compose_compact_text(str(base), focus, limit=40)
        if beat == "高潮前停顿":
            base = brief.get("world_rule") or brief["summary"]
            return self._compose_compact_text(str(base), "情绪压低，等待爆发", limit=38)
        if beat == "高潮":
            return self._compose_compact_text(brief["key_scene"], chunk, limit=38)
        return self._compose_compact_text(chunk, "余波与尾钩", limit=34)

    def _build_group_performance(self, brief: dict[str, Any], stage_block: dict[str, Any], group_index: int, local_index: int) -> str:
        beat = str(stage_block.get("beat", "推进"))
        emotion = brief["emotion"]
        if beat == "开场钩子":
            return f"{emotion}；先压后提，留出人物登场前的期待"
        if beat == "关系建立":
            return f"{emotion}；通过眼神和停顿建立人物关系"
        if beat == "冲突升级":
            return f"{emotion}；动作更明确，情绪开始外放"
        if beat == "高潮前停顿":
            return f"{emotion}；短暂停顿，强调爆发前的克制"
        if beat == "高潮":
            return f"{emotion}；情绪兑现，动作和表情顶到峰值"
        return f"{emotion}；余波未散，留下下一章悬念"

    def _build_group_dialogue_payload(self, brief: dict[str, Any], stage_block: dict[str, Any], group_index: int, local_index: int, group_count: int) -> dict[str, str]:
        beat = str(stage_block.get("beat", "推进"))
        memorable_line = str(brief.get("memorable_line", "")).strip()
        world_rule = str(brief.get("world_rule", "")).strip()
        content = self._build_group_content(brief, self._build_story_chunks("", brief), stage_block, group_index, local_index)
        speaker = self._resolve_dialogue_speaker(beat=beat, local_index=local_index, group_count=group_count)
        if beat == "高潮" and memorable_line:
            dialogue = memorable_line
        elif beat == "高潮前停顿" and world_rule:
            dialogue = world_rule
        elif beat == "关系建立":
            dialogue = "先别急着开口，让我确认这里到底哪里不对。"
        elif beat == "冲突升级":
            dialogue = "再退一步，局面就真的压不住了。"
        elif beat == "开场钩子" and local_index == 0:
            dialogue = "有人在看着我们。"
        elif beat == "尾钩" and local_index == group_count - 1:
            dialogue = "这件事，还没结束。"
        else:
            dialogue = "—"
        narration = self._build_group_narration(brief, beat, content)
        return {
            "speaker": speaker,
            "dialogue": dialogue,
            "narration": narration,
            "audio_design": self._build_group_audio_beat(beat),
        }

    def _build_group_dialogue(self, brief: dict[str, Any], stage_block: dict[str, Any], group_index: int, local_index: int, group_count: int) -> str:
        return self._build_group_dialogue_payload(brief, stage_block, group_index, local_index, group_count)["dialogue"]

    def _default_dialogue_speaker(self, beat: str) -> str:
        roles = self._story_role_characters()
        if beat in {"冲突升级", "高潮"} and roles.get("lead") is not None:
            return roles["lead"].name
        if beat == "关系建立" and roles.get("support") is not None:
            return roles["support"].name
        narrator = roles.get("narrator")
        return narrator.name if narrator is not None else ""

    def _resolve_dialogue_speaker(self, *, beat: str, local_index: int, group_count: int) -> str:
        roles = self._story_role_characters()
        lead = roles.get("lead")
        support = roles.get("support")
        rival = roles.get("rival")
        narrator = roles.get("narrator")
        if beat == "开场钩子":
            return lead.name if local_index == 0 and lead is not None else (narrator.name if narrator is not None else "")
        if beat == "关系建立":
            return support.name if local_index % 2 == 0 and support is not None else (lead.name if lead is not None else "")
        if beat == "冲突升级":
            return lead.name if local_index % 2 == 0 and lead is not None else (rival.name if rival is not None else "")
        if beat == "高潮前停顿":
            return ""
        if beat == "高潮":
            return lead.name if local_index < max(1, group_count - 1) and lead is not None else (rival.name if rival is not None else "")
        if beat == "尾钩":
            return lead.name if lead is not None else ""
        return self._default_dialogue_speaker(beat)

    def _build_group_audio_beat(self, beat: str) -> str:
        mapping = {
            "开场钩子": "低频氛围先行，人物声后入，制造未知压迫感",
            "关系建立": "环境底噪压低，让对白和呼吸声更贴近",
            "冲突升级": "拟音前推，脚步、撞击和鼓点同步抬升",
            "高潮前停顿": "抽离鼓点，只保留呼吸、布料和空间残响",
            "高潮": "对白、旁白与重击音齐推，形成情绪兑现",
            "尾钩": "音乐收束后留下短暂停顿和尾音残响",
        }
        return mapping.get(beat, "环境声与情绪音乐平衡推进")

    def _build_group_narration(self, brief: dict[str, Any], beat: str, content: str) -> str:
        scene = self._compose_compact_text(content, brief.get("summary", ""), limit=36)
        if beat == "开场钩子":
            return f"{scene}，危险先于答案降临。"
        if beat == "关系建立":
            return f"{scene}，人物关系在停顿里逐步成形。"
        if beat == "冲突升级":
            return f"{scene}，局面开始失控，情绪被一步步顶高。"
        if beat == "高潮前停顿":
            return f"{scene}，所有人都在等那个无法回避的结果。"
        if beat == "高潮":
            return f"{scene}，压抑至此终于兑现成正面碰撞。"
        return f"{scene}，余波未散，新的悬念已经落下。"

    def _build_group_roles(self, brief: dict[str, Any], stage_block: dict[str, Any]) -> str:
        beat = str(stage_block.get("beat", "推进"))
        if beat in {"高潮", "冲突升级"}:
            return self._append_unique_text(self.source_title, "核心冲突角色")
        if beat == "关系建立":
            return self._append_unique_text(self.source_title, "主要人物关系")
        return self.source_title

    def _build_group_audio(self, stage_block: dict[str, Any], group_index: int, local_index: int) -> str:
        beat = str(stage_block.get("beat", "推进"))
        focus = self._summarize_focus(str(stage_block.get("audio_focus", "氛围环境声")).strip(), fallback="氛围环境声")
        audio_map = {
            "开场钩子": "环境声铺场，人物延后入场",
            "关系建立": "对白和环境声并行",
            "冲突升级": "重点拟音前推，鼓点抬升",
            "高潮前停顿": "抽掉鼓点，保留呼吸停顿",
            "高潮": "重击音和配乐齐推",
            "尾钩": "尾音停顿，留钩子",
        }
        if beat == "高潮":
            return audio_map[beat]
        if beat == "尾钩":
            return audio_map[beat]
        return audio_map.get(beat, focus or "氛围环境声")

    def _build_group_music(self, brief: dict[str, Any], stage_block: dict[str, Any], group_index: int) -> str:
        beat = str(stage_block.get("beat", "推进"))
        emotion = brief["emotion"]
        music_map = {
            "开场钩子": f"{emotion}；底色先压住",
            "关系建立": f"{emotion}；配乐轻铺关系线",
            "冲突升级": f"{emotion}；鼓点逐步抬升",
            "高潮前停顿": f"{emotion}；低频压住，给爆发留空间",
            "高潮": f"{emotion}；配乐上扬，强化兑现感",
            "尾钩": f"{emotion}；收束后保留悬念余音",
        }
        if beat == "高潮前停顿":
            return music_map[beat]
        if beat == "高潮":
            return music_map[beat]
        if beat == "尾钩":
            return music_map[beat]
        return music_map.get(beat, emotion)

    def _build_audio_plan(self, brief: dict[str, Any], storyboard_rows: list[dict[str, Any]]) -> dict[str, Any]:
        asset_lock = self._current_asset_lock()
        timing_windows = self._build_voice_timing_windows(storyboard_rows)
        mix_profile = {
            "dialogue_priority": 100,
            "narration_priority": 60,
            "ambience_priority": 20,
            "ducking": {
                "narration_when_dialogue": 0.4,
                "ambience_when_dialogue": 0.6,
            },
            "ambience_gain": 0.18,
        }
        cue_sheet: list[dict[str, Any]] = []
        narration_tracks: list[dict[str, Any]] = []
        dialogue_tracks: list[dict[str, Any]] = []
        voice_script_lines: list[str] = []
        last_narration = ""
        last_dialogue_pair: tuple[str, str] | None = None
        narrator_character = asset_lock.narrator_character()
        narration_budget = max(1, math.ceil(len(storyboard_rows) / 3))
        for row in storyboard_rows:
            shot_no = self._row_shot_no(row)
            shot_window = timing_windows.get(
                shot_no,
                {
                    "start_seconds": 0.0,
                    "duration_seconds": self._row_duration(row),
                    "end_seconds": self._row_duration(row),
                },
            )
            shot_start = float(shot_window["start_seconds"])
            shot_duration = max(1.0, float(shot_window["duration_seconds"]))
            shot_end = float(shot_window["end_seconds"])
            narration = self._row_narration(row)
            dialogue = self._row_dialogue(row)
            speaker = self._row_dialogue_speaker(row)
            speaker_character = asset_lock.resolve_character(speaker)
            has_dialogue = dialogue and dialogue not in {"-", "—", "无"}
            generated_narration = self._build_group_narration(brief, self._row_pace(row), self._row_content(row))
            narration_is_auto_fill = narration == generated_narration
            world_rule_text = str(brief.get("world_rule") or "").strip()
            contains_world_rule = bool(world_rule_text and world_rule_text in narration)
            keep_narration = bool(narration and narration not in {"-", "—", "无"}) and (
                not has_dialogue
                or not narration_is_auto_fill
                or shot_no == 1
                or self._row_pace(row) in {"开场钩子", "高潮前停顿", "结尾反转/尾钩", "尾钩"}
                or contains_world_rule
            )
            if has_dialogue and narration_is_auto_fill and shot_no not in {1, len(storyboard_rows)}:
                narration = ""
            if (
                keep_narration
                and has_dialogue
                and len(narration_tracks) >= narration_budget
                and not contains_world_rule
                and self._row_pace(row) not in {"高潮前停顿", "结尾反转/尾钩", "尾钩"}
            ):
                narration = ""
                keep_narration = False
            cue_sheet.append(
                {
                    "shot": shot_no,
                    "duration_seconds": shot_duration,
                    "beat": self._row_pace(row),
                    "narration": narration,
                    "dialogue": dialogue,
                    "speaker": speaker,
                    "canonical_character": speaker_character.name if speaker_character else None,
                    "voice_id": speaker_character.voice_id if speaker_character else None,
                    "sfx": str(row.get("音效", "氛围环境声")),
                    "music": str(row.get("音乐", brief["emotion"])),
                    "audio_design": str(row.get("音频设计", self._build_group_audio_beat(self._row_pace(row)))),
                }
            )
            narration_track: dict[str, Any] | None = None
            if keep_narration and narration and narration not in {"-", "—", "无"}:
                if narration != last_narration:
                    narration_target = min(
                        max(1.0, self._estimate_voice_duration(narration)),
                        max(1.0, shot_duration * (0.45 if has_dialogue else 0.7)),
                    )
                    narration_track = {
                        "shot": shot_no,
                        "text": narration,
                        "canonical_character": narrator_character.name if narrator_character else "旁白",
                        "voice_id": narrator_character.voice_id if narrator_character else None,
                        "start_seconds": round(shot_start, 3),
                        "target_duration_seconds": round(narration_target, 3),
                        "end_seconds": round(shot_start + narration_target, 3),
                        "track_role": "narration",
                        "bus": "narration_bus",
                        "priority": mix_profile["narration_priority"],
                        "duck_target": "dialogue_bus",
                        "mix_gain": 0.96,
                    }
                    narration_tracks.append(narration_track)
                    voice_script_lines.append(f"旁白：{narration}")
                    last_narration = narration
            if dialogue and dialogue not in {"-", "—", "无"}:
                dialogue_pair = (speaker, dialogue)
                if dialogue_pair != last_dialogue_pair:
                    dialogue_start = shot_start
                    if narration_track is not None and not narration_is_auto_fill:
                        dialogue_start = max(
                            shot_start,
                            min(shot_end - 0.8, float(narration_track["end_seconds"]) + 0.2),
                        )
                    dialogue_target = min(
                        max(1.0, self._estimate_voice_duration(dialogue)),
                        max(1.0, shot_end - dialogue_start),
                    )
                    dialogue_tracks.append(
                        {
                            "shot": shot_no,
                            "speaker": speaker,
                            "text": dialogue,
                            "canonical_character": speaker_character.name if speaker_character else None,
                            "voice_id": speaker_character.voice_id if speaker_character else None,
                            "start_seconds": round(dialogue_start, 3),
                            "target_duration_seconds": round(dialogue_target, 3),
                            "end_seconds": round(dialogue_start + dialogue_target, 3),
                            "track_role": "dialogue",
                            "bus": "dialogue_bus",
                            "priority": mix_profile["dialogue_priority"],
                            "duck_target": "",
                            "mix_gain": 1.0,
                        }
                    )
                    voice_script_lines.append(f"{speaker}：{dialogue}")
                    last_dialogue_pair = dialogue_pair

        if not narration_tracks:
            fallback_narration = self._condense_text(brief["summary"], limit=48) or brief["summary"]
            fallback_target = min(
                max(1.5, self._estimate_voice_duration(fallback_narration)),
                max(2.0, float(self.target_duration_seconds) * 0.4),
            )
            narration_tracks.append(
                {
                    "shot": 1,
                    "text": fallback_narration,
                    "canonical_character": narrator_character.name if narrator_character else "旁白",
                    "voice_id": narrator_character.voice_id if narrator_character else None,
                    "start_seconds": 0.0,
                    "target_duration_seconds": round(fallback_target, 3),
                    "end_seconds": round(fallback_target, 3),
                    "track_role": "narration",
                    "bus": "narration_bus",
                    "priority": mix_profile["narration_priority"],
                    "duck_target": "dialogue_bus",
                    "mix_gain": 0.96,
                }
            )
            voice_script_lines.append(f"旁白：{fallback_narration}")

        if not dialogue_tracks and brief.get("memorable_line"):
            memorable_line = str(brief["memorable_line"]).strip()
            lead_character = asset_lock.lead_character()
            shot_index = max(0, len(storyboard_rows) // 2 - 1)
            shot_no = max(1, len(storyboard_rows) // 2)
            if storyboard_rows:
                shot_no = self._row_shot_no(storyboard_rows[shot_index])
            shot_window = timing_windows.get(
                shot_no,
                {
                    "start_seconds": max(0.0, float(self.target_duration_seconds) / 2.0 - 1.5),
                    "duration_seconds": 3.0,
                    "end_seconds": max(3.0, float(self.target_duration_seconds) / 2.0 + 1.5),
                },
            )
            dialogue_target = min(
                max(1.2, self._estimate_voice_duration(memorable_line)),
                max(1.2, float(shot_window["duration_seconds"])),
            )
            dialogue_tracks.append(
                {
                    "shot": shot_no,
                    "speaker": lead_character.name if lead_character else "",
                    "text": memorable_line,
                    "canonical_character": lead_character.name if lead_character else None,
                    "voice_id": lead_character.voice_id if lead_character else None,
                    "start_seconds": round(float(shot_window["start_seconds"]), 3),
                    "target_duration_seconds": round(dialogue_target, 3),
                    "end_seconds": round(float(shot_window["start_seconds"]) + dialogue_target, 3),
                    "track_role": "dialogue",
                    "bus": "dialogue_bus",
                    "priority": mix_profile["dialogue_priority"],
                    "duck_target": "",
                    "mix_gain": 1.0,
                }
            )
            voice_script_lines.append(f"{lead_character.name if lead_character else '角色'}：{memorable_line}")

        voice_script_lines = self._dedupe_preserve_order(voice_script_lines)
        narration_script = "\n".join(track["text"] for track in narration_tracks if track.get("text")).strip()
        voice_script = "\n".join(line for line in voice_script_lines if line).strip() or narration_script
        voice_tracks = sorted(
            [*narration_tracks, *dialogue_tracks],
            key=lambda item: (
                float(item.get("start_seconds", 0.0) or 0.0),
                0 if item.get("track_role") == "narration" else 1,
                int(item.get("shot", 0) or 0),
            ),
        )
        return {
            "render_mode": "timeline_multitrack",
            "voice_style": narrator_character.voice_id if narrator_character and narrator_character.voice_id else DEFAULT_TTS_VOICE,
            "music_mood": brief["emotion"],
            "mix_profile": mix_profile,
            "total_duration_seconds": round(sum(float(self._row_duration(row)) for row in storyboard_rows), 3),
            "sfx": [{"shot": row["shot"], "cue": row["sfx"]} for row in cue_sheet],
            "cue_sheet": cue_sheet,
            "narration_tracks": narration_tracks,
            "dialogue_tracks": dialogue_tracks,
            "voice_tracks": voice_tracks,
            "voice_track_count": len(voice_tracks),
            "voice_script": voice_script,
            "narration_script": narration_script or voice_script,
        }

    def _build_voice_timing_windows(self, storyboard_rows: list[dict[str, Any]]) -> dict[int, dict[str, float]]:
        cursor = 0.0
        windows: dict[int, dict[str, float]] = {}
        for row in storyboard_rows:
            shot_no = self._row_shot_no(row)
            duration = max(1.0, self._row_duration(row))
            windows[shot_no] = {
                "start_seconds": round(cursor, 3),
                "duration_seconds": round(duration, 3),
                "end_seconds": round(cursor + duration, 3),
            }
            cursor += duration
        return windows

    def _estimate_voice_duration(self, text: str) -> float:
        content = re.sub(r"\s+", "", str(text or "").strip())
        if not content:
            return 1.0
        return min(8.0, max(1.0, len(content) * 0.28 + 0.6))

    def _collect_voice_tracks(self, audio_plan: dict[str, Any], fallback_voice: str) -> list[dict[str, Any]]:
        tracks_payload = audio_plan.get("voice_tracks")
        if isinstance(tracks_payload, list) and tracks_payload:
            raw_tracks = [item for item in tracks_payload if isinstance(item, dict)]
        else:
            raw_tracks = [
                *[item for item in audio_plan.get("narration_tracks", []) if isinstance(item, dict)],
                *[item for item in audio_plan.get("dialogue_tracks", []) if isinstance(item, dict)],
            ]
        collected: list[dict[str, Any]] = []
        for index, item in enumerate(raw_tracks, start=1):
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            track = dict(item)
            track["text"] = text
            track["track_role"] = str(track.get("track_role") or ("narration" if "speaker" not in track else "dialogue")).strip() or "dialogue"
            track["voice_id"] = str(track.get("voice_id") or fallback_voice or DEFAULT_TTS_VOICE).strip() or DEFAULT_TTS_VOICE
            track["canonical_character"] = str(track.get("canonical_character") or track.get("speaker") or track["track_role"]).strip()
            track["start_seconds"] = round(float(track.get("start_seconds") or 0.0), 3)
            track["target_duration_seconds"] = round(
                max(1.0, float(track.get("target_duration_seconds") or self._estimate_voice_duration(text))),
                3,
            )
            track["end_seconds"] = round(track["start_seconds"] + track["target_duration_seconds"], 3)
            track["track_index"] = int(track.get("track_index") or index)
            track["bus"] = str(track.get("bus") or ("narration_bus" if track["track_role"] == "narration" else "dialogue_bus")).strip()
            track["priority"] = int(track.get("priority") or (60 if track["track_role"] == "narration" else 100))
            track["duck_target"] = str(track.get("duck_target") or ("dialogue_bus" if track["track_role"] == "narration" else "")).strip()
            track["mix_gain"] = float(track.get("mix_gain") or (0.96 if track["track_role"] == "narration" else 1.0))
            collected.append(track)
        return sorted(
            collected,
            key=lambda item: (
                float(item.get("start_seconds", 0.0) or 0.0),
                0 if item.get("track_role") == "narration" else 1,
                int(item.get("track_index", 0) or 0),
            ),
        )

    def _dedupe_preserve_order(self, lines: list[str]) -> list[str]:
        deduped: list[str] = []
        for line in lines:
            clean = str(line or "").strip()
            if not clean:
                continue
            if deduped and deduped[-1] == clean:
                continue
            deduped.append(clean)
        return deduped

    def _synthesize_voiceover(self, narration_text: dict[str, Any] | str, output_path: Path, voice_style: str = DEFAULT_TTS_VOICE) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(narration_text, dict):
            audio_plan = narration_text
            fallback_voice = str(audio_plan.get("voice_style") or voice_style or DEFAULT_TTS_VOICE).strip() or DEFAULT_TTS_VOICE
            voice_tracks = self._collect_voice_tracks(audio_plan, fallback_voice)
            audio_plan["render_mode"] = str(audio_plan.get("render_mode") or "timeline_multitrack")
            if audio_plan["render_mode"] != "timeline_multitrack":
                combined_text = str(audio_plan.get("voice_script") or audio_plan.get("narration_script") or "").strip()
                self._synthesize_voiceover(combined_text, output_path, fallback_voice)
                return
            if not voice_tracks:
                duration_seconds = max(2, int(round(float(audio_plan.get("total_duration_seconds") or 2.0))))
                self._generate_silence_mp3(output_path, duration_seconds=duration_seconds)
                audio_plan["voice_tracks"] = []
                audio_plan["voice_track_count"] = 0
                return
            rendered_dir = output_path.parent / "voice_tracks"
            rendered_dir.mkdir(parents=True, exist_ok=True)
            rendered_tracks: list[dict[str, Any]] = []
            try:
                for track in voice_tracks:
                    track_stem = self._sanitize_track_file_stem(
                        f"{int(track['track_index']):02d}_{track['track_role']}_{track['canonical_character']}"
                    )
                    track_output_path = rendered_dir / f"{track_stem}.mp3"
                    self._render_track_audio(track=track, output_path=track_output_path)
                    rendered_track = dict(track)
                    rendered_track["output_path"] = str(track_output_path)
                    rendered_tracks.append(rendered_track)
                self._mix_timeline_voice_tracks(rendered_tracks=rendered_tracks, output_path=output_path)
                audio_plan["voice_tracks"] = rendered_tracks
                audio_plan["voice_track_count"] = len(rendered_tracks)
                return
            except Exception as exc:
                self.provider_notes.append(f"多角色配音混音回退为静音音轨：{exc}")
                duration_seconds = max(2, int(round(float(audio_plan.get("total_duration_seconds") or 6.0))))
                self._generate_silence_mp3(output_path, duration_seconds=duration_seconds)
                return
        try:
            import edge_tts

            async def _save() -> None:
                await edge_tts.Communicate(narration_text, voice_style or DEFAULT_TTS_VOICE).save(str(output_path))

            asyncio.run(_save())
        except Exception as exc:
            self.provider_notes.append(f"旁白回退为静音音轨：{exc}")
            self._generate_silence_mp3(output_path, duration_seconds=max(6, len(narration_text) // 12))

    def _render_track_audio(self, *, track: dict[str, Any], output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        source_path = output_path.with_name(f"{output_path.stem}_raw.mp3")
        voice_id = str(track.get("voice_id") or DEFAULT_TTS_VOICE).strip() or DEFAULT_TTS_VOICE
        text = str(track.get("text") or "").strip()
        target_duration_seconds = max(1.0, float(track.get("target_duration_seconds") or self._estimate_voice_duration(text)))
        try:
            import edge_tts

            async def _save() -> None:
                await edge_tts.Communicate(text, voice_id).save(str(source_path))

            asyncio.run(_save())
            self._fit_track_audio_to_duration(
                source_path=source_path,
                output_path=output_path,
                target_duration_seconds=target_duration_seconds,
            )
        except Exception as exc:
            self.provider_notes.append(
                f"分轨配音回退为静音音轨：{track.get('canonical_character', 'track')} -> {exc}"
            )
            self._generate_silence_mp3(output_path, duration_seconds=max(1, int(math.ceil(target_duration_seconds))))
        finally:
            source_path.unlink(missing_ok=True)

    def _probe_media_duration(self, media_path: Path) -> float:
        if not media_path.exists():
            return 0.0
        if Path(self.ffprobe_exe).exists():
            try:
                command = [
                    self.ffprobe_exe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(media_path),
                ]
                result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                return max(0.0, float((result.stdout or "").strip() or 0.0))
            except Exception:
                return 0.0
        return 0.0

    def _build_atempo_filter_chain(self, ratio: float) -> str:
        ratio = max(0.25, float(ratio))
        filters: list[str] = []
        while ratio > 2.0:
            filters.append("atempo=2.0")
            ratio /= 2.0
        while ratio < 0.5:
            filters.append("atempo=0.5")
            ratio /= 0.5
        filters.append(f"atempo={ratio:.4f}")
        return ",".join(filters)

    def _fit_track_audio_to_duration(self, *, source_path: Path, output_path: Path, target_duration_seconds: float) -> None:
        actual_duration = self._probe_media_duration(source_path)
        if actual_duration <= 0.0 or target_duration_seconds <= 0.0 or abs(actual_duration - target_duration_seconds) <= 0.2:
            shutil.copyfile(source_path, output_path)
            return
        ratio = actual_duration / target_duration_seconds
        command = [
            self.ffmpeg_exe,
            "-y",
            "-i",
            str(source_path),
            "-filter:a",
            self._build_atempo_filter_chain(ratio),
            "-q:a",
            "4",
            "-acodec",
            "libmp3lame",
            str(output_path),
        ]
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _mix_timeline_voice_tracks(self, *, rendered_tracks: list[dict[str, Any]], output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not rendered_tracks:
            self._generate_silence_mp3(output_path, duration_seconds=2)
            return
        command = [self.ffmpeg_exe, "-y"]
        filter_parts: list[str] = []
        narration_inputs: list[str] = []
        dialogue_inputs: list[str] = []
        for index, track in enumerate(rendered_tracks):
            command.extend(["-i", str(track["output_path"])])
            delay_ms = max(0, int(round(float(track.get("start_seconds") or 0.0) * 1000)))
            gain = float(track.get("mix_gain") or 1.0)
            bus = str(track.get("bus") or ("narration_bus" if track.get("track_role") == "narration" else "dialogue_bus")).strip()
            label = f"a{index}"
            filter_parts.append(f"[{index}:a]volume={gain:.3f},adelay={delay_ms}|{delay_ms}[{label}]")
            if bus == "narration_bus":
                narration_inputs.append(f"[{label}]")
            else:
                dialogue_inputs.append(f"[{label}]")

        if dialogue_inputs:
            filter_parts.append(f"{''.join(dialogue_inputs)}amix=inputs={len(dialogue_inputs)}:duration=longest:normalize=0[dialogue_bus]")
        if narration_inputs:
            filter_parts.append(f"{''.join(narration_inputs)}amix=inputs={len(narration_inputs)}:duration=longest:normalize=0[narration_bus]")

        if dialogue_inputs and narration_inputs:
            filter_parts.append("[dialogue_bus]asplit=2[dialogue_duck][dialogue_mix]")
            filter_parts.append("[narration_bus][dialogue_duck]sidechaincompress=threshold=0.02:ratio=8:attack=10:release=250[narration_ducked]")
            filter_parts.append("[dialogue_mix][narration_ducked]amix=inputs=2:duration=longest:normalize=0[aout]")
        elif dialogue_inputs:
            filter_parts.append("[dialogue_bus]anull[aout]")
        else:
            filter_parts.append("[narration_bus]anull[aout]")
        command.extend(
            [
                "-filter_complex",
                ";".join(filter_parts),
                "-map",
                "[aout]",
                "-q:a",
                "4",
                "-acodec",
                "libmp3lame",
                str(output_path),
            ]
        )
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _sanitize_track_file_stem(self, value: str) -> str:
        cleaned = re.sub(r"[^\w\-]+", "_", str(value or "").strip(), flags=re.UNICODE).strip("_")
        return cleaned or "track"

    def _generate_ambience(self, output_path: Path, duration_seconds: float, storyboard_rows: list[dict[str, Any]]) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = 22050
        frame_count = max(1, int(duration_seconds * sample_rate))
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            for index in range(frame_count):
                t = index / sample_rate
                base = math.sin(2 * math.pi * 110 * t) * 0.08 + math.sin(2 * math.pi * 220 * t) * 0.03
                pulse = 0.0
                if storyboard_rows:
                    shot = storyboard_rows[min(int((t / duration_seconds) * len(storyboard_rows)), len(storyboard_rows) - 1)]
                    pulse = 0.03 if shot["节奏目的"] in {"高潮", "尾钩"} else 0.01
                value = int(max(-1.0, min(1.0, base + pulse)) * 32767)
                wav_file.writeframesraw(struct.pack("<h", value))

    def _render_chapter_video(self, storyboard_rows: list[dict[str, Any]], keyframe_images: list[Path], output_path: Path, brief: dict[str, Any], voiceover_path: Path, ambience_path: Path) -> None:
        silent_path = output_path.with_name("chapter_preview_silent.mp4")
        writer = imageio.get_writer(silent_path, fps=DEFAULT_FPS, codec="libx264")
        try:
            for row in storyboard_rows:
                image_path = keyframe_images[min((int(row["镜头号"]) - 1) * len(keyframe_images) // max(1, len(storyboard_rows)), len(keyframe_images) - 1)]
                frame_count = max(1, int(float(row["时长(s)"]) * DEFAULT_FPS))
                for frame_index in range(frame_count):
                    progress = frame_index / max(1, frame_count - 1)
                    writer.append_data(self._compose_frame(image_path=image_path, row=row, brief=brief, progress=progress))
        finally:
            writer.close()
        self._mux_audio(silent_path, voiceover_path, ambience_path, output_path)
        silent_path.unlink(missing_ok=True)

    def _compose_frame(self, *, image_path: Path, row: dict[str, Any], brief: dict[str, Any], progress: float) -> np.ndarray:
        canvas = Image.open(image_path).convert("RGB").resize((1280, 720))
        draw = ImageDraw.Draw(canvas)
        header_font = self.load_font(size=24)
        body_font = self.load_font(size=30)
        subtitle_font = self.load_font(size=28)
        draw.rounded_rectangle((32, 24, 1248, 88), radius=18, fill=(8, 12, 20))
        draw.text((56, 40), f"第{brief['chapter']:02d}章 {brief['title']} | 镜头 {row['镜头号']:02d} | {row['节奏目的']}", font=header_font, fill=(245, 245, 245))
        overlay = f"{row['画面内容']} | {row['人物动作/神态']}"
        for offset, line in enumerate(textwrap.wrap(overlay, width=24)[:2]):
            draw.text((56, 560 + offset * 34), line, font=body_font, fill=(255, 245, 228))
        if row["台词对白"] not in {"", "—"}:
            draw.rounded_rectangle((80, 630, 1200, 700), radius=16, fill=(0, 0, 0))
            draw.text((110, 650), row["台词对白"], font=subtitle_font, fill=(255, 255, 255))
        return np.array(canvas)

    def _mux_audio(self, silent_video: Path, voiceover: Path, ambience: Path, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self.ffmpeg_exe,
            "-y",
            "-i",
            str(silent_video),
            "-i",
            str(voiceover),
            "-i",
            str(ambience),
            "-filter_complex",
            "[1:a]volume=1.0,asplit=2[voice_duck][voice_mix];"
            "[2:a]volume=0.18[ambience_bus];"
            "[ambience_bus][voice_duck]sidechaincompress=threshold=0.02:ratio=6:attack=8:release=300[ambience_ducked];"
            "[voice_mix][ambience_ducked]amix=inputs=2:duration=longest:normalize=0[aout]",
            "-map",
            "0:v:0",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(output_path),
        ]
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _concat_videos(self, video_paths: list[Path], output_path: Path) -> None:
        concat_file = output_path.with_suffix(".txt")
        concat_file.write_text("\n".join(f"file '{path.as_posix()}'" for path in video_paths), encoding="utf-8")
        command = [self.ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(output_path)]
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        concat_file.unlink(missing_ok=True)

    def _build_preview_gif_from_video(self, video_path: Path, output_path: Path) -> None:
        reader = imageio.get_reader(video_path)
        frames = []
        try:
            for index, frame in enumerate(reader):
                if index % max(1, int(reader.get_meta_data().get("fps", 12) // 3)) == 0:
                    frames.append(frame)
                if len(frames) >= 18:
                    break
        finally:
            reader.close()
        imageio.mimsave(output_path, frames or [np.zeros((720, 1280, 3), dtype=np.uint8)], duration=0.28)

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

    def _build_chapter_preview_html(self, brief: dict[str, Any], rows: list[dict[str, Any]], keyframe_images: list[Path]) -> str:
        image_tiles = "\n".join(f"<li><img src=\"../images/{path.name}\" alt=\"{path.name}\" style=\"width:100%\"></li>" for path in keyframe_images)
        shot_items = "\n".join(f"<li>镜头{row['镜头号']:02d}｜{row['时长(s)']}s｜{row['画面内容']}</li>" for row in rows)
        return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>第{brief['chapter']:02d}章预览</title></head><body><h1>第{brief['chapter']:02d}章：{brief['title']}</h1><video src="chapter_preview.mp4" controls style="width:100%;max-width:960px"></video><h2>关键帧</h2><ul style="display:grid;grid-template-columns:repeat(2,1fr);gap:16px;list-style:none;padding:0">{image_tiles}</ul><h2>镜头清单</h2><ol>{shot_items}</ol></body></html>"""

    def _build_preview_html(self) -> str:
        cards = []
        for item in self.chapter_packages:
            chapter = item["chapter"]
            cards.append(f"<li><a href=\"../chapters/chapter_{chapter:02d}/preview/index.html\">第{chapter:02d}章：{item['title']}</a> | <a href=\"../chapters/chapter_{chapter:02d}/delivery/chapter_final_cut.mp4\">交付视频</a></li>")
        return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>{self.source_title} 漫剧预览</title></head><body><h1>{self.source_title}</h1><video src="preview.mp4" controls style="width:100%;max-width:1080px"></video><h2>章节交付</h2><ol>{''.join(cards)}</ol></body></html>"""

    def _build_chapter_qa_markdown(self, brief: dict[str, Any], qa_rounds: list[dict[str, Any]], final_review: dict[str, Any]) -> str:
        lines = [f"# 第{brief['chapter']:02d}章 QA 报告", "", f"- 结论：{'通过' if final_review['passed'] else '未通过'}", f"- 综合评分：{final_review['overall']}", ""]
        for item in qa_rounds:
            lines.append(f"## Round {item['round']}")
            lines.append(f"- 通过：{item['passed']}")
            lines.append(f"- 分数：{json.dumps(item['scores'], ensure_ascii=False)}")
            if item["issues"]:
                lines.extend([f"- 问题：{issue}" for issue in item["issues"]])
            if item["blockers"]:
                lines.extend([f"- 阻塞：{issue}" for issue in item["blockers"]])
            lines.append("")
        return "\n".join(lines)

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
                    "asset_lock": self._asset_lock_summary(),
                    "artifacts": sorted(set(artifact_paths)),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

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

    def _select_keyframe_rows(self, storyboard_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ranked = sorted(
            storyboard_rows,
            key=lambda item: (self._row_priority(item), self._row_duration(item)),
            reverse=True,
        )
        keyframe_override = next(
            (
                int(row.get("blueprint_keyframe_count") or 0)
                for row in storyboard_rows
                if int(row.get("blueprint_keyframe_count") or 0) > 0
            ),
            0,
        )
        keyframe_count = max(
            1,
            keyframe_override or int(getattr(self, "keyframe_count", DEFAULT_KEYFRAME_COUNT) or DEFAULT_KEYFRAME_COUNT),
        )
        selected = ranked[:keyframe_count]
        return selected or storyboard_rows[:keyframe_count]

    def _build_keyframe_prompt(self, brief: dict[str, Any], row: dict[str, Any]) -> str:
        asset_lock = self._current_asset_lock()
        locked_characters = asset_lock.resolve_many(self._row_present_characters(row))
        prompt_parts = [
            f"Chinese cinematic manga keyframe for {self.source_title} chapter {brief['chapter']}",
            self._row_content(row),
            f"Scene {self._row_scene(row)}",
            f"Shot size {self._row_size(row)}",
            f"Camera cue {self._row_movement(row)}",
            f"Acting {self._row_performance(row)}",
            f"Style {self.visual_style}",
        ]
        if asset_lock.scene_baseline_prompt:
            prompt_parts.append(f"Scene baseline: {asset_lock.scene_baseline_prompt}")
        if locked_characters:
            prompt_parts.append(
                "Character locks: "
                + " | ".join(
                    f"{character.name}: {character.fixed_prompt}"
                    for character in locked_characters
                    if character.fixed_prompt
                )
            )
        prompt_parts.append("Preserve original character motivations and world rules.")
        return ". ".join(part for part in prompt_parts if part).strip()

    def _generate_keyframes(self, images_dir: Path, brief: dict[str, Any], keyframe_rows: list[dict[str, Any]]) -> tuple[list[str], list[Path]]:
        prompts: list[str] = []
        paths: list[Path] = []
        for index, row in enumerate(keyframe_rows, start=1):
            prompt = self._build_keyframe_prompt(brief, row)
            output_path = images_dir / f"keyframe_{index:02d}.png"
            if self.provider is not None:
                try:
                    self.provider.generate_image_to_file(
                        prompt=prompt,
                        output_path=output_path,
                        width=1024,
                        height=1024,
                        image_model=self.keyframe_image_model,
                    )
                    self.real_image_count += 1
                except Exception as exc:
                    self.provider_notes.append(f"章节 {brief['chapter']} 关键帧回退：{exc}")
                    self.write_placeholder_image(
                        output_path=output_path,
                        title=f"{self.source_title} 第{brief['chapter']}章",
                        subtitle=self._row_content(row) or str(brief.get("key_scene", "")),
                        size=(1024, 1024),
                    )
            else:
                self.write_placeholder_image(
                    output_path=output_path,
                    title=f"{self.source_title} 第{brief['chapter']}章",
                    subtitle=self._row_content(row) or str(brief.get("key_scene", "")),
                    size=(1024, 1024),
                )
            prompts.append(prompt)
            paths.append(output_path)
        return prompts, paths

    def _build_video_segment_prompt(self, brief: dict[str, Any], row: dict[str, Any]) -> str:
        parts = [
            f"{self.source_title} cinematic manga adaptation",
            self._row_content(row),
            f"Shot size {self._row_size(row)}",
            f"Camera motion {self._row_movement(row)}",
            f"Performance {self._row_performance(row)}",
            f"Pacing goal {self._row_pace(row)}",
            "cinematic manga motion, natural character acting, preserve world logic",
            "no chapter labels, no scene captions, no timestamps, no storyboard text overlay in frame",
        ]
        dialogue = self._row_dialogue(row)
        if dialogue and dialogue not in {"-", "—", "无", "鏃"}:
            parts.append(f"Keep dialogue mood: {dialogue}")
        return ". ".join(part for part in parts if part)

    def _build_video_plan(
        self,
        *,
        brief: dict[str, Any],
        storyboard_rows: list[dict[str, Any]],
        keyframe_rows: list[dict[str, Any]],
        keyframe_images: list[Path],
        total_duration: float,
        video_dir: Path,
    ) -> dict[str, Any]:
        segments_dir = video_dir / "segments"
        segments_dir.mkdir(parents=True, exist_ok=True)
        keyframe_lookup = {self._row_shot_no(row): idx for idx, row in enumerate(keyframe_rows)}

        assets: list[dict[str, Any]] = []
        for index, row in enumerate(keyframe_rows, start=1):
            image_path = keyframe_images[min(index - 1, len(keyframe_images) - 1)]
            clip_path = segments_dir / f"keyframe_motion_{index:02d}.mp4"
            assets.append(
                {
                    "asset_id": f"keyframe_{index:02d}",
                    "shot_no": self._row_shot_no(row),
                    "image_index": index - 1,
                    "image_path": str(image_path),
                    "clip_path": str(clip_path),
                    "prompt": self._build_video_segment_prompt(brief, row),
                    "render_mode": "ark_i2v" if self.provider is not None and self.use_real_images else "local_pan",
                    "render_duration_seconds": REAL_VIDEO_SEGMENT_SECONDS,
                    "status": "pending",
                }
            )

        segments: list[dict[str, Any]] = []
        asset_count = max(1, len(keyframe_images))
        for row in storyboard_rows:
            shot_no = self._row_shot_no(row)
            image_index = min((shot_no - 1) * asset_count // max(1, len(storyboard_rows)), asset_count - 1)
            asset = assets[min(image_index, len(assets) - 1)] if assets else None
            if shot_no in keyframe_lookup and assets:
                asset = assets[keyframe_lookup[shot_no]]
            image_path = keyframe_images[min(image_index, len(keyframe_images) - 1)]
            segments.append(
                {
                    "segment_id": f"shot_{shot_no:02d}",
                    "shot_no": shot_no,
                    "duration_seconds": self._row_duration(row),
                    "image_path": str(image_path),
                    "asset_id": asset["asset_id"] if asset else None,
                    "source_kind": "ark_i2v" if asset and asset["render_mode"] == "ark_i2v" else "local_pan",
                    "source_video_path": asset["clip_path"] if asset else "",
                    "prompt": self._build_video_segment_prompt(brief, row),
                    "render_status": "pending",
                    "row": row,
                }
            )

        return {
            "chapter": int(brief["chapter"]),
            "title": str(brief["title"]),
            "target_duration_seconds": round(float(total_duration), 2),
            "assets": assets,
            "segments": segments,
            "summary": {
                "requested_real_video": bool(self.provider is not None and self.use_real_images),
                "asset_count": len(assets),
                "segment_count": len(segments),
                "real_asset_success_count": 0,
                "real_segment_count": 0,
                "local_segment_count": len(segments),
                "fallback_ratio": 1.0 if segments else 0.0,
            },
        }

    def _render_real_video_assets(self, *, brief: dict[str, Any], video_plan: dict[str, Any]) -> None:
        assets = video_plan.get("assets", [])
        if not assets:
            return

        total_assets = len(assets)
        chapter_no = int(brief.get("chapter", 0) or 0)
        for index, asset in enumerate(assets, start=1):
            self._report_progress(
                "chapter_packaging",
                f"第 {chapter_no:02d} 章《{brief['title']}》正在生成视频资产 {index}/{total_assets}",
            )
            if asset.get("render_mode") != "ark_i2v" or self.provider is None:
                asset["status"] = "local_only"
                continue

            try:
                self.provider.generate_video_to_file(
                    asset.get("prompt", ""),
                    Path(asset["clip_path"]),
                    image_paths=[Path(asset["image_path"])],
                    image_roles=["first_frame"],
                    video_model=self.video_model,
                    duration_seconds=int(asset.get("render_duration_seconds", REAL_VIDEO_SEGMENT_SECONDS)),
                    ratio="16:9",
                    resolution="720p",
                    generate_audio=False,
                    return_last_frame=True,
                    camera_fixed=False,
                    draft=False,
                    max_wait_seconds=REAL_VIDEO_ASSET_MAX_WAIT_SECONDS,
                    poll_interval_seconds=REAL_VIDEO_ASSET_POLL_INTERVAL_SECONDS,
                )
                self.real_video_count += 1
                asset["status"] = "succeeded"
                asset["provider_details"] = dict(self.provider.last_video_task_details)
                self._report_progress(
                    "chapter_packaging",
                    f"第 {chapter_no:02d} 章《{brief['title']}》视频资产 {index}/{total_assets} 已完成",
                )
            except Exception as exc:
                asset["status"] = "fallback_local"
                asset["error"] = str(exc)
                self.provider_notes.append(f"章节 {brief['chapter']} 图生视频回退：{exc}")
                self._report_progress(
                    "chapter_packaging",
                    f"第 {chapter_no:02d} 章《{brief['title']}》视频资产 {index}/{total_assets} 回退为本地镜头",
                )
                self.requirement_miner.record_incident(
                    title="图生视频链路发生回退",
                    summary=f"章节 {brief['chapter']} 的关键帧视频资产未生成成功，已回退到本地镜头动画。",
                    area="video_generation",
                    suggested_change="把图生视频失败视为显式需求，持续补强模型回退、任务诊断和 QA 门禁。",
                    severity="high",
                    dedupe_key="manga.video_i2v_fallback",
                    context={
                        "chapter": int(brief["chapter"]),
                        "asset_id": asset.get("asset_id"),
                        "error": str(exc),
                        "video_model": self.video_model,
                    },
                    related_files=[
                        str(Path(__file__)),
                        str((ROOT_DIR / "shared" / "providers" / "ark.py")),
                    ],
                )

        asset_map = {str(asset.get("asset_id")): asset for asset in assets}
        for segment in video_plan.get("segments", []):
            asset = asset_map.get(str(segment.get("asset_id")))
            if not asset or asset.get("status") != "succeeded":
                segment["source_kind"] = "local_pan"
                segment["render_status"] = "fallback_local"
                segment["source_video_path"] = ""
            else:
                segment["source_kind"] = "ark_i2v"
                segment["render_status"] = "succeeded"
                segment["source_video_path"] = asset.get("clip_path", "")

        total_segments = len(video_plan.get("segments", []))
        real_asset_success_count = sum(1 for asset in assets if asset.get("status") == "succeeded")
        real_segment_count = sum(1 for segment in video_plan.get("segments", []) if segment.get("source_kind") == "ark_i2v")
        local_segment_count = max(0, total_segments - real_segment_count)
        video_plan.setdefault("summary", {}).update(
            {
                "real_asset_success_count": real_asset_success_count,
                "real_segment_count": real_segment_count,
                "local_segment_count": local_segment_count,
                "fallback_ratio": round(local_segment_count / total_segments, 4) if total_segments else 0.0,
            }
        )

    def _render_chapter_video(
        self,
        video_plan: dict[str, Any],
        output_path: Path,
        brief: dict[str, Any],
        voiceover_path: Path,
        ambience_path: Path,
    ) -> None:
        self._render_real_video_assets(brief=brief, video_plan=video_plan)
        silent_path = output_path.with_name("chapter_preview_silent.mp4")
        writer = imageio.get_writer(silent_path, fps=DEFAULT_FPS, codec="libx264")
        try:
            for segment in video_plan.get("segments", []):
                row = segment.get("row", {})
                duration_seconds = float(segment.get("duration_seconds", 3.0) or 3.0)
                if segment.get("source_kind") == "ark_i2v" and str(segment.get("source_video_path", "")).strip():
                    self._append_video_segment_frames(
                        writer=writer,
                        source_video_path=Path(str(segment["source_video_path"])),
                        fallback_image_path=Path(str(segment["image_path"])),
                        target_duration_seconds=duration_seconds,
                        row=row,
                        brief=brief,
                    )
                else:
                    self._append_local_segment_frames(
                        writer=writer,
                        image_path=Path(str(segment["image_path"])),
                        target_duration_seconds=duration_seconds,
                        row=row,
                        brief=brief,
                    )
        finally:
            writer.close()
        self._mux_audio(silent_path, voiceover_path, ambience_path, output_path)
        silent_path.unlink(missing_ok=True)

    def _append_local_segment_frames(
        self,
        *,
        writer,
        image_path: Path,
        target_duration_seconds: float,
        row: dict[str, Any],
        brief: dict[str, Any],
    ) -> None:
        frame_count = max(1, int(target_duration_seconds * DEFAULT_FPS))
        for frame_index in range(frame_count):
            progress = frame_index / max(1, frame_count - 1)
            writer.append_data(self._compose_frame(image_path=image_path, row=row, brief=brief, progress=progress))

    def _append_video_segment_frames(
        self,
        *,
        writer,
        source_video_path: Path,
        fallback_image_path: Path,
        target_duration_seconds: float,
        row: dict[str, Any],
        brief: dict[str, Any],
    ) -> None:
        if not source_video_path.exists():
            self._append_local_segment_frames(
                writer=writer,
                image_path=fallback_image_path,
                target_duration_seconds=target_duration_seconds,
                row=row,
                brief=brief,
            )
            return

        reader = imageio.get_reader(source_video_path)
        sampled_frames: list[np.ndarray] = []
        try:
            meta = reader.get_meta_data()
            src_fps = float(meta.get("fps", DEFAULT_FPS) or DEFAULT_FPS)
            stride = max(1, int(round(src_fps / DEFAULT_FPS)))
            for index, frame in enumerate(reader):
                if index % stride == 0:
                    sampled_frames.append(frame)
            if not sampled_frames:
                for frame in reader:
                    sampled_frames.append(frame)
                    break
        finally:
            reader.close()

        if not sampled_frames:
            self._append_local_segment_frames(
                writer=writer,
                image_path=fallback_image_path,
                target_duration_seconds=target_duration_seconds,
                row=row,
                brief=brief,
            )
            return

        target_frame_count = max(1, int(target_duration_seconds * DEFAULT_FPS))
        for frame_index in range(target_frame_count):
            progress = frame_index / max(1, target_frame_count - 1)
            frame = sampled_frames[frame_index % len(sampled_frames)]
            writer.append_data(self._compose_frame_from_array(frame=frame, row=row, brief=brief, progress=progress))

    def _compose_frame(self, *, image_path: Path, row: dict[str, Any], brief: dict[str, Any], progress: float) -> np.ndarray:
        canvas = Image.open(image_path).convert("RGB")
        canvas = self._apply_motion_transform(canvas=canvas, movement=self._row_movement(row), progress=progress)
        canvas = canvas.resize((1280, 720))
        return self._overlay_frame(canvas=canvas, row=row, brief=brief)

    def _compose_frame_from_array(self, *, frame: np.ndarray, row: dict[str, Any], brief: dict[str, Any], progress: float) -> np.ndarray:
        canvas = Image.fromarray(frame).convert("RGB")
        canvas = self._apply_motion_transform(canvas=canvas, movement=self._row_movement(row), progress=progress * 0.35)
        canvas = canvas.resize((1280, 720))
        return self._overlay_frame(canvas=canvas, row=row, brief=brief)

    def _apply_motion_transform(self, *, canvas: Image.Image, movement: str, progress: float) -> Image.Image:
        width, height = canvas.size
        normalized = str(movement or "").lower()
        zoom_in = any(token in normalized for token in ("推", "zoom in", "push"))
        zoom_out = any(token in normalized for token in ("拉", "zoom out", "pull"))
        pan = any(token in normalized for token in ("移", "pan", "track"))
        tilt = any(token in normalized for token in ("摇", "tilt", "swivel"))

        if zoom_in:
            zoom = 1.0 + 0.08 * progress
        elif zoom_out:
            zoom = 1.08 - 0.08 * progress
        else:
            zoom = 1.02 + 0.03 * progress

        crop_w = max(1, int(width / zoom))
        crop_h = max(1, int(height / zoom))
        max_x = max(0, width - crop_w)
        max_y = max(0, height - crop_h)
        if pan:
            left = int(max_x * progress)
        else:
            left = int(max_x * 0.5)
        if tilt:
            top = int(max_y * progress * 0.7)
        else:
            top = int(max_y * 0.5)
        box = (left, top, min(width, left + crop_w), min(height, top + crop_h))
        return canvas.crop(box)

    def _overlay_frame(self, *, canvas: Image.Image, row: dict[str, Any], brief: dict[str, Any]) -> np.ndarray:
        draw = ImageDraw.Draw(canvas)
        subtitle_font = self.load_font(size=28)
        dialogue = self._row_dialogue(row)
        if dialogue not in {"", "鈥?", "-", "—"}:
            speaker = self._row_dialogue_speaker(row)
            subtitle = f"{speaker}：{dialogue}" if speaker not in {"", "旁白"} else dialogue
            lines = textwrap.wrap(subtitle, width=30)[:2] or [subtitle]
            box_height = 34 * len(lines) + 38
            top = 700 - box_height
            draw.rounded_rectangle((72, top, 1208, 700), radius=18, fill=(0, 0, 0))
            for offset, line in enumerate(lines):
                draw.text((108, top + 18 + offset * 34), line, font=subtitle_font, fill=(255, 255, 255))
        return np.array(canvas)

    def _probe_video_metadata(self, video_path: Path) -> dict[str, float | int]:
        if Path(self.ffprobe_exe).exists():
            command = [
                self.ffprobe_exe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=avg_frame_rate,nb_frames,duration,width,height",
                "-of",
                "json",
                str(video_path),
            ]
            result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            payload = json.loads(result.stdout or "{}")
            stream = (payload.get("streams") or [{}])[0]
            fps_text = str(stream.get("avg_frame_rate", "0/1"))
            fps_parts = fps_text.split("/", 1)
            fps = float(fps_parts[0]) / max(1.0, float(fps_parts[1])) if len(fps_parts) == 2 else float(fps_text or 0)
            nb_frames = int(stream.get("nb_frames") or 0)
            duration = float(stream.get("duration") or 0.0)
            return {
                "fps": fps or float(DEFAULT_FPS),
                "frame_count": nb_frames if nb_frames > 0 else int(duration * (fps or DEFAULT_FPS)),
                "duration_seconds": duration,
                "width": int(stream.get("width") or 0),
                "height": int(stream.get("height") or 0),
            }

        reader = imageio.get_reader(video_path)
        try:
            meta = reader.get_meta_data()
            fps = float(meta.get("fps", DEFAULT_FPS) or DEFAULT_FPS)
            duration = float(meta.get("duration") or 0.0)
            raw_nframes = meta.get("nframes")
            frame_count = 0
            try:
                nframes_value = float(raw_nframes)
                if math.isfinite(nframes_value) and nframes_value > 0:
                    frame_count = int(nframes_value)
            except (TypeError, ValueError):
                frame_count = 0
            if frame_count <= 0 and math.isfinite(duration):
                frame_count = int(max(0.0, duration * fps))
            return {
                "fps": fps,
                "frame_count": frame_count,
                "duration_seconds": duration,
                "width": int(meta.get("size", (0, 0))[0]),
                "height": int(meta.get("size", (0, 0))[1]),
            }
        finally:
            reader.close()

    def _analyze_video_motion(self, video_path: Path) -> dict[str, float | int]:
        reader = imageio.get_reader(video_path)
        sampled: list[np.ndarray] = []
        try:
            meta = reader.get_meta_data()
            fps = float(meta.get("fps", DEFAULT_FPS) or DEFAULT_FPS)
            stride = max(1, int(round(fps / 3)))
            for index, frame in enumerate(reader):
                if index % stride == 0:
                    sampled.append(frame.astype(np.float32))
                if len(sampled) >= 24:
                    break
        finally:
            reader.close()

        if len(sampled) < 2:
            return {"motion_score": 0.0, "sampled_frames": len(sampled)}

        diffs = []
        for prev, current in zip(sampled, sampled[1:]):
            diffs.append(float(np.mean(np.abs(current - prev)) / 255.0))
        return {"motion_score": round(float(np.mean(diffs)), 6), "sampled_frames": len(sampled)}

    def _review_final(
        self,
        brief: dict[str, Any],
        storyboard_rows: list[dict[str, Any]],
        plan_review: dict[str, Any],
        preview_video: Path,
        delivery_video: Path,
        voiceover: Path,
        storyboard_xlsx: Path,
        video_plan_path: Path,
        video_plan: dict[str, Any],
    ) -> dict[str, Any]:
        blockers = list(plan_review["blockers"])
        issues = list(plan_review["issues"])
        dialogue_count = len([row for row in storyboard_rows if self._row_dialogue(row) not in {"", "-", "—", "无"}])
        narration_count = len([row for row in storyboard_rows if self._row_narration(row) not in {"", "-", "—", "无"}])
        polluted_scene_rows = [
            self._row_shot_no(row)
            for row in storyboard_rows
            if re.search(r"第\d+章|第\d+组|\d+秒|scene|chapter", self._row_scene(row), flags=re.IGNORECASE)
        ]
        if not preview_video.exists() or not delivery_video.exists():
            blockers.append("章节视频缺失")
        if not storyboard_xlsx.exists():
            blockers.append("章节分镜交付缺失")
        if not voiceover.exists():
            blockers.append("章节旁白缺失")
        if not video_plan_path.exists():
            blockers.append("章节视频计划缺失")
        if dialogue_count <= 0:
            blockers.append("章节对白缺失")
        if narration_count <= 0:
            blockers.append("章节旁白文案缺失")
        if polluted_scene_rows:
            blockers.append("分镜场景字段仍包含章节/时间字卡污染")

        expected_duration = round(sum(self._row_duration(row) for row in storyboard_rows), 2)
        preview_meta = self._probe_video_metadata(preview_video) if preview_video.exists() else {"duration_seconds": 0.0, "frame_count": 0, "fps": 0.0}
        delivery_meta = self._probe_video_metadata(delivery_video) if delivery_video.exists() else {"duration_seconds": 0.0, "frame_count": 0, "fps": 0.0}
        motion = self._analyze_video_motion(preview_video) if preview_video.exists() else {"motion_score": 0.0, "sampled_frames": 0}
        actual_duration = float(preview_meta.get("duration_seconds", 0.0) or 0.0)
        delivery_duration = float(delivery_meta.get("duration_seconds", 0.0) or 0.0)
        motion_score = float(motion.get("motion_score", 0.0) or 0.0)
        summary = dict(video_plan.get("summary", {}))

        if actual_duration < max(30.0, expected_duration * 0.7):
            blockers.append("章节视频时长明显不足")
        elif abs(actual_duration - expected_duration) > max(12.0, expected_duration * 0.25):
            issues.append("章节视频时长与分镜计划偏差较大")
        if abs(actual_duration - delivery_duration) > 1.5:
            blockers.append("预览视频与交付视频时长不一致")
        if motion_score < VIDEO_MOTION_SCORE_THRESHOLD:
            blockers.append("章节视频运动性不足，接近静态拼片")

        requested_real_video = bool(summary.get("requested_real_video"))
        real_asset_success_count = int(summary.get("real_asset_success_count", 0) or 0)
        fallback_ratio = float(summary.get("fallback_ratio", 0.0) or 0.0)
        if requested_real_video and real_asset_success_count <= 0:
            blockers.append("已启用真图模式，但未生成任何真实图生视频片段")
        elif requested_real_video and fallback_ratio > REAL_VIDEO_FALLBACK_WARNING_RATIO:
            issues.append("真实视频片段回退比例偏高")

        passed = not blockers and plan_review["passed"]
        summary_text = f"第{int(brief['chapter']):02d}章{'通过' if passed else '未通过'} QA"
        return {
            "passed": passed,
            "overall": plan_review["overall"],
            "scores": plan_review["scores"],
            "issues": issues,
            "blockers": blockers,
            "summary": summary_text,
            "expected_duration_seconds": expected_duration,
            "preview_duration_seconds": round(actual_duration, 2),
            "delivery_duration_seconds": round(delivery_duration, 2),
            "motion_score": round(motion_score, 6),
            "real_asset_success_count": real_asset_success_count,
            "real_segment_count": int(summary.get("real_segment_count", 0) or 0),
            "local_segment_count": int(summary.get("local_segment_count", 0) or 0),
            "fallback_ratio": round(fallback_ratio, 4),
            "dialogue_count": dialogue_count,
            "narration_count": narration_count,
            "polluted_scene_rows": polluted_scene_rows,
        }

    def _resolve_target_duration(self, payload: dict[str, Any]) -> float | None:
        raw = payload.get("target_duration_seconds")
        if raw in (None, ""):
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        return max(20.0, min(180.0, value))

    def _unique_texts(self, values: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for value in values:
            raw = str(value or "").strip()
            item = self._condense_text(raw, limit=48)
            tail = raw[-1] if raw else ""
            if tail and re.match(r"[。！？!?]", tail) and item and not item.endswith(("。", "！", "？", "!", "?")):
                item = f"{item}{tail}"
            if not item or item in seen:
                continue
            seen.add(item)
            unique.append(item)
        return unique

    def _resolve_story_duration_target(self, rows: list[dict[str, Any]]) -> float:
        if self.target_duration_seconds is not None:
            return round(self.target_duration_seconds, 1)
        suggested_total = sum(self._suggest_row_duration(row) for row in rows)
        return round(max(MIN_CHAPTER_DURATION_SECONDS, min(MAX_CHAPTER_DURATION_SECONDS, suggested_total)), 1)

    def _suggest_row_duration(self, row: dict[str, Any]) -> float:
        narration = self._row_narration(row)
        dialogue = self._row_dialogue(row)
        content = self._row_content(row)
        beat = self._row_pace(row)
        spoken_chars = len(narration) + len(dialogue)
        visual_chars = len(content)
        reading_seconds = spoken_chars / 8.5 if spoken_chars else 0.0
        visual_seconds = max(0.0, visual_chars / 18.0)
        base = max(2.8, self._row_duration(row))
        beat_bonus = {
            "寮€鍦洪挬瀛?": 0.4,
            "鍏崇郴寤虹珛": 0.5,
            "鍐茬獊鍗囩骇": 0.7,
            "楂樻疆鍓嶅仠椤?": 0.8,
            "楂樻疆": 1.0,
            "灏鹃挬": 0.6,
        }.get(beat, 0.3)
        duration = max(base, 2.6 + reading_seconds * 0.55 + visual_seconds * 0.35 + beat_bonus)
        return round(max(2.5, min(9.5, duration)), 1)

    def _rebalance_storyboard_durations(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        target_duration = self._resolve_story_duration_target(rows)
        durations = [self._suggest_row_duration(row) for row in rows]
        current_total = sum(durations)
        if target_duration and current_total > 0:
            scale = target_duration / current_total
            durations = [round(max(2.5, min(9.5, duration * scale)), 1) for duration in durations]
            delta = round(target_duration - sum(durations), 1)
            durations[-1] = round(max(2.5, durations[-1] + delta), 1)
        self._reflow_storyboard_timing(rows, durations)

    def _normalize_storyboard_text_key(self, text: str) -> str:
        normalized = re.sub(r"\s+", "", str(text or "").lower())
        normalized = re.sub(r"[，。！？、,.!?:：;；'\"“”‘’\\-_/|]", "", normalized)
        return normalized[:48]

    def _build_variation_hint(self, brief: dict[str, Any], row: dict[str, Any], index: int, duplicate_count: int) -> str:
        beat = self._row_pace(row)
        beat_variants = {
            "开场钩子": [
                "墙上符纹再次闪动",
                "病房里的异样开始扩散",
            ],
            "关系建立": [
                "视线切到同伴表情变化",
                "人物关系压进前景",
            ],
            "冲突升级": [
                "压迫感继续逼近",
                "空间已经开始失控",
            ],
            "高潮前停顿": [
                "所有人屏住呼吸",
                "危险显形前短暂停住",
            ],
            "高潮": [
                "异兆正面压到人物面前",
                "冲突终于正面兑现",
            ],
            "结尾反转/尾钩": [
                "余波里留下新悬念",
                "病房异兆并没有结束",
            ],
        }
        selected_beat = next((key for key in beat_variants if key in beat), "")
        candidates = [
            item
            for item in [
                str(brief.get("key_scene", "")).strip() if selected_beat in {"开场钩子", "高潮"} else "",
                str(brief.get("world_rule", "")).strip() if selected_beat in {"关系建立", "高潮前停顿"} else "",
                beat_variants.get(selected_beat, [""])[(duplicate_count - 2) % max(1, len(beat_variants.get(selected_beat, [""])))],
                str(brief.get("summary", "")).strip() if selected_beat in {"结尾反转/尾钩"} else "",
            ]
            if item
        ]
        candidate = candidates[(duplicate_count - 2) % len(candidates)] if candidates else ""
        return self._condense_text(candidate, limit=28) or f"{beat}新变化"

    def _build_variation_performance(self, brief: dict[str, Any], row: dict[str, Any], duplicate_count: int) -> str:
        beat = self._row_pace(row) or "推进"
        emotion = str(brief.get("emotion", "")).strip()
        variants = [
            "眼神先扫环境，再回到人物反应",
            "动作重心从环境切到人物判断",
            "把停顿拉长半拍，制造前后拍差",
            "视线落点切到新的压力源",
        ]
        note = variants[(duplicate_count - 2) % len(variants)]
        detail = f"{beat}层次变化：{note}"
        if emotion and emotion not in detail:
            detail = f"{detail}，情绪保持{emotion}"
        return self._append_unique_text(self._row_performance(row), detail)

    def _contains_meta_direction_phrase(self, text: str) -> bool:
        normalized = str(text or "").strip()
        if not normalized:
            return False
        meta_phrases = (
            "别停在同一个反应上",
            "继续往前推",
            "这一拍别复述",
            "画面没变，但人物立场已经变了",
            "把焦点切到另一个受压点",
            "层次变化",
            "第2层反应",
            "细节变化",
        )
        return any(phrase in normalized for phrase in meta_phrases)

    def _build_variation_dialogue(self, brief: dict[str, Any], row: dict[str, Any], duplicate_count: int) -> str:
        beat = self._row_pace(row)
        memorable_line = str(brief.get("memorable_line", "")).strip()
        world_rule = str(brief.get("world_rule", "")).strip()
        speaker = self._row_dialogue_speaker(row)
        if "高潮前停顿" in beat and world_rule:
            return world_rule
        if "高潮" in beat and "停顿" not in beat and memorable_line:
            return memorable_line
        narrator_variants = {
            "开场钩子": [
                "墙上的符纹又亮了一次。",
                "异样不是错觉，它就在墙面上。",
            ],
            "关系建立": [
                "两个人都意识到，病房里还有第三种东西。",
                "沉默越久，病房里的异常越像真的。",
            ],
            "冲突升级": [
                "压迫感继续逼近，退路已经不多了。",
                "再拖下去，病房里迟早会失控。",
            ],
            "高潮前停顿": [
                "所有人都在等它真正现身。",
                "空气安静得只剩下呼吸声。",
            ],
            "高潮": [
                "那道异兆终于正面压了过来。",
                "病房里的异常，在这一刻彻底失控。",
            ],
            "结尾反转/尾钩": [
                memorable_line or "这件事，还没结束。",
                "余波没散，真正的问题才刚开始。",
            ],
        }
        dialogue_variants = {
            "开场钩子": [
                "别出声，墙上那东西又动了。",
                "先别回头，看墙上。",
            ],
            "关系建立": [
                "先别急，我还没看清它到底是什么。",
                "你也看见了，对吧？",
            ],
            "冲突升级": [
                "再逼一步，谁都收不了场。",
                "你再靠近试试，后果你担不起。",
            ],
            "高潮前停顿": [
                "等等，它还没真正现身。",
                "先别动，听它会从哪边来。",
            ],
            "高潮": [
                memorable_line or "现在退已经晚了。",
                "来了，别再退。",
            ],
            "结尾反转/尾钩": [
                memorable_line or "这件事，还没结束。",
                "别松气，真正的麻烦还在后面。",
            ],
        }
        variant_pool = narrator_variants if speaker == "旁白" else dialogue_variants
        selected_beat = next((key for key in variant_pool if key in beat), "关系建立")
        variants = [item for item in variant_pool[selected_beat] if item]
        return variants[(duplicate_count - 2) % len(variants)]

    def _diversify_storyboard_rows(self, brief: dict[str, Any], rows: list[dict[str, Any]]) -> None:
        seen_visuals: dict[str, int] = {}
        movement_cycle = ["缓推", "平移", "定镜", "微摇", "突推", "切入定镜"]
        size_cycle = ["近景", "中景", "中近景", "特写", "双人中景", "大全景"]
        for index, row in enumerate(rows):
            normalized_key = self._normalize_storyboard_text_key(self._row_content(row))
            if not normalized_key:
                continue
            seen_visuals[normalized_key] = seen_visuals.get(normalized_key, 0) + 1
            duplicate_count = seen_visuals[normalized_key]
            if duplicate_count <= 1:
                continue
            content = self._append_unique_text(
                self._row_content(row),
                self._build_variation_hint(brief, row, index, duplicate_count),
            )
            performance = self._build_variation_performance(brief, row, duplicate_count)
            movement = movement_cycle[index % len(movement_cycle)]
            shot_size = size_cycle[index % len(size_cycle)]

            row["画面内容"] = content
            row["content"] = content
            row["人物动作/神态"] = performance
            row["performance"] = performance
            row["镜头运动"] = movement
            row["camera_move"] = movement
            row["镜头景别"] = shot_size
            row["shot_size"] = shot_size

            if self._row_dialogue(row) in {"", "-", "—", "无"}:
                dialogue = self._build_variation_dialogue(brief, row, duplicate_count)
                row["对白"] = dialogue
                row["台词对白"] = dialogue
                row["dialogue"] = dialogue

    def _append_video_segment_frames(
        self,
        *,
        writer,
        source_video_path: Path,
        fallback_image_path: Path,
        target_duration_seconds: float,
        row: dict[str, Any],
        brief: dict[str, Any],
    ) -> None:
        if not source_video_path.exists():
            self._append_local_segment_frames(
                writer=writer,
                image_path=fallback_image_path,
                target_duration_seconds=target_duration_seconds,
                row=row,
                brief=brief,
            )
            return

        reader = imageio.get_reader(source_video_path)
        sampled_frames: list[np.ndarray] = []
        try:
            meta = reader.get_meta_data()
            src_fps = float(meta.get("fps", DEFAULT_FPS) or DEFAULT_FPS)
            stride = max(1, int(round(src_fps / DEFAULT_FPS)))
            for index, frame in enumerate(reader):
                if index % stride == 0:
                    sampled_frames.append(frame)
            if not sampled_frames:
                for frame in reader:
                    sampled_frames.append(frame)
                    break
        finally:
            reader.close()

        if not sampled_frames:
            self._append_local_segment_frames(
                writer=writer,
                image_path=fallback_image_path,
                target_duration_seconds=target_duration_seconds,
                row=row,
                brief=brief,
            )
            return

        target_frame_count = max(1, int(target_duration_seconds * DEFAULT_FPS))
        if len(sampled_frames) == 1:
            stretched_frames = sampled_frames * target_frame_count
        else:
            stretched_frames = []
            for frame_index in range(target_frame_count):
                progress = frame_index / max(1, target_frame_count - 1)
                source_index = min(len(sampled_frames) - 1, int(round(progress * (len(sampled_frames) - 1))))
                stretched_frames.append(sampled_frames[source_index])

        for frame_index, frame in enumerate(stretched_frames):
            progress = frame_index / max(1, len(stretched_frames) - 1)
            writer.append_data(self._compose_frame_from_array(frame=frame, row=row, brief=brief, progress=progress))


    def _review_final(
        self,
        brief: dict[str, Any],
        storyboard_rows: list[dict[str, Any]],
        plan_review: dict[str, Any],
        preview_video: Path,
        delivery_video: Path,
        voiceover: Path,
        storyboard_xlsx: Path,
        video_plan_path: Path,
        video_plan: dict[str, Any],
    ) -> dict[str, Any]:
        blockers = list(plan_review["blockers"])
        issues = list(plan_review["issues"])
        dialogue_count = len([row for row in storyboard_rows if self._row_dialogue(row) not in {"", "-", "无", "空"}])
        narration_count = len([row for row in storyboard_rows if self._row_narration(row) not in {"", "-", "无", "空"}])
        polluted_scene_rows = [
            self._row_shot_no(row)
            for row in storyboard_rows
            if re.search(r"第\d+章|第\d+组|scene|chapter|\d+:\d+", self._row_scene(row), flags=re.IGNORECASE)
        ]
        if not preview_video.exists() or not delivery_video.exists():
            blockers.append("章节预览或交付视频缺失")
        if not storyboard_xlsx.exists():
            blockers.append("章节分镜表缺失")
        if not voiceover.exists():
            blockers.append("章节配音文件缺失")
        if not video_plan_path.exists():
            blockers.append("章节视频计划文件缺失")
        if dialogue_count <= 0:
            blockers.append("章节缺少对白")
        if narration_count <= 0:
            blockers.append("章节缺少旁白")
        if polluted_scene_rows:
            blockers.append("分镜场景字段混入章节号、分组号或时间标签")

        expected_duration = round(sum(self._row_duration(row) for row in storyboard_rows), 2)
        target_duration = self._resolve_story_duration_target(storyboard_rows)
        lower_bound = max(MIN_CHAPTER_DURATION_SECONDS, target_duration * 0.75)
        upper_bound = min(MAX_CHAPTER_DURATION_SECONDS + 20.0, target_duration * 1.25)
        preview_meta = self._probe_video_metadata(preview_video) if preview_video.exists() else {"duration_seconds": 0.0, "frame_count": 0, "fps": 0.0}
        delivery_meta = self._probe_video_metadata(delivery_video) if delivery_video.exists() else {"duration_seconds": 0.0, "frame_count": 0, "fps": 0.0}
        motion = self._analyze_video_motion(preview_video) if preview_video.exists() else {"motion_score": 0.0, "sampled_frames": 0}
        actual_duration = float(preview_meta.get("duration_seconds", 0.0) or 0.0)
        delivery_duration = float(delivery_meta.get("duration_seconds", 0.0) or 0.0)
        motion_score = float(motion.get("motion_score", 0.0) or 0.0)
        summary = dict(video_plan.get("summary", {}))

        if actual_duration < lower_bound:
            blockers.append("成片时长低于当前章节内容可支撑的下限")
        elif actual_duration > upper_bound:
            issues.append("成片时长明显超出当前章节内容支撑范围")
        elif abs(actual_duration - expected_duration) > max(10.0, expected_duration * 0.25):
            issues.append("成片时长与分镜预估时长偏差较大")
        if abs(actual_duration - delivery_duration) > 1.5:
            blockers.append("预览视频与交付视频时长不一致")
        if motion_score < VIDEO_MOTION_SCORE_THRESHOLD:
            blockers.append("成片运动变化不足")

        requested_real_video = bool(summary.get("requested_real_video"))
        real_asset_success_count = int(summary.get("real_asset_success_count", 0) or 0)
        fallback_ratio = float(summary.get("fallback_ratio", 0.0) or 0.0)
        if requested_real_video and real_asset_success_count <= 0:
            blockers.append("已启用真图模式，但未生成任何真实图生视频片段")
        elif requested_real_video and fallback_ratio > REAL_VIDEO_FALLBACK_WARNING_RATIO:
            issues.append("图生视频片段回退比例偏高")

        passed = not blockers and plan_review["passed"]
        summary_text = f"第{int(brief['chapter']):02d}章{'通过' if passed else '未通过'} QA"
        return {
            "passed": passed,
            "overall": plan_review["overall"],
            "scores": plan_review["scores"],
            "issues": issues,
            "blockers": blockers,
            "summary": summary_text,
            "expected_duration_seconds": expected_duration,
            "preview_duration_seconds": round(actual_duration, 2),
            "delivery_duration_seconds": round(delivery_duration, 2),
            "motion_score": round(motion_score, 6),
            "real_asset_success_count": real_asset_success_count,
            "real_segment_count": int(summary.get("real_segment_count", 0) or 0),
            "local_segment_count": int(summary.get("local_segment_count", 0) or 0),
            "fallback_ratio": round(fallback_ratio, 4),
            "dialogue_count": dialogue_count,
            "narration_count": narration_count,
            "polluted_scene_rows": polluted_scene_rows,
        }

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
    def _review_plan(self, brief: dict[str, Any], storyboard_rows: list[dict[str, Any]], audio_plan: dict[str, Any]) -> dict[str, Any]:
        asset_lock = self._current_asset_lock()
        joined = json.dumps(storyboard_rows, ensure_ascii=False)
        blockers: list[str] = []
        issues: list[str] = []
        dialogue_count = len(audio_plan.get("dialogue_tracks", []))
        narration_count = len(audio_plan.get("narration_tracks", []))
        cue_sheet = audio_plan.get("cue_sheet", [])
        meaningful_speakers = {
            str(track.get("speaker") or "").strip()
            for track in audio_plan.get("dialogue_tracks", [])
            if str(track.get("speaker") or "").strip() not in {"", "无", "空", "旁白"}
        }
        voice_script = str(audio_plan.get("voice_script") or "").strip()
        if brief.get("memorable_line") and str(brief["memorable_line"]).strip() not in joined:
            blockers.append("名台词没有进入章节分镜")
        if brief.get("world_rule") and str(brief["world_rule"]).strip() not in joined:
            issues.append("世界观规则表达偏弱")
        if not cue_sheet:
            blockers.append("音频 cue sheet 缺失")
        if dialogue_count <= 0:
            blockers.append("章节对白缺失")
        if narration_count <= 0:
            blockers.append("章节旁白缺失")
        if dialogue_count > 0 and not meaningful_speakers:
            blockers.append("章节对白没有有效角色承载")
        if narration_count > 0 and "旁白：" not in voice_script:
            blockers.append("voice_script 缺少旁白台本")
        if dialogue_count > 0 and not any(f"{speaker}：" in voice_script for speaker in meaningful_speakers):
            blockers.append("voice_script 缺少角色对白台本")
        if asset_lock.validation_errors:
            blockers.append("资产锁引用路径无效")
        meta_direction_found = any(
            self._contains_meta_direction_phrase(text)
            for text in [voice_script, *[self._row_dialogue(row) for row in storyboard_rows], *[self._row_narration(row) for row in storyboard_rows]]
        )
        if meta_direction_found:
            blockers.append("对白或旁白混入制作指令，破坏成片沉浸感")
        unresolved_present_rows = [
            self._row_shot_no(row)
            for row in storyboard_rows
            if not self._row_present_characters(row)
        ]
        if unresolved_present_rows:
            blockers.append("出镜角色缺失或无法归一")
        generic_speaker_rows = [
            self._row_shot_no(row)
            for row in storyboard_rows
            if self._row_dialogue_speaker(row) in {"主角", "同伴", "对手"}
        ]
        if asset_lock.exists and generic_speaker_rows:
            blockers.append("分镜对白角色仍停留在泛槽位，没有直达真实角色")
        unmapped_dialogue_tracks = [
            track
            for track in audio_plan.get("dialogue_tracks", [])
            if str(track.get("speaker") or "").strip() not in {"", "无", "空", "旁白"}
            and (
                not str(track.get("canonical_character") or "").strip()
                or not str(track.get("voice_id") or "").strip()
            )
        ]
        if unmapped_dialogue_tracks:
            blockers.append("对白角色无法映射到音色")
        generic_canonical_tracks = [
            track
            for track in audio_plan.get("dialogue_tracks", [])
            if str(track.get("canonical_character") or "").strip() in {"", "主角", "同伴", "对手"}
        ]
        if asset_lock.exists and generic_canonical_tracks:
            blockers.append("audio_plan 仍存在 generic canonical_character 兜底")
        prompt_missing_rows = []
        for row in self._select_keyframe_rows(storyboard_rows):
            locked_characters = asset_lock.resolve_many(self._row_present_characters(row))
            if not locked_characters:
                continue
            prompt = self._build_keyframe_prompt(brief, row)
            if any(character.fixed_prompt and character.fixed_prompt not in prompt for character in locked_characters):
                prompt_missing_rows.append(self._row_shot_no(row))
        if prompt_missing_rows:
            blockers.append("镜头 prompt 未带角色固定特征")
        polluted_scene_rows = [
            self._row_shot_no(row)
            for row in storyboard_rows
            if re.search(r"第\d+章|第\d+组|\d+秒|scene|chapter", self._row_scene(row), flags=re.IGNORECASE)
        ]
        if polluted_scene_rows:
            blockers.append("分镜场景字段仍混入章节号、分组号或时间标签")
        normalized_keys = [self._normalize_storyboard_text_key(self._row_content(row)) for row in storyboard_rows]
        duplicate_groups = len(normalized_keys) - len(set(normalized_keys))
        adjacent_duplicates = sum(1 for prev, current in zip(normalized_keys, normalized_keys[1:]) if prev and prev == current)
        if adjacent_duplicates > 0:
            blockers.append("分镜出现连续重复画面，会直接导致视频重复")
        elif duplicate_groups > max(1, len(storyboard_rows) // 4):
            issues.append("分镜重复度偏高，需要进一步丰富反应点")
        total_duration = sum(self._row_duration(row) for row in storyboard_rows)
        target_duration = self._resolve_story_duration_target(storyboard_rows)
        lower_bound = max(MIN_CHAPTER_DURATION_SECONDS, target_duration * 0.75)
        upper_bound = min(MAX_CHAPTER_DURATION_SECONDS + 20.0, target_duration * 1.25)
        pacing_ok = lower_bound <= total_duration <= upper_bound
        scores = {
            "fidelity": 9.0 if not blockers else 6.8,
            "pacing": 8.8 if pacing_ok else 6.5,
            "production": 8.6 if audio_plan.get("voice_style") and dialogue_count > 0 and narration_count > 0 and cue_sheet else 6.4,
            "adaptation": 8.4 if storyboard_rows and adjacent_duplicates == 0 else 6.5,
        }
        overall = round(sum(scores.values()) / 4, 2)
        passed = (
            all(scores[key] >= self.qa_threshold[key] for key in ("fidelity", "pacing", "production", "adaptation"))
            and overall >= self.qa_threshold["overall"]
            and not blockers
        )
        if not passed:
            issues.extend(["加强情绪铺垫", "增强章节钩子与结尾反转"])
        return {"passed": passed, "scores": scores, "overall": overall, "issues": issues, "blockers": blockers}

    def _resolve_chapter_duration_plan(self, payload: dict[str, Any]) -> dict[str, float]:
        raw_plan = payload.get("chapter_duration_plan")
        if not isinstance(raw_plan, dict):
            return {}
        normalized: dict[str, float] = {}
        for key, value in raw_plan.items():
            try:
                chapter_key = str(int(key))
                duration = float(value)
            except (TypeError, ValueError):
                continue
            normalized[chapter_key] = max(20.0, min(180.0, duration))
        return normalized

    def _resolve_target_duration(self, payload: dict[str, Any]) -> float | None:
        raw = payload.get("target_duration_seconds")
        if raw in (None, ""):
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        return max(20.0, min(180.0, value))

    def _chapter_target_duration(self, brief: dict[str, Any]) -> float | None:
        if self.explicit_target_duration and self.target_duration_seconds is not None:
            return round(self.target_duration_seconds, 1)
        chapter_key = str(int(brief.get("chapter", 0) or 0))
        planned = self.chapter_duration_plan.get(chapter_key)
        if planned is not None:
            return round(planned, 1)
        if self.target_duration_seconds is not None:
            return round(self.target_duration_seconds, 1)
        brief_value = brief.get("target_duration_seconds")
        if brief_value in (None, ""):
            return None
        try:
            return round(max(20.0, min(180.0, float(brief_value))), 1)
        except (TypeError, ValueError):
            return None

    def _extract_dialogue_candidates(self, cleaned_source_lines: list[str], detected_characters: list[dict[str, Any]], brief: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        quote_pattern = re.compile(r'[\u201c"\u300c\u300e](.+?)[\u201d"\u300d\u300f]')
        for index, line in enumerate(cleaned_source_lines, start=1):
            matches = [
                self._normalize_dialogue_text(item)
                for item in quote_pattern.findall(str(line or ""))
                if item and not self._is_low_value_dialogue(item)
            ]
            if not matches:
                continue
            line_characters = self._extract_line_characters(str(line), detected_characters)
            speaker = line_characters[0] if line_characters else ""
            for text in matches:
                candidates.append(
                    {
                        "text": text,
                        "speaker": speaker,
                        "source": "quoted_dialogue",
                        "line_index": index,
                        "context": str(line),
                    }
                )
        memorable_line = self._condense_text(str(brief.get("memorable_line") or "").strip(), limit=36)
        if memorable_line and memorable_line not in {item["text"] for item in candidates}:
            candidates.append(
                {
                    "text": memorable_line,
                    "speaker": self._default_dialogue_speaker("高潮"),
                    "source": "brief_memorable_line",
                    "line_index": 0,
                    "context": str(brief.get("summary") or "").strip(),
                }
            )
        return candidates

    def _normalize_dialogue_text(self, text: str) -> str:
        raw = str(text or "").strip()
        normalized = self._condense_text(raw, limit=36)
        tail = raw[-1] if raw else ""
        if tail and re.match(r"[。！？!?]", tail) and normalized and not normalized.endswith(("。", "！", "？", "!", "?")):
            return f"{normalized}{tail}"
        if "别理他们" in raw and normalized.endswith("别理他们"):
            return f"{normalized}{raw[-1]}"
        return normalized

    def _build_story_chunks(self, source_text: str, brief: dict[str, Any]) -> list[str]:
        cleaned_lines = self._clean_source_lines(source_text or brief.get("summary") or "")
        chunks: list[str] = []
        for line in cleaned_lines:
            compact = self._condense_text(
                re.sub(r'[\u201c"\u300c\u300e](.+?)[\u201d"\u300d\u300f]', "", line),
                limit=34,
            )
            if not compact:
                compact = self._condense_text(line, limit=34)
            if not compact or self._normalize_storyboard_text_key(compact) in {"级别", "斗之力"}:
                continue
            if compact not in chunks:
                chunks.append(compact)
        for fallback in (str(brief.get("key_scene") or "").strip(), str(brief.get("summary") or "").strip()):
            compact = self._condense_text(fallback, limit=34)
            if compact and compact not in chunks:
                chunks.append(compact)
        return chunks[:6] or [self._condense_text(str(brief.get("summary") or "").strip(), limit=34)]

    def _is_low_value_dialogue(self, text: str) -> bool:
        normalized = str(text or "").strip()
        if not normalized:
            return True
        return any(token in normalized for token in ("级别", "低级", "高阶测试", "斗之力"))

    def _build_blueprint_units(self, brief: dict[str, Any], grounding: dict[str, Any]) -> list[dict[str, Any]]:
        detected_characters = list(grounding.get("characters", []))
        quote_pattern = re.compile(r'[\u201c"\u300c\u300e](.+?)[\u201d"\u300d\u300f]')
        units: list[dict[str, Any]] = []
        for index, line in enumerate(grounding.get("cleaned_source_lines", []), start=1):
            clean_line = str(line or "").strip()
            if not clean_line:
                continue
            present_characters = self._extract_line_characters(clean_line, detected_characters)
            dialogue_matches = [
                self._normalize_dialogue_text(item)
                for item in quote_pattern.findall(clean_line)
                if item and not self._is_low_value_dialogue(item)
            ]
            dialogue = dialogue_matches[0] if dialogue_matches else ""
            content = self._condense_text(re.sub(quote_pattern, "", clean_line), limit=42)
            if any(token in content for token in ("级别", "低级")) and not any(token in content for token in ("哄笑", "拳", "身前", "压住")):
                continue
            if not content and not dialogue:
                continue
            units.append(
                {
                    "line_index": index,
                    "content": content,
                    "dialogue": dialogue,
                    "speaker": present_characters[0] if dialogue and present_characters else "",
                    "present_characters": present_characters,
                    "source_line": clean_line,
                }
            )
        if not units:
            fallback_content = self._compose_compact_text(str(brief.get("key_scene") or "").strip(), str(brief.get("summary") or "").strip(), limit=42)
            units.append(
                {
                    "line_index": 1,
                    "content": fallback_content,
                    "dialogue": self._normalize_dialogue_text(str(brief.get("memorable_line") or "").strip()),
                    "speaker": self._default_dialogue_speaker("高潮"),
                    "present_characters": list(grounding.get("character_names", []))[:2],
                    "source_line": fallback_content,
                }
            )
        return units

    def _trim_blueprint_units(self, units: list[dict[str, Any]], shot_count: int) -> list[dict[str, Any]]:
        if len(units) <= shot_count:
            return units
        scored: list[tuple[int, int]] = []
        for index, unit in enumerate(units):
            score = 0
            if str(unit.get("dialogue") or "").strip():
                score += 3
            content = str(unit.get("content") or "")
            if any(token in content for token in ("哄笑", "攥紧", "站到", "压住", "现身", "退婚", "拜师", "挑战")):
                score += 2
            if len(unit.get("present_characters") or []) >= 2:
                score += 1
            scored.append((score, index))
        selected = {0, len(units) - 1}
        for _, index in sorted(scored, reverse=True):
            selected.add(index)
            if len(selected) >= shot_count:
                break
        if len(selected) < shot_count:
            step = max(1, len(units) // shot_count)
            for index in range(0, len(units), step):
                selected.add(index)
                if len(selected) >= shot_count:
                    break
        return [units[index] for index in sorted(selected)[:shot_count]]

    def _blueprint_narration(self, *, brief: dict[str, Any], beat: str, content: str, has_dialogue: bool, shot_index: int, total_shots: int, grounding: dict[str, Any]) -> str:
        if has_dialogue:
            return ""
        if shot_index == 1:
            return self._condense_text((grounding.get("scene_anchors") or [""])[0], limit=32)
        if "高潮前停顿" in beat and grounding.get("world_rules"):
            return self._condense_text(str(grounding["world_rules"][0]), limit=32)
        if shot_index == total_shots:
            return self._condense_text((grounding.get("conflict_points") or [content])[-1], limit=32)
        return ""

    def _build_storyboard_blueprint(self, brief: dict[str, Any], grounding: dict[str, Any], feedback: list[str] | None = None) -> dict[str, Any]:
        profile_blocks = self.storyboard_profile.get("group_style_blocks", [])
        beats = [str(block.get("beat") or "") for block in profile_blocks if str(block.get("beat") or "").strip()]
        if not beats:
            beats = ["开场钩子", "关系建立", "冲突升级", "高潮前停顿", "高潮", "结尾反转/尾钩"]
        units = self._build_blueprint_units(brief, grounding)
        shot_count = self._derive_blueprint_shot_count(grounding)
        if not self.explicit_shot_count:
            shot_count = max(shot_count, min(12, len(units)))
        units = self._trim_blueprint_units(units, shot_count)
        keyframe_count = self._derive_blueprint_keyframe_count(shot_count)
        target_duration_seconds = self._derive_blueprint_target_duration(brief, grounding)
        roles = self._story_role_characters()
        detected_names = list(grounding.get("character_names", []))
        durations = build_fallback_shot_distribution(
            group_durations=[target_duration_seconds / len(beats)] * len(beats),
            shot_count=shot_count,
        )
        shots: list[dict[str, Any]] = []
        cursor = 0.0
        shot_no = 1
        for beat_index, beat in enumerate(beats, start=1):
            local_count = durations[beat_index - 1] if beat_index - 1 < len(durations) else 1
            beat_shot_count = max(1, int(local_count))
            duration_per_shot = round(target_duration_seconds / max(1, shot_count), 1)
            for local_index in range(beat_shot_count):
                unit = units[min(len(units) - 1, shot_no - 1)] if units else {}
                stage_block = profile_blocks[min(beat_index - 1, len(profile_blocks) - 1)] if profile_blocks else {}
                present_characters = list(unit.get("present_characters") or self._blueprint_present_characters(beat, roles, detected_names))
                speaker = self._canonicalize_character_name(str(unit.get("speaker") or "").strip())
                dialogue = self._normalize_dialogue_text(str(unit.get("dialogue") or "").strip())
                if not dialogue and "高潮" in beat and str(brief.get("memorable_line") or "").strip():
                    dialogue = self._normalize_dialogue_text(str(brief.get("memorable_line") or "").strip())
                if not speaker and dialogue:
                    speaker = self._blueprint_speaker(beat, local_index, beat_shot_count, roles, present_characters)
                content = self._compose_compact_text(
                    str(unit.get("content") or ""),
                    str(stage_block.get("focus") or brief.get("key_scene") or "").strip(),
                    limit=42,
                )
                narration = self._blueprint_narration(
                    brief=brief,
                    beat=beat,
                    content=content,
                    has_dialogue=bool(dialogue),
                    shot_index=shot_no,
                    total_shots=shot_count,
                    grounding=grounding,
                )
                shots.append(
                    {
                        "shot": shot_no,
                        "beat": beat,
                        "scene": self._build_stage_scene_label(brief, beat_index, beat),
                        "duration_seconds": duration_per_shot,
                        "start_seconds": round(cursor, 1),
                        "end_seconds": round(cursor + duration_per_shot, 1),
                        "speaker": speaker,
                        "present_characters": present_characters,
                        "content": content,
                        "performance": self._append_unique_text(
                            self._build_group_performance(brief, stage_block, beat_index, local_index),
                            self._condense_text(str(unit.get("source_line") or ""), limit=24),
                        ),
                        "dialogue": dialogue,
                        "narration": narration,
                        "audio_design": self._build_group_audio_beat(beat),
                        "music": self._build_group_music(brief, stage_block, beat_index),
                        "shot_size": self._pick_group_value(stage_block.get("size_candidates", ["中景"]), local_index, fallback="中景"),
                        "camera_move": self._pick_group_value(stage_block.get("movement_candidates", ["缓推"]), local_index, fallback="缓推"),
                        "priority": max(1, 6 - local_index),
                    }
                )
                cursor += duration_per_shot
                shot_no += 1
                if shot_no > shot_count:
                    break
            if shot_no > shot_count:
                break
        return {
            "chapter": int(brief["chapter"]),
            "title": brief["title"],
            "target_duration_seconds": target_duration_seconds,
            "shot_count": shot_count,
            "keyframe_count": keyframe_count,
            "feedback": list(feedback or []),
            "scene": grounding.get("scene", {}),
            "character_names": detected_names,
            "story_grounding_summary": {
                "scene_anchors": grounding.get("scene_anchors", []),
                "conflict_points": grounding.get("conflict_points", []),
                "dialogue_candidates": grounding.get("dialogue_candidates", []),
            },
            "shots": shots,
        }

    def _normalize_storyboard_rows(self, rows: list[dict[str, Any]], brief: dict[str, Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        cursor = 0.0
        shot_limit = next(
            (
                int(row.get("blueprint_shot_count") or 0)
                for row in rows
                if int(row.get("blueprint_shot_count") or 0) > 0
            ),
            int(self.shot_count),
        )
        for index, row in enumerate(rows[: shot_limit], start=1):
            duration = max(0.8, float(row.get("时长(s)", row.get("duration", 1.2)) or 1.2))
            end_time = round(cursor + duration, 1)
            beat = str(row.get("节奏目的", "冲突推进"))
            scene_value = str(row.get("场景/时间", "")).strip()
            if not scene_value or re.search(r"chapter|scene", scene_value, flags=re.IGNORECASE):
                scene_value = self._build_stage_scene_label(brief, min(6, math.ceil(index / 2)), beat)
            dialogue = str(row.get("对白", row.get("台词对白", ""))).strip()
            narration = str(row.get("旁白", "")).strip()
            if narration and self._normalize_storyboard_text_key(narration) == self._normalize_storyboard_text_key(dialogue):
                narration = ""
            speaker = self._canonicalize_character_name(
                str(row.get("对白角色", row.get("角色", self._default_dialogue_speaker(beat)))).strip()
                or self._default_dialogue_speaker(beat)
            )
            present_characters = self._normalize_present_characters(row=row, speaker=speaker, beat=beat)
            canonical_role_text = "、".join(present_characters) if present_characters else str(row.get("角色", self.source_title))
            normalized.append(
                {
                    "分组": str(row.get("分组", f"第{min(6, math.ceil(index / 2))}组")),
                    "15秒段": str(row.get("15秒段", f"{cursor}-{end_time}秒")),
                    "镜头号": index,
                    "时长(s)": round(duration, 1),
                    "起始时间": round(cursor, 1),
                    "结束时间": end_time,
                    "场景/时间": scene_value,
                    "镜头景别": str(row.get("镜头景别", "中景")),
                    "镜头运动": str(row.get("镜头运动", "缓推")),
                    "画面内容": str(row.get("画面内容", brief["key_scene"])),
                    "人物动作/神态": str(row.get("人物动作/神态", brief["emotion"])),
                    "旁白": narration,
                    "对白角色": speaker,
                    "对白": dialogue,
                    "台词对白": dialogue,
                    "角色": canonical_role_text,
                    "出镜角色": "、".join(present_characters),
                    "音效": str(row.get("音效", "氛围环境声")),
                    "音频设计": str(row.get("音频设计", self._build_group_audio_beat(beat))),
                    "音乐": str(row.get("音乐", brief["emotion"])),
                    "节奏目的": beat,
                    "关键帧优先级": self._coerce_priority(row.get("关键帧优先级", 3), default=3),
                    "blueprint_shot_count": int(row.get("blueprint_shot_count") or shot_limit),
                    "blueprint_keyframe_count": int(row.get("blueprint_keyframe_count") or self.keyframe_count),
                    "blueprint_target_duration": float(row.get("blueprint_target_duration") or self._chapter_target_duration(brief) or 0.0),
                }
            )
            cursor = end_time
        return normalized or self._fallback_storyboard(brief, "")

    def _ensure_storyboard_quality_anchors(self, brief: dict[str, Any], rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        rows[0]["节奏目的"] = "开场钩子"
        rows[0]["画面内容"] = self._append_unique_text(str(rows[0].get("画面内容", "")), brief["key_scene"])
        rows[-1]["节奏目的"] = "结尾反转/尾钩"
        rows[-1]["画面内容"] = self._append_unique_text(str(rows[-1].get("画面内容", "")), f"尾钩：{brief['summary']}")
        memorable_line = str(brief.get("memorable_line", "")).strip()
        if memorable_line and memorable_line not in json.dumps(rows, ensure_ascii=False):
            anchor_index = 1 if len(rows) > 1 else 0
            rows[anchor_index]["对白"] = memorable_line
            rows[anchor_index]["台词对白"] = memorable_line
            current_speaker = str(rows[anchor_index].get("对白角色", "")).strip()
            rows[anchor_index]["对白角色"] = current_speaker or self._default_dialogue_speaker(str(rows[anchor_index].get("节奏目的", "高潮")))
            rows[anchor_index]["画面内容"] = self._append_unique_text(str(rows[anchor_index].get("画面内容", "")), f"名台词爆点：{memorable_line}")
            rows[anchor_index]["节奏目的"] = self._append_unique_text(str(rows[anchor_index].get("节奏目的", "")), "名台词爆点")
        world_rule = str(brief.get("world_rule", "")).strip()
        if world_rule and world_rule not in json.dumps(rows, ensure_ascii=False):
            anchor_index = min(len(rows) - 1, max(1, len(rows) // 2))
            rows[anchor_index]["画面内容"] = self._append_unique_text(str(rows[anchor_index].get("画面内容", "")), world_rule)
            if str(rows[anchor_index].get("台词对白", "")).strip() in {"", "-"}:
                rows[anchor_index]["对白"] = world_rule
                rows[anchor_index]["台词对白"] = world_rule
                rows[anchor_index]["对白角色"] = str(rows[anchor_index].get("对白角色", "旁白")).strip() or "旁白"
            rows[anchor_index]["节奏目的"] = self._append_unique_text(str(rows[anchor_index].get("节奏目的", "")), "规则落地")
            if not str(rows[anchor_index].get("旁白", "")).strip():
                rows[anchor_index]["旁白"] = world_rule

    def _resolve_story_duration_target(self, rows: list[dict[str, Any]]) -> float:
        blueprint_target = next(
            (
                float(row.get("blueprint_target_duration") or 0.0)
                for row in rows
                if float(row.get("blueprint_target_duration") or 0.0) > 0
            ),
            0.0,
        )
        if blueprint_target > 0:
            return round(blueprint_target, 1)
        if self.target_duration_seconds is not None:
            return round(self.target_duration_seconds, 1)
        suggested_total = sum(self._suggest_row_duration(row) for row in rows)
        return round(max(MIN_CHAPTER_DURATION_SECONDS, min(MAX_CHAPTER_DURATION_SECONDS, suggested_total)), 1)

    def _review_final(
        self,
        brief: dict[str, Any],
        storyboard_rows: list[dict[str, Any]],
        plan_review: dict[str, Any],
        preview_video: Path,
        delivery_video: Path,
        voiceover: Path,
        storyboard_xlsx: Path,
        video_plan_path: Path,
        video_plan: dict[str, Any],
    ) -> dict[str, Any]:
        blockers = list(plan_review["blockers"])
        issues = list(plan_review["issues"])
        dialogue_count = len([row for row in storyboard_rows if self._row_dialogue(row) not in {"", "-", "无", "空"}])
        narration_count = len([row for row in storyboard_rows if self._row_narration(row) not in {"", "-", "无", "空"}])
        polluted_scene_rows = [
            self._row_shot_no(row)
            for row in storyboard_rows
            if re.search(r"第\d+章|第\d+组|scene|chapter|\d+:\d+", self._row_scene(row), flags=re.IGNORECASE)
        ]
        if not preview_video.exists() or not delivery_video.exists():
            blockers.append("章节预览或交付视频缺失")
        if not storyboard_xlsx.exists():
            blockers.append("章节分镜表缺失")
        if not voiceover.exists():
            blockers.append("章节配音文件缺失")
        if not video_plan_path.exists():
            blockers.append("章节视频计划文件缺失")
        if dialogue_count <= 0:
            blockers.append("章节缺少对白")
        if narration_count <= 0:
            blockers.append("章节缺少旁白")
        if polluted_scene_rows:
            blockers.append("分镜场景字段混入章节号、分组号或时间标签")

        expected_duration = round(sum(self._row_duration(row) for row in storyboard_rows), 2)
        target_duration = self._resolve_story_duration_target(storyboard_rows)
        lower_bound = max(MIN_CHAPTER_DURATION_SECONDS, target_duration * 0.75)
        upper_bound = min(MAX_CHAPTER_DURATION_SECONDS + 20.0, target_duration * 1.25)
        preview_meta = self._probe_video_metadata(preview_video) if preview_video.exists() else {"duration_seconds": 0.0, "frame_count": 0, "fps": 0.0}
        delivery_meta = self._probe_video_metadata(delivery_video) if delivery_video.exists() else {"duration_seconds": 0.0, "frame_count": 0, "fps": 0.0}
        motion = self._analyze_video_motion(preview_video) if preview_video.exists() else {"motion_score": 0.0, "sampled_frames": 0}
        actual_duration = float(preview_meta.get("duration_seconds", 0.0) or 0.0)
        delivery_duration = float(delivery_meta.get("duration_seconds", 0.0) or 0.0)
        motion_score = float(motion.get("motion_score", 0.0) or 0.0)
        summary = dict(video_plan.get("summary", {}))

        if actual_duration < lower_bound:
            blockers.append("成片时长低于当前章节内容可支撑的下限")
        elif actual_duration > upper_bound:
            issues.append("成片时长明显超出当前章节内容支撑范围")
        elif abs(actual_duration - expected_duration) > max(10.0, expected_duration * 0.25):
            issues.append("成片时长与分镜预计时长偏差较大")
        if abs(actual_duration - delivery_duration) > 1.5:
            blockers.append("预览视频与交付视频时长不一致")
        if motion_score < VIDEO_MOTION_SCORE_THRESHOLD:
            blockers.append("成片运动变化不足")

        requested_real_video = bool(summary.get("requested_real_video"))
        real_asset_success_count = int(summary.get("real_asset_success_count", 0) or 0)
        fallback_ratio = float(summary.get("fallback_ratio", 0.0) or 0.0)
        if requested_real_video and real_asset_success_count <= 0:
            blockers.append("已启用真图模式，但未生成任何真实图生视频片段")
        elif requested_real_video and fallback_ratio > REAL_VIDEO_FALLBACK_WARNING_RATIO:
            issues.append("图生视频片段回退比例偏高")

        passed = not blockers and plan_review["passed"]
        summary_text = f"第{int(brief['chapter']):02d}章{'通过' if passed else '未通过'} QA"
        return {
            "passed": passed,
            "overall": plan_review["overall"],
            "scores": plan_review["scores"],
            "issues": issues,
            "blockers": blockers,
            "summary": summary_text,
            "expected_duration_seconds": expected_duration,
            "preview_duration_seconds": round(actual_duration, 2),
            "delivery_duration_seconds": round(delivery_duration, 2),
            "motion_score": round(motion_score, 6),
            "real_asset_success_count": real_asset_success_count,
            "real_segment_count": int(summary.get("real_segment_count", 0) or 0),
            "local_segment_count": int(summary.get("local_segment_count", 0) or 0),
            "fallback_ratio": round(fallback_ratio, 4),
            "dialogue_count": dialogue_count,
            "narration_count": narration_count,
            "polluted_scene_rows": polluted_scene_rows,
        }

    def _build_chapter_qa_markdown(self, brief: dict[str, Any], qa_rounds: list[dict[str, Any]], final_review: dict[str, Any]) -> str:
        lines = [
            f"# 第{int(brief['chapter']):02d}章 QA 报告",
            "",
            f"- 结论：{'通过' if final_review['passed'] else '未通过'}",
            f"- 综合评分：{final_review['overall']}",
            f"- 计划时长：{final_review['expected_duration_seconds']}s",
            f"- 预览时长：{final_review['preview_duration_seconds']}s",
            f"- 交付时长：{final_review['delivery_duration_seconds']}s",
            f"- 运动评分：{final_review['motion_score']}",
            f"- 真实视频资产：{final_review['real_asset_success_count']}",
            f"- 真实视频镜头：{final_review['real_segment_count']}",
            f"- 本地动画镜头：{final_review['local_segment_count']}",
            f"- 回退比例：{final_review['fallback_ratio']:.0%}",
            "",
        ]
        for item in qa_rounds:
            lines.append(f"## Round {item['round']}")
            lines.append(f"- 通过：{item['passed']}")
            lines.append(f"- 分数：{json.dumps(item['scores'], ensure_ascii=False)}")
            if item["issues"]:
                lines.extend([f"- 问题：{issue}" for issue in item["issues"]])
            if item["blockers"]:
                lines.extend([f"- 阻塞：{issue}" for issue in item["blockers"]])
            lines.append("")
        if final_review["issues"]:
            lines.extend([f"- 最终问题：{issue}" for issue in final_review["issues"]])
        if final_review["blockers"]:
            lines.extend([f"- 最终阻塞：{issue}" for issue in final_review["blockers"]])
        return "\n".join(lines)

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
