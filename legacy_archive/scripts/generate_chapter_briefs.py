#!/usr/bin/env python3
"""调用 Ark 文本模型为适配包生成章节剧情摘要。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.adaptation_packs import get_adaptation_pack
from shared.providers.ark import ArkProvider
from shared.source_materials import ChapterSource, load_chapter_sources


ADAPTATION_RULES = """\
你要把小说改编为漫剧，必须严格遵守以下标准。
一、最核心的 4 个硬指标
1. 还原度：角色人设不能崩，动机和关系不能乱改，关键名场面和名台词优先保留，世界观规则不能乱加。
2. 叙事节奏：不能注水、不能乱跳、不能硬塞原创支线，高光场面前必须有铺垫。
3. 制作可落地：分镜必须能画、能拍、能演，情绪必须落到具体画面和动作上。
4. 改编合理性：不能尴尬中二，不能强行耍帅，不能让角色降智，战斗和特效要有明确动因。
二、3 个加分项
1. 适度补全人物动机，让角色更立体。
2. 情绪感染力强，让没看过原作的人也能被打动。
3. 路人友好，单看本章也能理解当前冲突。
如果提供了原文章节，请以原文章节为最高优先级，不要自行补后续剧情，不要跨章剧透。"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="为适配包自动生成章节剧情摘要")
    parser.add_argument("--pack-name", required=True, help="适配包名称，例如 dpcq_ch1_20")
    parser.add_argument("--batch-size", type=int, default=3, help="每次生成多少章，默认 3")
    parser.add_argument("--chapter-start", type=int, default=None)
    parser.add_argument("--chapter-end", type=int, default=None)
    parser.add_argument("--text-model", default=ArkProvider.DEFAULT_BRIEF_TEXT_MODEL)
    parser.add_argument("--source-notes-file", default=None, help="可选，补充设定、原作说明或人工校对意见")
    parser.add_argument("--source-dir", default=None, help="默认自动读取 adaptations/<pack>/source/chapters")
    parser.add_argument("--source-max-chars", type=int, default=2500, help="每章喂给模型的原文最大字数")
    parser.add_argument("--force", action="store_true", help="即使已有非占位摘要也强制覆盖")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack = get_adaptation_pack(args.pack_name)
    provider = ArkProvider.from_local_secrets(
        root_dir=PROJECT_ROOT,
        image_model=ArkProvider.DEFAULT_IMAGE_MODEL,
        video_model=ArkProvider.DEFAULT_VIDEO_MODEL,
        text_model=args.text_model,
    )
    if provider is None:
        raise SystemExit("未找到 Ark API key，无法调用文本模型生成章节摘要。")

    chapter_briefs_path = pack.root_dir / "chapter_briefs.json"
    briefs = json.loads(chapter_briefs_path.read_text(encoding="utf-8"))
    selected = [
        item
        for item in briefs
        if (args.chapter_start is None or int(item["chapter"]) >= args.chapter_start)
        and (args.chapter_end is None or int(item["chapter"]) <= args.chapter_end)
    ]
    if not selected:
        raise SystemExit("没有匹配到需要生成的章节。")

    source_notes = load_source_notes(args.source_notes_file)
    selected_numbers = [int(item["chapter"]) for item in selected]
    chapter_sources = load_available_sources(
        pack_root=pack.root_dir,
        source_dir=args.source_dir,
        chapter_numbers=selected_numbers,
        source_max_chars=args.source_max_chars,
    )
    batch_size = max(1, args.batch_size)
    generated_by_chapter: dict[int, dict] = {}

    for index in range(0, len(selected), batch_size):
        batch = selected[index:index + batch_size]
        batch_sources = {
            int(item["chapter"]): chapter_sources[int(item["chapter"])]
            for item in batch
            if int(item["chapter"]) in chapter_sources
        }
        messages = build_messages(
            source_title=pack.source_title,
            chapter_range=pack.chapter_range,
            batch=batch,
            source_notes=source_notes,
            batch_sources=batch_sources,
        )
        raw = provider.generate_text(
            messages=messages,
            text_model=args.text_model,
            temperature=0.25,
            max_tokens=5000,
        )
        items = parse_json_array(raw)
        for item in items:
            chapter = int(item["chapter"])
            generated_by_chapter[chapter] = normalize_item(item=item, fallback_title=f"第{chapter}章")

    updated: list[dict] = []
    changed_count = 0
    for item in briefs:
        chapter = int(item["chapter"])
        if chapter not in generated_by_chapter:
            updated.append(item)
            continue
        if not args.force and not is_placeholder_brief(item):
            updated.append(item)
            continue
        updated.append({**item, **generated_by_chapter[chapter]})
        changed_count += 1

    chapter_briefs_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = write_generation_report(
        pack_root=pack.root_dir,
        model_name=provider.text_model,
        changed_count=changed_count,
        chapter_start=min(selected_numbers),
        chapter_end=max(selected_numbers),
        source_mode="逐章原文驱动" if chapter_sources else "标题/补充说明驱动",
        source_count=len(chapter_sources),
    )
    print(f"已生成章节摘要：{changed_count} 章")
    print(f"模型：{provider.text_model}")
    print(f"文件：{chapter_briefs_path}")
    print(f"报告：{report_path}")
    return 0


