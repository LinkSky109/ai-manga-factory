#!/usr/bin/env python3
"""为小说转漫剧项目创建可复用适配包。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.adaptation_packs import DEFAULT_VISUAL_STYLE
from backend.config import ADAPTATIONS_DIR
from shared.asset_lock import ensure_asset_lock_scaffold
from shared.source_materials import ensure_source_layout


def build_briefs(chapter_start: int, chapter_end: int, *, chapter_target_duration_seconds: float | None = None) -> list[dict]:
    briefs = []
    for chapter in range(chapter_start, chapter_end + 1):
        briefs.append(
            {
                "chapter": chapter,
                "title": f"第{chapter}章",
                "summary": f"请填写第 {chapter} 章的剧情摘要。",
                "key_scene": f"请填写第 {chapter} 章最关键的一幕。",
                "emotion": "热血",
                "fidelity_notes": "",
                "memorable_line": "",
                "world_rule": "",
                "target_duration_seconds": chapter_target_duration_seconds,
            }
        )
    return briefs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="创建新的小说适配包")
    parser.add_argument("--pack-name", required=True, help="适配包英文名，例如 dpcq_ch1_20")
    parser.add_argument("--source-title", required=True, help="原作名称，例如 斗破苍穹")
    parser.add_argument("--chapter-start", type=int, default=1)
    parser.add_argument("--chapter-end", type=int, default=20)
    parser.add_argument("--default-project-name", default=None)
    parser.add_argument("--default-scene-count", type=int, default=20)
    parser.add_argument("--default-target-duration-seconds", type=float, default=66.0)
    parser.add_argument("--chapter-target-duration-seconds", type=float, default=None)
    parser.add_argument("--visual-style", default=DEFAULT_VISUAL_STYLE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.chapter_end < args.chapter_start:
        raise SystemExit("chapter-end 必须大于或等于 chapter-start。")

    pack_dir = ADAPTATIONS_DIR / args.pack_name
    reports_dir = pack_dir / "reports"
    if pack_dir.exists():
        raise SystemExit(f"适配包已存在：{pack_dir}")

    reports_dir.mkdir(parents=True, exist_ok=False)
    ensure_source_layout(pack_dir)
    ensure_asset_lock_scaffold(pack_dir, source_title=args.source_title)

    pack_meta = {
        "pack_name": args.pack_name,
        "source_title": args.source_title,
        "chapter_range": f"{args.chapter_start}-{args.chapter_end}",
        "default_project_name": args.default_project_name or args.pack_name.replace("_", "-"),
        "default_scene_count": args.default_scene_count,
        "default_target_duration_seconds": args.default_target_duration_seconds,
        "recommended_visual_style": args.visual_style,
    }
    (pack_dir / "pack.json").write_text(json.dumps(pack_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (pack_dir / "chapter_briefs.json").write_text(
        json.dumps(
            build_briefs(
                args.chapter_start,
                args.chapter_end,
                chapter_target_duration_seconds=args.chapter_target_duration_seconds,
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (pack_dir / "README.md").write_text(
        "\n".join(
            [
                f"# {args.source_title} 适配包",
                "",
                f"- 适配包名：`{args.pack_name}`",
                f"- 章节范围：`{args.chapter_start}-{args.chapter_end}`",
                f"- 默认项目名：`{pack_meta['default_project_name']}`",
                "",
                "## 文件说明",
                "- `pack.json`：适配包元信息",
                "- `chapter_briefs.json`：章节摘要输入或模型生成结果",
                "- `asset_lock.json`：角色 / 场景 / 音色锁定配置",
                "- `assets/`：角色参考图、场景参考图、音色与 LoRA 资产目录",
                "- `source/`：原文章节目录、网页采集模板与索引",
                "- `reports/`：自动沉淀出来的阶段报告和结果索引",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (reports_dir / "README.md").write_text(
        "\n".join(
            [
                "# reports",
                "",
                "每次任务结束后，系统会自动把结果摘要、校验报告和最近一次结果写到这里。",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(f"已创建适配包：{pack_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
