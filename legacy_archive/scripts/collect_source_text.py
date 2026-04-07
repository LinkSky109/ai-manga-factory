#!/usr/bin/env python3
"""为适配包收集小说原文，支持本地导入、认证抓取和离线 HTML 导入。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

import requests

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.adaptation_packs import get_adaptation_pack
from shared.source_materials import (
    ChapterSource,
    ensure_source_layout,
    extract_chapter_number,
    normalize_text,
    read_text_file,
    write_chapter_markdown,
    write_source_manifest,
)


COMMON_CONTENT_SELECTORS = (
    "article",
    "main",
    "#content",
    "#chaptercontent",
    ".content",
    ".chapter-content",
    ".read-content",
    ".article-content",
    ".entry-content",
)


@dataclass(frozen=True)
class RemoteChapterSpec:
    chapter: int
    title: str
    url: str
    content_selector: str | None = None
    title_selector: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="收集适配包原文章节文本")
    parser.add_argument("--pack-name", required=True, help="适配包名称，例如 dpcq_ch1_20")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--source-file", help="单个 txt/md/json/html 文件")
    source_group.add_argument("--source-dir", help="逐章文件目录，支持 txt/md/html")
    source_group.add_argument("--url-manifest", help="章节链接清单，支持 json 或 txt")
    source_group.add_argument("--toc-url", help="目录页 URL，配合 --link-selector 使用")
    parser.add_argument("--link-selector", help="目录页里的章节链接 CSS 选择器")
    parser.add_argument("--content-selector", help="正文 CSS 选择器")
    parser.add_argument("--title-selector", help="标题 CSS 选择器")
    parser.add_argument("--chapter-start", type=int, default=None, help="限制起始章节")
    parser.add_argument("--chapter-end", type=int, default=None, help="限制结束章节")
    parser.add_argument(
        "--chapter-pattern",
        default=r"(?m)^\s*(?:#+\s*)?(第\s*[0-9零〇一二两三四五六七八九十百千万]+\s*[章话回节卷][^\n\r]*)",
        help="单文件拆章时使用的章节标题正则",
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--user-agent", default="AI Manga Factory Source Collector/1.0")
    parser.add_argument("--header-file", default=None, help="可选，请求头 JSON 文件")
    parser.add_argument("--cookie-file", default=None, help="可选，Cookie JSON 或 key=value 文本")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的 source/chapters 文件")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack = get_adaptation_pack(args.pack_name)
    source_root, chapters_dir = ensure_source_layout(pack.root_dir)
    target_chapters = {
        int(item["chapter"])
        for item in pack.chapter_briefs
        if (args.chapter_start is None or int(item["chapter"]) >= args.chapter_start)
        and (args.chapter_end is None or int(item["chapter"]) <= args.chapter_end)
    }
    if not target_chapters:
        raise SystemExit("没有匹配到适配包中的目标章节。")

    if has_existing_source_content(chapters_dir) and not args.overwrite:
        raise SystemExit("source/chapters 已存在内容；如需覆盖，请加 --overwrite。")

    session = build_session(args)
    chapters = collect_sources(args=args, target_chapters=target_chapters, session=session)
    chapters = [item for item in chapters if item.chapter in target_chapters]
    if not chapters:
        raise SystemExit("没有采集到任何章节内容。")

    chapters = deduplicate_and_sort(chapters)
    missing = sorted(target_chapters.difference({item.chapter for item in chapters}))
    if missing:
        raise SystemExit(f"仍缺少章节：{missing}")

    clear_existing_chapters(chapters_dir)
    for item in chapters:
        write_chapter_markdown(chapters_dir, item)

    collection_mode = infer_collection_mode(args)
    manifest_path = write_source_manifest(
        source_root,
        sources=chapters,
        collection_mode=collection_mode,
        note="请确认你对这些原文内容有合法使用权。",
    )
    report_path = write_collection_report(
        pack_root=pack.root_dir,
        pack_name=pack.pack_name,
        source_title=pack.source_title,
        collection_mode=collection_mode,
        chapter_count=len(chapters),
        missing=missing,
        manifest_path=manifest_path,
    )

    print(f"已收集原文章节：{len(chapters)} 章")
    print(f"清单文件：{manifest_path}")
    print(f"沉淀报告：{report_path}")
    return 0


def has_existing_source_content(chapters_dir: Path) -> bool:
    chapters_dir.mkdir(parents=True, exist_ok=True)
    for item in chapters_dir.iterdir():
        if item.name != ".gitkeep":
            return True
    return False


def build_session(args: argparse.Namespace) -> requests.Session:
    session = requests.Session()
    headers = {"User-Agent": args.user_agent}
    headers.update(load_header_mapping(args.header_file))
    session.headers.update(headers)
    cookies = load_cookie_mapping(args.cookie_file)
    if cookies:
        session.cookies.update(cookies)
    return session


def collect_sources(
    *,
    args: argparse.Namespace,
    target_chapters: set[int],
    session: requests.Session,
) -> list[ChapterSource]:
    if args.source_file:
        return collect_from_file(
            path=resolve_input_path(args.source_file),
            chapter_pattern=args.chapter_pattern,
            starting_chapter=min(target_chapters),
        )
    if args.source_dir:
        return collect_from_dir(
            path=resolve_input_path(args.source_dir),
            starting_chapter=min(target_chapters),
        )
    if args.url_manifest:
        specs = load_remote_specs_from_manifest(
            path=resolve_input_path(args.url_manifest),
            default_start=min(target_chapters),
            content_selector=args.content_selector,
            title_selector=args.title_selector,
        )
        return fetch_remote_chapters(
            specs=specs,
            session=session,
            timeout=args.timeout,
            default_content_selector=args.content_selector,
            default_title_selector=args.title_selector,
        )
    if args.toc_url:
        if not args.link_selector:
            raise SystemExit("使用 --toc-url 时必须同时提供 --link-selector。")
        specs = load_remote_specs_from_toc(
            toc_url=args.toc_url,
            link_selector=args.link_selector,
            chapter_start=args.chapter_start or min(target_chapters),
            chapter_end=args.chapter_end or max(target_chapters),
            timeout=args.timeout,
            session=session,
            content_selector=args.content_selector,
            title_selector=args.title_selector,
        )
        return fetch_remote_chapters(
            specs=specs,
            session=session,
            timeout=args.timeout,
            default_content_selector=args.content_selector,
            default_title_selector=args.title_selector,
        )
    raise SystemExit("未提供有效的原文来源。")


def resolve_input_path(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / raw
    return path


def collect_from_file(*, path: Path, chapter_pattern: str, starting_chapter: int) -> list[ChapterSource]:
    if not path.exists():
        raise SystemExit(f"源文件不存在：{path}")
    suffix = path.suffix.lower()
    if suffix == ".json":
        return load_chapters_from_json(path)
    if suffix in {".html", ".htm"}:
        return [parse_local_html_file(path, fallback_chapter=starting_chapter)]
    text = read_text_file(path)
    return split_text_into_chapters(
        text=text,
        chapter_pattern=chapter_pattern,
        starting_chapter=starting_chapter,
        source_ref=str(path),
    )


def collect_from_dir(*, path: Path, starting_chapter: int) -> list[ChapterSource]:
    if not path.exists() or not path.is_dir():
        raise SystemExit(f"源目录不存在：{path}")
    files = [
        item
        for item in sorted(path.iterdir(), key=sort_key_for_path)
        if item.is_file() and item.suffix.lower() in {".md", ".txt", ".html", ".htm"}
    ]
    if not files:
        raise SystemExit(f"目录里没有可导入的 txt/md/html 文件：{path}")

    chapters: list[ChapterSource] = []
    fallback_chapter = starting_chapter
    for item in files:
        if item.suffix.lower() in {".html", ".htm"}:
            source = parse_local_html_file(item, fallback_chapter=fallback_chapter)
        else:
            source = parse_local_chapter_file(item, fallback_chapter)
        fallback_chapter = max(fallback_chapter, source.chapter + 1)
        chapters.append(source)
    return chapters


def split_text_into_chapters(
    *,
    text: str,
    chapter_pattern: str,
    starting_chapter: int,
    source_ref: str,
) -> list[ChapterSource]:
    normalized = normalize_text(text)
    matches = list(re.finditer(chapter_pattern, normalized))
    if not matches:
        raise SystemExit("单文件中没有识别到章节标题，请改用逐章文件目录或自定义 --chapter-pattern。")

    chapters: list[ChapterSource] = []
    next_fallback = starting_chapter
    for index, match in enumerate(matches):
        title = normalize_text(match.group(1))
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        block = normalize_text(normalized[start:end])
        lines = block.splitlines()
        body = normalize_text("\n".join(lines[1:]))
        chapter = extract_chapter_number(title) or next_fallback
        next_fallback = max(next_fallback, chapter + 1)
        chapters.append(
            ChapterSource(
                chapter=chapter,
                title=title,
                content=body,
                source_type="single_file",
                source_ref=source_ref,
            )
        )
    return chapters


def load_chapters_from_json(path: Path) -> list[ChapterSource]:
    raw = json.loads(read_text_file(path))
    items = raw.get("chapters", []) if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise SystemExit(f"JSON 结构不合法：{path}")

    chapters: list[ChapterSource] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        chapter = int(item.get("chapter", 0) or 0)
        title = str(item.get("title", "")).strip() or f"第{chapter}章"
        content = normalize_text(str(item.get("content", "")).strip())
        if chapter <= 0 or not content:
            continue
        chapters.append(
            ChapterSource(
                chapter=chapter,
                title=title,
                content=content,
                source_type="json_file",
                source_ref=str(path),
            )
        )
    if not chapters:
        raise SystemExit(f"JSON 中没有可用章节：{path}")
    return chapters


def load_remote_specs_from_manifest(
    *,
    path: Path,
    default_start: int,
    content_selector: str | None,
    title_selector: str | None,
) -> list[RemoteChapterSpec]:
    if not path.exists():
        raise SystemExit(f"链接清单不存在：{path}")
    if path.suffix.lower() == ".json":
        payload = json.loads(read_text_file(path))
        if not isinstance(payload, list):
            raise SystemExit("链接清单 JSON 必须是数组。")
        specs: list[RemoteChapterSpec] = []
        fallback = default_start
        for item in payload:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", "")).strip()
            if not url:
                continue
            chapter = int(item.get("chapter") or 0) or fallback
            title = (
                str(item.get("catalog_title", "")).strip()
                or str(item.get("title", "")).strip()
                or f"第{chapter}章"
            )
            specs.append(
                RemoteChapterSpec(
                    chapter=chapter,
                    title=title,
                    url=url,
                    content_selector=str(item.get("content_selector", "")).strip() or content_selector,
                    title_selector=str(item.get("title_selector", "")).strip() or title_selector,
                )
            )
            fallback = chapter + 1
        return specs

    urls = [line.strip() for line in read_text_file(path).splitlines() if line.strip()]
    return [
        RemoteChapterSpec(
            chapter=default_start + index,
            title=f"第{default_start + index}章",
            url=url,
            content_selector=content_selector,
            title_selector=title_selector,
        )
        for index, url in enumerate(urls)
    ]


def load_remote_specs_from_toc(
    *,
    toc_url: str,
    link_selector: str,
    chapter_start: int,
    chapter_end: int,
    timeout: int,
    session: requests.Session,
    content_selector: str | None,
    title_selector: str | None,
) -> list[RemoteChapterSpec]:
    soup = fetch_html_soup(session=session, url=toc_url, timeout=timeout)
    links = soup.select(link_selector)
    if not links:
        raise SystemExit("目录页中没有匹配到任何链接，请检查 --link-selector。")

    specs: list[RemoteChapterSpec] = []
    fallback = chapter_start
    for link in links:
        href = link.get("href")
        if not href:
            continue
        title = normalize_text(link.get_text(" ", strip=True))
        chapter = extract_chapter_number(title) or fallback
        if chapter < chapter_start or chapter > chapter_end:
            continue
        specs.append(
            RemoteChapterSpec(
                chapter=chapter,
                title=title or f"第{chapter}章",
                url=urljoin(toc_url, href),
                content_selector=content_selector,
                title_selector=title_selector,
            )
        )
        fallback = chapter + 1
    if not specs:
        raise SystemExit("目录页解析后没有落在目标章节范围内的链接。")
    return specs


def fetch_remote_chapters(
    *,
    specs: Iterable[RemoteChapterSpec],
    session: requests.Session,
    timeout: int,
    default_content_selector: str | None,
    default_title_selector: str | None,
) -> list[ChapterSource]:
    chapters: list[ChapterSource] = []
    for spec in specs:
        soup = fetch_html_soup(session=session, url=spec.url, timeout=timeout)
        title, content = extract_remote_chapter(
            soup=soup,
            content_selector=spec.content_selector or default_content_selector,
            title_selector=spec.title_selector or default_title_selector,
        )
        chapters.append(
            ChapterSource(
                chapter=spec.chapter,
                title=title or spec.title,
                content=content,
                source_type="remote_page",
                source_ref=spec.url,
            )
        )
    return chapters


def fetch_html_soup(*, session: requests.Session, url: str, timeout: int):
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise SystemExit("网页采集模式依赖 beautifulsoup4，请先安装 requirements.txt。") from exc

    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    response.encoding = response.encoding or response.apparent_encoding or "utf-8"
    html = response.text
    if looks_like_bot_challenge(html):
        raise SystemExit(
            "目标页面返回了人机校验壳，而不是正文。请改用 --cookie-file/--header-file，"
            "或先在浏览器里保存章节 HTML，再用 --source-dir 导入。"
        )
    return BeautifulSoup(html, "html.parser")


def extract_remote_chapter(*, soup, content_selector: str | None, title_selector: str | None) -> tuple[str, str]:
    candidates: list[str] = []
    if title_selector:
        title_node = soup.select_one(title_selector)
        if title_node is not None:
            title = normalize_text(title_node.get_text(" ", strip=True))
            if title:
                candidates.append(title)
    for selector in ("h1", ".chapter-title", ".article-title", ".j_chapterName", "title"):
        node = soup.select_one(selector)
        if node is None:
            continue
        title = normalize_text(node.get_text(" ", strip=True))
        if title:
            candidates.append(title)
    title = choose_best_title(candidates)

    content_node = soup.select_one(content_selector) if content_selector else None
    if content_node is None:
        for selector in COMMON_CONTENT_SELECTORS:
            content_node = soup.select_one(selector)
            if content_node is not None:
                break
    if content_node is None:
        content_node = soup.body
    if content_node is None:
        raise SystemExit("网页中没有找到可提取的正文节点。")

    for selector in ("script", "style", "noscript", "iframe", "header", "footer", "nav", "aside", "form"):
        for node in content_node.select(selector):
            node.decompose()

    paragraphs = [
        normalize_text(node.get_text(" ", strip=True))
        for node in content_node.select("p")
        if normalize_text(node.get_text(" ", strip=True))
    ]
    content = "\n\n".join(paragraphs) if paragraphs else normalize_text(content_node.get_text("\n", strip=True))
    if not content:
        raise SystemExit("网页正文提取结果为空，请调整 --content-selector。")
    return title, content


def choose_best_title(candidates: Iterable[str]) -> str:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        title = simplify_title(raw)
        if not title or title in seen:
            continue
        seen.add(title)
        cleaned.append(title)
    if not cleaned:
        return ""
    for title in cleaned:
        if extract_chapter_number(title) is not None:
            return title
    return cleaned[0]


def simplify_title(raw: str) -> str:
    title = normalize_text(str(raw or "").strip())
    if not title:
        return ""
    for marker in (" _", "_《", " - ", "丨", "|"):
        if marker not in title:
            continue
        head = normalize_text(title.split(marker, 1)[0])
        if extract_chapter_number(head) is not None:
            return head
    trimmed = re.sub(r"\s+\d+$", "", title)
    if trimmed != title and extract_chapter_number(trimmed) is not None:
        return trimmed
    return title


def deduplicate_and_sort(items: list[ChapterSource]) -> list[ChapterSource]:
    merged: dict[int, ChapterSource] = {}
    for item in items:
        if not item.content.strip():
            continue
        merged[item.chapter] = item
    return [merged[key] for key in sorted(merged)]


def clear_existing_chapters(chapters_dir: Path) -> None:
    chapters_dir.mkdir(parents=True, exist_ok=True)
    for path in chapters_dir.iterdir():
        if path.name == ".gitkeep":
            continue
        if path.is_file():
            path.unlink()


def infer_collection_mode(args: argparse.Namespace) -> str:
    if args.source_file:
        suffix = Path(args.source_file).suffix.lower()
        if suffix == ".json":
            return "json_file"
        if suffix in {".html", ".htm"}:
            return "single_html"
        return "single_file"
    if args.source_dir:
        return "source_dir"
    if args.url_manifest:
        return "url_manifest_authenticated" if args.cookie_file or args.header_file else "url_manifest"
    if args.toc_url:
        return "toc_page_authenticated" if args.cookie_file or args.header_file else "toc_page"
    return "unknown"


def sort_key_for_path(path: Path) -> tuple[int, str]:
    chapter = extract_chapter_number(path.stem)
    if chapter is None:
        return (10**9, path.name.lower())
    return (chapter, path.name.lower())


def parse_local_chapter_file(path: Path, fallback_chapter: int) -> ChapterSource:
    text = normalize_text(read_text_file(path))
    lines = text.splitlines()
    title = ""
    body_lines = lines
    if lines and lines[0].lstrip().startswith("#"):
        title = lines[0].lstrip("#").strip()
        body_lines = lines[1:]

    chapter = extract_chapter_number(title) or extract_chapter_number(path.stem) or fallback_chapter
    content = normalize_text("\n".join(body_lines))
    if not content:
        raise SystemExit(f"文件内容为空：{path}")
    return ChapterSource(
        chapter=chapter,
        title=title or f"第{chapter}章",
        content=content,
        source_type="local_dir",
        source_ref=str(path),
    )


def parse_local_html_file(path: Path, fallback_chapter: int) -> ChapterSource:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise SystemExit("HTML 导入模式依赖 beautifulsoup4，请先安装 requirements.txt。") from exc

    html = read_text_file(path)
    soup = BeautifulSoup(html, "html.parser")
    title, content = extract_remote_chapter(soup=soup, content_selector=None, title_selector=None)
    chapter = extract_chapter_number(title) or extract_chapter_number(path.stem) or fallback_chapter
    return ChapterSource(
        chapter=chapter,
        title=title or f"第{chapter}章",
        content=content,
        source_type="saved_html",
        source_ref=str(path),
    )


def load_header_mapping(header_file: str | None) -> dict[str, str]:
    if not header_file:
        return {}
    path = resolve_input_path(header_file)
    if not path.exists():
        raise SystemExit(f"请求头文件不存在：{path}")
    payload = json.loads(read_text_file(path))
    if not isinstance(payload, dict):
        raise SystemExit("请求头文件必须是 JSON 对象。")
    return {str(key): str(value) for key, value in payload.items() if str(value).strip()}


def load_cookie_mapping(cookie_file: str | None) -> dict[str, str]:
    if not cookie_file:
        return {}
    path = resolve_input_path(cookie_file)
    if not path.exists():
        raise SystemExit(f"Cookie 文件不存在：{path}")
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(read_text_file(path))
        if not isinstance(payload, dict):
            raise SystemExit("Cookie JSON 必须是对象。")
        return {str(key): str(value) for key, value in payload.items() if str(value).strip()}

    cookies: dict[str, str] = {}
    for line in read_text_file(path).splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


def looks_like_bot_challenge(html: str) -> bool:
    text = html.lower()
    markers = (
        "probe.js",
        "var buid = \"fffffffffffffffffff\"",
        "human verification",
        "captcha",
    )
    return any(marker in text for marker in markers)


def write_collection_report(
    *,
    pack_root: Path,
    pack_name: str,
    source_title: str,
    collection_mode: str,
    chapter_count: int,
    missing: list[int],
    manifest_path: Path,
) -> Path:
    reports_dir = pack_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / "source_collection_report.md"
    lines = [
        "# 原文采集报告",
        "",
        f"- 时间：{datetime.now().isoformat()}",
        f"- 适配包：{pack_name}",
        f"- 原作：{source_title}",
        f"- 采集方式：{collection_mode}",
        f"- 成功章节数：{chapter_count}",
        f"- 缺失章节：{missing or '无'}",
        f"- 索引文件：{manifest_path}",
        "- 说明：请确认导入内容来自你有权使用的原文、官方梗概或授权页面。",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


if __name__ == "__main__":
    raise SystemExit(main())
