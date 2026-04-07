from __future__ import annotations

import json
import math
import re
from typing import Any

from modules.manga.chapter_factory_constants import (
    MAX_CHAPTER_DURATION_SECONDS,
    MIN_CHAPTER_DURATION_SECONDS,
)
from shared.asset_lock import split_character_tokens
from shared.adaptation_quality import build_quality_prompt
from shared.storyboard_reference import build_fallback_shot_distribution


class ChapterFactoryStoryboardPhaseMixin:
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

    def _reflow_storyboard_timing(self, rows: list[dict[str, Any]], durations: list[float]) -> None:
        cursor = 0.0
        for row, duration in zip(rows, durations):
            end_time = round(cursor + duration, 1)
            row["时长(s)"] = round(duration, 1)
            row["起始时间"] = round(cursor, 1)
            row["结束时间"] = end_time
            row["15秒段"] = f"{round(cursor, 1)}-{end_time}秒"
            cursor = end_time

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

