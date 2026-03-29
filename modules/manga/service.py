import json
import os
import textwrap
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from backend.config import ARTIFACTS_DIR, ROOT_DIR
from backend.schemas import ArtifactPreview, CapabilityDescriptor, CapabilityField, WorkflowStep
from modules.base import CapabilityModule, ExecutionContext, ExecutionResult, PlannedJob
from modules.manga.chapter_factory import run_manga_job
from shared.providers.ark import ArkProvider


class MangaCapability(CapabilityModule):
    descriptor = CapabilityDescriptor(
        id="manga",
        name="AI 漫剧",
        description="把小说或故事主题规划并执行成漫剧生产任务。",
        category="content",
        outputs=["角色设定", "分镜", "图片", "预览视频", "交付视频"],
        input_fields=[
            CapabilityField(
                key="source_title",
                label="原作名称",
                description="小说名、IP 名称或故事主题。",
            ),
            CapabilityField(
                key="chapter_range",
                label="章节范围",
                description="例如：1-10。",
            ),
            CapabilityField(
                key="episode_count",
                label="章节数量",
                field_type="integer",
                description="本次要处理多少章。",
            ),
            CapabilityField(
                key="visual_style",
                label="视觉风格",
                required=False,
                description="例如：国风玄幻、热血、悬疑。",
            ),
            CapabilityField(
                key="chapter_briefs",
                label="章节摘要数组",
                required=False,
                field_type="array",
                description="可选。用于更准确改编的结构化章节摘要。",
            ),
            CapabilityField(
                key="storyboard_scene_count",
                label="分镜图数量",
                required=False,
                field_type="integer",
                description="要生成多少张分镜图。",
            ),
            CapabilityField(
                key="chapter_keyframe_count",
                label="每章关键帧数",
                required=False,
                field_type="integer",
                description="每章生成多少张关键帧图片，默认 4。",
            ),
            CapabilityField(
                key="chapter_shot_count",
                label="每章镜头数",
                required=False,
                field_type="integer",
                description="每章分镜表镜头数，默认 10。",
            ),
            CapabilityField(
                key="use_model_storyboard",
                label="启用模型细化分镜",
                required=False,
                field_type="boolean",
                description="是否用文本模型逐章细化镜头表，默认关闭以优先保证整包速度。",
            ),
            CapabilityField(
                key="use_real_images",
                label="启用真图/真视频",
                required=False,
                field_type="boolean",
                description="是否调用服务商 API 生成真图和真视频。",
            ),
            CapabilityField(
                key="image_model",
                label="图片模型",
                required=False,
                description="Ark 图片模型名称，默认 Doubao-Seedream-4.5。",
            ),
            CapabilityField(
                key="video_model",
                label="视频模型",
                required=False,
                description="Ark 视频模型名称，默认 Doubao-Seedance-1.5-pro。",
            ),
        ],
    )

    def plan_job(self, payload: dict) -> PlannedJob:
        source_title = payload.get("source_title", "Untitled")
        chapter_range = payload.get("chapter_range", "TBD")
        requested_episodes = int(payload.get("episode_count", 3))
        chapter_briefs = self._normalize_chapter_briefs(payload=payload, fallback_episode_count=requested_episodes)
        episode_count = len(chapter_briefs)
        visual_style = payload.get("visual_style", "TBD")

        workflow = [
            WorkflowStep(
                key="research",
                title="题材研究",
                description=f"分析《{source_title}》的改编价值、受众和整体基调。",
            ),
            WorkflowStep(
                key="story_breakdown",
                title="章节拆解",
                description=f"把章节 {chapter_range} 拆成 {episode_count} 个可独立交付的章节包。",
            ),
            WorkflowStep(
                key="storyboard_design",
                title="镜头设计",
                description="为每章输出可审片的镜头表、节奏分组和音视频设计。",
            ),
            WorkflowStep(
                key="chapter_packaging",
                title="章节封装",
                description="每章生成关键帧、章节视频、章节页面和章节交付清单。",
            ),
            WorkflowStep(
                key="qa_loop",
                title="QA 迭代",
                description="按四个硬指标对每章做门禁校验，不满意则返工后再交付。",
            ),
        ]

        artifacts = [
            ArtifactPreview(artifact_type="directory", label="角色素材目录", path_hint="characters"),
            ArtifactPreview(artifact_type="directory", label="总分镜目录", path_hint="storyboard"),
            ArtifactPreview(artifact_type="directory", label="章节目录", path_hint="chapters"),
            ArtifactPreview(artifact_type="directory", label="交付目录", path_hint="delivery"),
            ArtifactPreview(artifact_type="html", label="预览页面", path_hint="preview/index.html"),
            ArtifactPreview(artifact_type="video", label="预览视频", path_hint="preview/preview.mp4"),
            ArtifactPreview(artifact_type="video", label="交付视频", path_hint="delivery/final_cut.mp4"),
            ArtifactPreview(artifact_type="json", label="章节索引", path_hint="chapters_index.json"),
            ArtifactPreview(artifact_type="markdown", label="QA 总览", path_hint="qa_overview.md"),
            ArtifactPreview(artifact_type="json", label="任务清单", path_hint="manifest.json"),
        ]

        summary = (
            f"已规划《{source_title}》的章节工厂流程，共 {episode_count} 章，章节范围 {chapter_range}，风格为 {visual_style}。"
        )
        return PlannedJob(workflow=workflow, artifacts=artifacts, summary=summary)

    def execute_job(self, payload: dict, context: ExecutionContext) -> ExecutionResult:
        plan = self.plan_job(payload)
        return run_manga_job(
            payload=payload,
            context=context,
            plan=plan,
            normalize_chapter_briefs=self._normalize_chapter_briefs,
            build_prompts=self._build_prompts,
            format_research_brief=self._format_research_brief,
            write_placeholder_image=self._write_placeholder_image,
            load_font=self._load_font,
        )

    def _normalize_chapter_briefs(self, payload: dict, fallback_episode_count: int) -> list[dict]:
        raw_briefs = payload.get("chapter_briefs")
        briefs: list[dict] = []
        if isinstance(raw_briefs, list):
            for index, item in enumerate(raw_briefs, start=1):
                if not isinstance(item, dict):
                    continue
                chapter = int(item.get("chapter", index))
                briefs.append(
                    {
                        "chapter": chapter,
                        "title": str(item.get("title", f"第{chapter}章")).strip(),
                        "summary": str(
                            item.get("summary", f"第 {chapter} 章的核心冲突升级。")
                        ).strip(),
                        "key_scene": str(
                            item.get("key_scene", f"第 {chapter} 章的关键转折场面。")
                        ).strip(),
                        "emotion": str(item.get("emotion", "压迫感")).strip(),
                        "fidelity_notes": str(item.get("fidelity_notes", "")).strip(),
                        "memorable_line": str(item.get("memorable_line", "")).strip(),
                        "world_rule": str(item.get("world_rule", "")).strip(),
                    }
                )

        if briefs:
            briefs.sort(key=lambda item: item["chapter"])
            return briefs

        count = max(1, fallback_episode_count)
        return [
            {
                "chapter": index,
                "title": f"第{index}章",
                "summary": f"第 {index} 章的冲突继续升级。",
                "key_scene": f"第 {index} 章的标志性场面。",
                "emotion": "压迫感",
                "fidelity_notes": "",
                "memorable_line": "",
                "world_rule": "",
            }
            for index in range(1, count + 1)
        ]

    def _resolve_scene_count(self, payload: dict, episode_count: int) -> int:
        raw_scene_count = payload.get("storyboard_scene_count")
        if raw_scene_count is None:
            return min(max(episode_count, 2), 20)

        try:
            scene_count = int(raw_scene_count)
        except (TypeError, ValueError):
            scene_count = min(max(episode_count, 2), 20)
        return min(max(scene_count, 2), 60)

    def _build_prompts(
        self,
        source_title: str,
        visual_style: str,
        chapter_briefs: list[dict],
        scene_count: int,
    ) -> dict:
        storyboard_prompts = []
        for index in range(scene_count):
            chapter = chapter_briefs[index % len(chapter_briefs)]
            memorable_line = f" Memorable line: {chapter['memorable_line']}." if chapter.get("memorable_line") else ""
            world_rule = f" World rule: {chapter['world_rule']}." if chapter.get("world_rule") else ""
            fidelity_notes = f" Fidelity rule: {chapter['fidelity_notes']}." if chapter.get("fidelity_notes") else ""
            storyboard_prompts.append(
                (
                    f"Manga storyboard frame for {source_title}: "
                    f"{chapter['key_scene']} Emotion: {chapter['emotion']}. "
                    f"Style: {visual_style}.{memorable_line}{world_rule}{fidelity_notes} "
                    "Respect original character motivations, cinematic composition, dramatic lighting. "
                    "Do not render chapter numbers, scene labels, timestamps, or storyboard captions inside the image."
                )
            )

        return {
            "lead_character": (
                f"Chinese dark xianxia manga portrait for {source_title}, lead protagonist, "
                f"{visual_style}, intricate costume details, cinematic contrast, faithful to the original protagonist image."
            ),
            "storyboard": storyboard_prompts,
        }

    def _build_scene_tiles(self, scene_images: list[Path], max_tiles: int = 8) -> list[str]:
        tiles = []
        for index, scene_path in enumerate(scene_images[:max_tiles], start=1):
            rel_path = f"../storyboard/{scene_path.name}"
            tiles.extend(
                [
                    "<div class=\"tile\">",
                    f"<h3>分镜 {index}</h3>",
                    f"<img src=\"{rel_path}\" alt=\"分镜 {index}\" />",
                    "</div>",
                ]
            )
        return tiles

    def _build_video_prompt(
        self,
        source_title: str,
        chapter_range: str,
        chapter_briefs: list[dict],
        visual_style: str,
    ) -> str:
        focus = "; ".join(
            [
                f"{item['title']}: {item['key_scene']}"
                for item in chapter_briefs[:6]
            ]
        )
        lines = " ".join(
            [
                f"Keep line: {item['memorable_line']}"
                for item in chapter_briefs[:6]
                if item.get("memorable_line")
            ]
        )
        return (
            f"Create a cinematic manga trailer for {source_title}. "
            f"Visual style: {visual_style}. Key beats: {focus}. "
            f"{lines} Preserve original character motivations and world rules. "
            "Dark xianxia atmosphere, high-contrast lighting, smooth camera motion, emotionally coherent pacing. "
            "Do not place chapter numbers, scene/time cards, or storyboard labels into the generated frames."
        )

    def _format_research_brief(self, item: dict) -> str:
        parts = [
            f"- 第{item['chapter']:02d}章：{item['title']} | {item['summary']}",
        ]
        if item.get("fidelity_notes"):
            parts.append(f"还原要求：{item['fidelity_notes']}")
        if item.get("world_rule"):
            parts.append(f"设定规则：{item['world_rule']}")
        return " | ".join(parts)

    def _build_delivery_video(
        self,
        *,
        image_paths: list[Path],
        chapter_briefs: list[dict],
        source_title: str,
        chapter_range: str,
        visual_style: str,
        output_path: Path,
        fps: int = 8,
    ) -> None:
        if not image_paths:
            raise RuntimeError("没有可用于生成交付视频的分镜图")

        frame_size = (1280, 720)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        writer = imageio.get_writer(output_path, fps=fps, codec="libx264")
        scene_groups = self._group_scene_images(image_paths=image_paths, chapter_briefs=chapter_briefs)

        try:
            title_card = self._build_text_card(
                title=f"{source_title} 漫剧交付版",
                lines=[
                    f"章节范围：{chapter_range}",
                    f"章节数量：{len(chapter_briefs)}",
                    f"视觉风格：{visual_style}",
                ],
                size=frame_size,
            )
            for _ in range(fps * 2):
                writer.append_data(title_card)

            for chapter, group in scene_groups:
                chapter_card = self._build_text_card(
                    title=f"第{int(chapter['chapter']):02d}章：{chapter['title']}",
                    lines=[
                        f"剧情摘要：{chapter['summary']}",
                        f"关键场面：{chapter['key_scene']}",
                        f"情绪基调：{chapter['emotion']}",
                    ],
                    size=frame_size,
                )
                for _ in range(max(6, fps)):
                    writer.append_data(chapter_card)

                for image_path in group:
                    frame = self._compose_video_frame(image_path=image_path, size=frame_size)
                    for _ in range(max(8, fps + 2)):
                        writer.append_data(frame)

            closing_card = self._build_text_card(
                title="交付完成",
                lines=[
                    f"原作：{source_title}",
                    "已封装为可直接查看的交付视频。",
                ],
                size=frame_size,
            )
            for _ in range(fps * 2):
                writer.append_data(closing_card)
        finally:
            writer.close()

    def _group_scene_images(
        self,
        *,
        image_paths: list[Path],
        chapter_briefs: list[dict],
    ) -> list[tuple[dict, list[Path]]]:
        groups: list[tuple[dict, list[Path]]] = []
        chapter_count = max(1, len(chapter_briefs))
        base_size = len(image_paths) // chapter_count
        remainder = len(image_paths) % chapter_count
        offset = 0

        for index, chapter in enumerate(chapter_briefs):
            group_size = base_size + (1 if index < remainder else 0)
            if group_size <= 0:
                group_size = 1
            group = image_paths[offset:offset + group_size]
            if not group and image_paths:
                group = [image_paths[min(index, len(image_paths) - 1)]]
            groups.append((chapter, group))
            offset += group_size

        return groups

    def _build_text_card(
        self,
        *,
        title: str,
        lines: list[str],
        size: tuple[int, int] = (1280, 720),
    ):
        image = Image.new("RGB", size, color=(13, 18, 28))
        draw = ImageDraw.Draw(image)
        width, height = size
        title_font = self._load_font(size=38)
        body_font = self._load_font(size=26)

        draw.rounded_rectangle((48, 48, width - 48, height - 48), radius=32, outline=(220, 104, 48), width=3)
        draw.rectangle((72, 72, width - 72, height - 72), fill=(22, 27, 40))

        title_y = 120
        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        title_x = (width - (title_bbox[2] - title_bbox[0])) // 2
        draw.text((title_x, title_y), title, fill=(255, 245, 230), font=title_font)

        current_y = 220
        for line in lines:
            wrapped = textwrap.wrap(line, width=24) or [line]
            for item in wrapped[:3]:
                draw.text((120, current_y), item, fill=(220, 228, 240), font=body_font)
                current_y += 52
            current_y += 12

        return np.array(image)

    def _load_font(self, *, size: int):
        font_dir = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"
        candidates = [
            font_dir / "msyh.ttc",
            font_dir / "msyhbd.ttc",
            font_dir / "simhei.ttf",
            font_dir / "simsun.ttc",
            font_dir / "arial.ttf",
        ]
        for path in candidates:
            if path.exists():
                try:
                    return ImageFont.truetype(str(path), size=size)
                except OSError:
                    continue
        return ImageFont.load_default()

    def _compose_video_frame(self, *, image_path: Path, size: tuple[int, int]):
        width, height = size
        canvas = Image.new("RGB", size, color=(10, 14, 24))
        source = Image.open(image_path).convert("RGB")
        source.thumbnail(size, Image.Resampling.LANCZOS)
        offset_x = (width - source.width) // 2
        offset_y = (height - source.height) // 2
        canvas.paste(source, (offset_x, offset_y))
        return np.array(canvas)

    def _build_preview_video(self, image_paths: list[Path], output_path: Path, fps: int = 6) -> None:
        if not image_paths:
            raise RuntimeError("没有可用于生成预览视频的分镜图")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        writer = imageio.get_writer(output_path, fps=fps, codec="libx264")
        try:
            for image_path in image_paths:
                frame = imageio.imread(image_path)
                writer.append_data(frame)
        finally:
            writer.close()

    def _write_placeholder_image(self, output_path: Path, title: str, subtitle: str, size: tuple[int, int]) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", size, color=(20, 24, 36))
        width, height = size
        for y in range(height):
            image.paste((20 + (y % 80), 24 + (y % 40), 36 + (y % 60)), (0, y, width, y + 1))
        image.save(output_path)

    def _build_preview_gif(self, image_paths: list[Path], output_path: Path) -> None:
        if not image_paths:
            raise RuntimeError("没有可用于生成预览动图的分镜图")
        frames = []
        for image_path in image_paths:
            frame = imageio.imread(image_path)
            frames.append(frame)
        imageio.mimsave(output_path, frames, duration=1.8)