def load_source_notes(source_notes_file: str | None) -> str:
    if not source_notes_file:
        return ""
    path = Path(source_notes_file)
    if not path.is_absolute():
        path = PROJECT_ROOT / source_notes_file
    if not path.exists():
        raise SystemExit(f"补充说明文件不存在：{path}")
    return path.read_text(encoding="utf-8").strip()


def load_available_sources(
    *,
    pack_root: Path,
    source_dir: str | None,
    chapter_numbers: list[int],
    source_max_chars: int,
) -> dict[int, ChapterSource]:
    if source_dir:
        resolved = Path(source_dir)
        if not resolved.is_absolute():
            resolved = PROJECT_ROOT / source_dir
    else:
        resolved = pack_root / "source"
    if not resolved.exists():
        return {}
    return load_chapter_sources(resolved, chapter_numbers=chapter_numbers, max_chars=source_max_chars)


def build_messages(
    *,
    source_title: str,
    chapter_range: str,
    batch: list[dict],
    source_notes: str,
    batch_sources: dict[int, ChapterSource],
) -> list[dict]:
    chapters = [int(item["chapter"]) for item in batch]
    placeholders = [
        {
            "chapter": int(item["chapter"]),
            "title": item.get("title", f"第{int(item['chapter'])}章"),
        }
        for item in batch
    ]
    source_payload = [
        {
            "chapter": source.chapter,
            "title": source.title,
            "content": source.content,
        }
        for source in batch_sources.values()
    ]
    prompt = {
        "任务": "为小说适配包生成章节剧情摘要，供漫剧分镜与视频生成使用。",
        "原作": source_title,
        "适配范围": chapter_range,
        "本批章节": chapters,
        "输出字段": [
            "chapter",
            "title",
            "summary",
            "key_scene",
            "emotion",
            "fidelity_notes",
            "memorable_line",
            "world_rule",
        ],
        "已有占位标题": placeholders,
        "补充说明": source_notes or "无额外补充说明。",
        "原文章节": source_payload or "当前没有逐章原文，请保守生成，不要编造后期设定。",
        "格式要求": {
            "summary": "60-120 字，说明本章核心冲突、推进和情绪。",
            "key_scene": "一句话写出最适合做漫剧分镜或短视频切片的名场面。",
            "emotion": "2-4 个字，例如压抑、反击、热血、悬念。",
            "fidelity_notes": "一句话写出改编时必须保留的东西，避免魔改。",
            "memorable_line": "若本章有高辨识度台词则写出，没有就写空字符串。",
            "world_rule": "若本章涉及关键设定或规则则写一句，没有就写空字符串。",
        },
        "输出要求": "只输出 JSON 数组，不要写解释，不要加 Markdown。",
    }
    return [
        {"role": "system", "content": ADAPTATION_RULES},
        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False, indent=2)},
    ]


def parse_json_array(raw: str) -> list[dict]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[[\s\S]*\]", text)
        if not match:
            raise SystemExit("模型返回内容不是有效的 JSON 数组，无法解析。")
        data = json.loads(match.group(0))

    if not isinstance(data, list):
        raise SystemExit("模型返回的不是 JSON 数组。")
    return [item for item in data if isinstance(item, dict)]


def normalize_item(*, item: dict, fallback_title: str) -> dict:
    chapter = int(item["chapter"])
    return {
        "chapter": chapter,
        "title": str(item.get("title", fallback_title)).strip() or fallback_title,
        "summary": str(item.get("summary", "")).strip(),
        "key_scene": str(item.get("key_scene", "")).strip(),
        "emotion": str(item.get("emotion", "热血")).strip() or "热血",
        "fidelity_notes": str(item.get("fidelity_notes", "")).strip(),
        "memorable_line": str(item.get("memorable_line", "")).strip(),
        "world_rule": str(item.get("world_rule", "")).strip(),
    }


def is_placeholder_brief(item: dict) -> bool:
    summary = str(item.get("summary", ""))
    key_scene = str(item.get("key_scene", ""))
    return "请填写第" in summary or "请填写第" in key_scene or not summary.strip()


def write_generation_report(
    *,
    pack_root: Path,
    model_name: str,
    changed_count: int,
    chapter_start: int,
    chapter_end: int,
    source_mode: str,
    source_count: int,
) -> Path:
    reports_dir = pack_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "brief_generation_report.md"
    report_path.write_text(
        "\n".join(
            [
                "# 章节摘要生成报告",
                "",
                f"- 时间：{datetime.now().isoformat()}",
                f"- 模型：{model_name}",
                f"- 覆盖章节：{chapter_start}-{chapter_end}",
                f"- 更新章节数：{changed_count}",
                f"- 原文模式：{source_mode}",
                f"- 原文章节数：{source_count}",
                "- 约束：已按还原度、叙事节奏、制作可落地与路人友好度生成。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return report_path


if __name__ == "__main__":
    raise SystemExit(main())
