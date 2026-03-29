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
from PIL import Image, ImageDraw

from modules.manga.chapter_factory_constants import (
    DEFAULT_KEYFRAME_COUNT,
    DEFAULT_FPS,
    REAL_VIDEO_ASSET_MAX_WAIT_SECONDS,
    REAL_VIDEO_ASSET_POLL_INTERVAL_SECONDS,
    REAL_VIDEO_SEGMENT_SECONDS,
)


class ChapterFactoryRenderPhaseMixin:
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

    def _compose_frame(self, *, image_path: Path, row: dict[str, Any], brief: dict[str, Any], progress: float) -> np.ndarray:
        frame = imageio.imread(image_path)
        return self._compose_frame_from_array(frame=frame, row=row, brief=brief, progress=progress)

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

