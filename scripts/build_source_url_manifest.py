#!/usr/bin/env python3
"""为适配包生成或回填 source_urls.json。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.adaptation_packs import get_adaptation_pack
from shared.source_materials import extract_chapter_number, normalize_text


CHINESE_DIGITS = "零一二三四五六七八九"


@dataclass(frozen=True)
class TocEntry:
    chapter: int
    title: str
    url: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成或回填适配包的 source_urls.json")
    parser.add_argument("--pack-name", required=True, help="适配包名称，例如 dpcq_ch1_20")
    parser.add_argument(
        "--output",
        default=None,
        help="输出路径，默认 adaptations/<pack>/source/incoming/source_urls.json",
    )
    parser.add_argument("--chapter-start", type=int, default=None)
    parser.add_argument("--chapter-end", type=int, default=None)
    parser.add_argument("--wait-selector", default="body", help="默认 wait_selector")
    parser.add_argument("--content-selector", default=None, help="默认 content_selector")
    parser.add_argument("--title-selector", default=None, help="默认 title_selector")
    parser.add_argument("--force", action="store_true", help="覆盖已有 source_urls.json")

    parser.add_argument("--toc-file", default=None, help="可选，浏览器保存下来的目录页 HTML")
    parser.add_argument("--base-url", default=None, help="目录页里相对链接的基地址")
    parser.add_argument("--link-selector", default=None, help="目录页链接选择器，默认自动猜测")
    parser.add_argument("--merge-existing", action="store_true", help="合并已有 source_urls.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack = get_adaptation_pack(args.pack_name)
    output_path = resolve_output_path(pack_name=args.pack_name, output=args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not args.force and not args.merge_existing:
        raise SystemExit(f"输出文件已存在：{output_path}。如需覆盖请加 --force 或 --merge-existing。")

    wanted_numbers = select_chapters(pack.chapter_briefs, args.chapter_start, args.chapter_end)
    if not wanted_numbers:
        raise SystemExit("没有匹配到目标章节。")

    items = [
        build_base_item(
            chapter=int(item["chapter"]),
            title=normalize_text(str(item.get("title", "")).strip()) or f"第{int(item['chapter'])}章",
            wait_selector=args.wait_selector,
            content_selector=args.content_selector,
            title_selector=args.title_selector,
        )
        for item in pack.chapter_briefs
        if int(item["chapter"]) in wanted_numbers
    ]

    if args.toc_file:
        toc_entries = parse_toc_entries(
            toc_file=resolve_input_path(args.toc_file),
            link_selector=args.link_selector,
            base_url=args.base_url,
        )
        items = merge_toc_entries(
            base_items=items,
            toc_entries=toc_entries,
            wait_selector=args.wait_selector,
            content_selector=args.content_selector,
            title_selector=args.title_selector,
        )

    if args.merge_existing and output_path.exists():
        items = merge_existing_items(
            base_items=items,
            existing_items=json.loads(output_path.read_text(encoding="utf-8")),
            wait_selector=args.wait_selector,
            content_selector=args.content_selector,
            title_selector=args.title_selector,
        )

    output_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 URL 清单：{output_path}")
    print(f"章节数：{len(items)}")
    return 0


def select_chapters(items: list[dict[str, Any]], chapter_start: int | None, chapter_end: int | None) -> list[int]:
    return [
        int(item["chapter"])
        for item in items
        if (chapter_start is None or int(item["chapter"]) >= chapter_start)
        and (chapter_end is None or int(item["chapter"]) <= chapter_end)
    ]


def resolve_output_path(*, pack_name: str, output: str | None) -> Path:
    if output:
        path = Path(output)
        if not path.is_absolute():
            path = PROJECT_ROOT / output
        return path
    return PROJECT_ROOT / "adaptations" / pack_name / "source" / "incoming" / "source_urls.json"


def resolve_input_path(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / raw
    return path


def build_base_item(
    *,
    chapter: int,
    title: str,
    wait_selector: str,
    content_selector: str | None,
    title_selector: str | None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "chapter": chapter,
        "title": title,
        "catalog_title": "",
        "match_aliases": build_match_aliases(chapter, title),
        "match_keywords": build_match_keywords(title),
        "url": "",
        "wait_selector": wait_selector,
    }
    if content_selector:
        item["content_selector"] = content_selector
    if title_selector:
        item["title_selector"] = title_selector
    return item


def parse_toc_entries(*, toc_file: Path, link_selector: str | None, base_url: str | None) -> list[TocEntry]:
    if not toc_file.exists():
        raise SystemExit(f"目录页文件不存在：{toc_file}")
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise SystemExit("解析目录页 HTML 需要 beautifulsoup4。") from exc

    soup = BeautifulSoup(toc_file.read_text(encoding="utf-8"), "html.parser")
    selectors = [link_selector] if link_selector else [
        "a[href*='/chapter/']",
        ".catalog-content a",
        ".chapter-list a",
        ".volume a",
        "a",
    ]
    links = []
    for selector in selectors:
        if not selector:
            continue
        matches = soup.select(selector)
        if matches:
            links = matches
            break
    if not links:
        raise SystemExit("目录页里没有找到任何章节链接，请检查 --link-selector。")

    entries: list[TocEntry] = []
    for link in links:
        href = str(link.get("href", "")).strip()
        if not href:
            continue
        title = normalize_text(link.get_text(" ", strip=True))
        chapter = extract_chapter_number(title)
        if chapter is None:
            continue
        url = urljoin(base_url, href) if base_url else href
        entries.append(TocEntry(chapter=chapter, title=title or f"第{chapter}章", url=url))
    if not entries:
        raise SystemExit("目录页解析到了链接，但没有识别出章节号。")
    return deduplicate_toc_entries(entries)


def deduplicate_toc_entries(entries: list[TocEntry]) -> list[TocEntry]:
    merged: dict[int, TocEntry] = {}
    for item in entries:
        if item.chapter not in merged:
            merged[item.chapter] = item
    return [merged[key] for key in sorted(merged)]


def merge_toc_entries(
    *,
    base_items: list[dict[str, Any]],
    toc_entries: list[TocEntry],
    wait_selector: str,
    content_selector: str | None,
    title_selector: str | None,
) -> list[dict[str, Any]]:
    toc_map = {item.chapter: item for item in toc_entries}
    merged: list[dict[str, Any]] = []
    for item in base_items:
        chapter = int(item["chapter"])
        toc_entry = toc_map.get(chapter)
        if toc_entry is None:
            merged.append(item)
            continue

        catalog_title = toc_entry.title or str(item.get("catalog_title", "")).strip()
        aliases = merge_text_lists(
            ensure_text_list(item.get("match_aliases")),
            build_match_aliases(chapter, item.get("title", ""), catalog_title),
        )
        keywords = merge_text_lists(
            ensure_text_list(item.get("match_keywords")),
            build_match_keywords(item.get("title", ""), catalog_title),
        )

        updated = {
            **item,
            "catalog_title": catalog_title,
            "match_aliases": aliases,
            "match_keywords": keywords,
            "url": toc_entry.url,
            "wait_selector": str(item.get("wait_selector", "")).strip() or wait_selector,
        }
        if content_selector and not str(updated.get("content_selector", "")).strip():
            updated["content_selector"] = content_selector
        if title_selector and not str(updated.get("title_selector", "")).strip():
            updated["title_selector"] = title_selector
        merged.append(updated)
    return merged


def merge_existing_items(
    *,
    base_items: list[dict[str, Any]],
    existing_items: Any,
    wait_selector: str,
    content_selector: str | None,
    title_selector: str | None,
) -> list[dict[str, Any]]:
    if not isinstance(existing_items, list):
        return base_items

    existing_map = {
        int(item.get("chapter", 0)): item
        for item in existing_items
        if isinstance(item, dict) and int(item.get("chapter", 0) or 0) > 0
    }
    merged: list[dict[str, Any]] = []
    for item in base_items:
        chapter = int(item["chapter"])
        existing = existing_map.get(chapter, {})
        catalog_title = normalize_text(str(existing.get("catalog_title", "")).strip())
        aliases = merge_text_lists(
            ensure_text_list(item.get("match_aliases")),
            ensure_text_list(existing.get("match_aliases")),
        )
        keywords = merge_text_lists(
            ensure_text_list(item.get("match_keywords")),
            ensure_text_list(existing.get("match_keywords")),
        )

        updated = {
            **item,
            "catalog_title": catalog_title or str(item.get("catalog_title", "")).strip(),
            "match_aliases": aliases or build_match_aliases(chapter, item.get("title", "")),
            "match_keywords": keywords or build_match_keywords(item.get("title", "")),
            "url": str(existing.get("url", item.get("url", ""))).strip(),
            "wait_selector": str(existing.get("wait_selector", item.get("wait_selector", wait_selector))).strip()
            or wait_selector,
        }

        existing_content_selector = str(existing.get("content_selector", "")).strip()
        if existing_content_selector:
            updated["content_selector"] = existing_content_selector
        elif content_selector and not str(updated.get("content_selector", "")).strip():
            updated["content_selector"] = content_selector

        existing_title_selector = str(existing.get("title_selector", "")).strip()
        if existing_title_selector:
            updated["title_selector"] = existing_title_selector
        elif title_selector and not str(updated.get("title_selector", "")).strip():
            updated["title_selector"] = title_selector

        merged.append(updated)
    return merged


def ensure_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [normalize_text(str(item).strip()) for item in value if normalize_text(str(item).strip())]


def merge_text_lists(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            normalized = normalize_text(str(item).strip())
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
    return merged


def build_match_aliases(chapter: int, *titles: Any) -> list[str]:
    aliases = [
        f"第{chapter}章",
        f"第{int_to_chinese_numeral(chapter)}章",
        str(chapter),
        f"{chapter:04d}",
    ]
    for title in titles:
        normalized = normalize_text(str(title).strip())
        if not normalized:
            continue
        aliases.append(normalized)
        stripped = strip_chapter_heading(normalized)
        if stripped and stripped != normalized:
            aliases.append(stripped)
    return merge_text_lists(aliases)


def build_match_keywords(*texts: Any) -> list[str]:
    keywords: list[str] = []
    for text in texts:
        normalized = normalize_text(str(text).strip())
        if not normalized:
            continue
        stripped = strip_chapter_heading(normalized)
        for candidate in (normalized, stripped):
            compact = re.sub(r"[^\w\u4e00-\u9fff]+", " ", candidate).strip()
            compact = re.sub(r"\s+", " ", compact)
            if compact:
                keywords.append(compact)
            tight = compact.replace(" ", "")
            if tight and tight != compact:
                keywords.append(tight)
    return merge_text_lists(keywords)


def strip_chapter_heading(title: str) -> str:
    return normalize_text(re.sub(r"^第\s*[0-9零一二三四五六七八九十百千万两]+\s*[章节回话卷]\s*[:：、.\- ]*", "", title))


def int_to_chinese_numeral(number: int) -> str:
    if number <= 0:
        return str(number)
    if number < 10:
        return CHINESE_DIGITS[number]
    if number < 20:
        return "十" if number == 10 else f"十{CHINESE_DIGITS[number % 10]}"
    if number < 100:
        tens, ones = divmod(number, 10)
        return f"{CHINESE_DIGITS[tens]}十{CHINESE_DIGITS[ones] if ones else ''}"
    return str(number)


if __name__ == "__main__":
    raise SystemExit(main())
