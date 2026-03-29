from __future__ import annotations

import asyncio
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
import numpy as np

from modules.manga.chapter_factory_constants import (
    DEFAULT_TTS_VOICE,
)


class ChapterFactoryAudioPhaseMixin:
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

