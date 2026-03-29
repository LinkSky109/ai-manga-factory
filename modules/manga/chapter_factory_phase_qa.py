from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from modules.manga.chapter_factory_constants import (
    MAX_CHAPTER_DURATION_SECONDS,
    MIN_CHAPTER_DURATION_SECONDS,
    REAL_VIDEO_FALLBACK_WARNING_RATIO,
    VIDEO_MOTION_SCORE_THRESHOLD,
)


class ChapterFactoryQAPhaseMixin:
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

