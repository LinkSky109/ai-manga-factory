from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_SOURCE_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk", "utf-16")

CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
CHINESE_UNITS = {
    "十": 10,
    "百": 100,
    "千": 1000,
    "万": 10000,
}
CHAPTER_HEADING_RE = re.compile(r"第\s*([0-9零〇一二两三四五六七八九十百千万]+)\s*[章话回节卷]", re.IGNORECASE)


@dataclass(frozen=True)
class ChapterSource:
    chapter: int
    title: str
    content: str
    source_type: str = ""
    source_ref: str = ""


def ensure_source_layout(pack_root: Path) -> tuple[Path, Path]:
    source_root = pack_root / "source"
    chapters_dir = source_root / "chapters"
    incoming_dir = source_root / "incoming"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    incoming_dir.mkdir(parents=True, exist_ok=True)

    readme_path = source_root / "README.md"
    if not readme_path.exists():
        readme_path.write_text(
            "\n".join(
                [
                    "# 原文目录",
                    "",
                    "- `chapters/`：逐章原文，文件名统一为 `chapter_0001.md` 这类格式。",
                    "- `source_manifest.json`：原文采集索引，记录来源、章节号和本地文件路径。",
                    "- `source_urls.template.json`：网页采集模板，填入你有权使用的章节链接。",
                    "",
                    "请只导入你有权使用的小说原文、官方梗概或经授权的网页内容。",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    template_path = source_root / "source_urls.template.json"
    if not template_path.exists():
        template_path.write_text(
            json.dumps(
                [
                    {
                        "chapter": 1,
                        "title": "第1章",
                        "catalog_title": "第1章 示例标题",
                        "match_aliases": [
                            "第1章 示例标题",
                            "示例标题"
                        ],
                        "match_keywords": [
                            "示例标题"
                        ],
                        "url": "https://example.com/chapter-1",
                        "wait_selector": "body",
                        "content_selector": "article",
                        "title_selector": "h1",
                    }
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    header_template_path = source_root / "request_headers.template.json"
    if not header_template_path.exists():
        header_template_path.write_text(
            json.dumps(
                {
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://www.qidian.com/",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    cookie_template_path = source_root / "request_cookies.template.json"
    if not cookie_template_path.exists():
        cookie_template_path.write_text(
            json.dumps(
                {
                    "example_cookie_name": "example_cookie_value"
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    playwright_template_path = source_root / "playwright_capture.template.json"
    if not playwright_template_path.exists():
        playwright_template_path.write_text(
            json.dumps(
                {
                    "login_url": "https://www.qidian.com/login",
                    "browser": "chromium",
                    "wait_until": "domcontentloaded",
                    "wait_selector": "body",
                    "wait_for_timeout_ms": 1500,
                    "url_manifest": "incoming/source_urls.json",
                    "header_file": "incoming/request_headers.json",
                    "cookie_file": "incoming/request_cookies.json",
                    "save_screenshots": False
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    incoming_readme_path = incoming_dir / "README.md"
    if not incoming_readme_path.exists():
        incoming_readme_path.write_text(
            "\n".join(
                [
                    "# 投递入口",
                    "",
                    "把后续准备好的正版原文材料放在这里即可，再执行对应命令导入：",
                    "",
                    "- 逐章 `html`：放到本目录或子目录中",
                    "- 逐章 `txt/md`：放到本目录或子目录中",
                    "- `source_urls.json`：章节 URL 清单",
                    "- `request_headers.json`：请求头",
                    "- `request_cookies.json`：Cookie",
                    "",
                    "推荐目录习惯：",
                    "",
                    "- `incoming/html/`：浏览器保存的逐章 HTML",
                    "- `incoming/text/`：逐章 txt 或 md",
                    "- `incoming/source_urls.json`",
                    "- `incoming/request_headers.json`",
                    "- `incoming/request_cookies.json`",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    incoming_headers_path = incoming_dir / "request_headers.json"
    if not incoming_headers_path.exists():
        incoming_headers_path.write_text(
            json.dumps(
                {
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://www.qidian.com/",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    incoming_cookies_path = incoming_dir / "request_cookies.json"
    if not incoming_cookies_path.exists():
        incoming_cookies_path.write_text(json.dumps({}, ensure_ascii=False, indent=2), encoding="utf-8")

    return source_root, chapters_dir


def read_text_file(path: Path, encodings: Iterable[str] = DEFAULT_SOURCE_ENCODINGS) -> str:
    last_error: UnicodeDecodeError | None = None
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    return path.read_text(encoding="utf-8")


def normalize_text(text: str) -> str:
    normalized = text.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def chinese_numeral_to_int(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)

    total = 0
    section = 0
    number = 0
    used = False
    for char in text:
        if char in CHINESE_DIGITS:
            number = CHINESE_DIGITS[char]
            used = True
            continue
        if char not in CHINESE_UNITS:
            return None
        used = True
        unit = CHINESE_UNITS[char]
        if unit == 10000:
            section = section + number
            if section == 0:
                section = 1
            total += section * unit
            section = 0
            number = 0
            continue
        if number == 0:
            number = 1
        section += number * unit
        number = 0

    if not used:
        return None
    return total + section + number


def extract_chapter_number(text: str) -> int | None:
    raw = str(text or "").strip()
    if not raw:
        return None

    match = CHAPTER_HEADING_RE.search(raw)
    if match:
        token = match.group(1)
        return chinese_numeral_to_int(token)

    digit_match = re.search(r"(?<!\d)(\d{1,5})(?!\d)", raw)
    if digit_match:
        return int(digit_match.group(1))
    return None


def build_chapter_file_name(chapter: int) -> str:
    return f"chapter_{int(chapter):04d}.md"


def write_chapter_markdown(chapters_dir: Path, source: ChapterSource) -> Path:
    chapters_dir.mkdir(parents=True, exist_ok=True)
    output_path = chapters_dir / build_chapter_file_name(source.chapter)
    title = source.title.strip() or f"第{source.chapter}章"
    content = normalize_text(source.content)
    output_path.write_text(f"# {title}\n\n{content}\n", encoding="utf-8")
    return output_path


def write_source_manifest(
    source_root: Path,
    *,
    sources: Iterable[ChapterSource],
    collection_mode: str,
    note: str = "",
) -> Path:
    payload = {
        "collection_mode": collection_mode,
        "note": note,
        "chapters": [
            {
                **asdict(item),
                "path": f"chapters/{build_chapter_file_name(item.chapter)}",
            }
            for item in sorted(sources, key=lambda value: value.chapter)
        ],
    }
    output_path = source_root / "source_manifest.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def load_chapter_sources(
    source_root: Path,
    *,
    chapter_numbers: Iterable[int] | None = None,
    max_chars: int | None = None,
) -> dict[int, ChapterSource]:
    normalized_root = source_root / "chapters" if (source_root / "chapters").exists() else source_root
    wanted = {int(value) for value in chapter_numbers} if chapter_numbers is not None else None
    result: dict[int, ChapterSource] = {}

    for path in sorted(normalized_root.glob("chapter_*.md")) + sorted(normalized_root.glob("chapter_*.txt")):
        item = read_chapter_source(path)
        if wanted is not None and item.chapter not in wanted:
            continue
        content = item.content
        if max_chars is not None and max_chars > 0:
            content = content[:max_chars].strip()
        result[item.chapter] = ChapterSource(
            chapter=item.chapter,
            title=item.title,
            content=content,
            source_type=item.source_type,
            source_ref=item.source_ref,
        )
    return result


def read_chapter_source(path: Path) -> ChapterSource:
    raw_text = read_text_file(path)
    text = normalize_text(raw_text)
    lines = text.splitlines()
    title = ""
    body_lines = lines
    if lines and lines[0].lstrip().startswith("#"):
        title = lines[0].lstrip("#").strip()
        body_lines = lines[1:]

    chapter = extract_chapter_number(title) or extract_chapter_number(path.stem)
    if chapter is None:
        raise ValueError(f"无法从文件名或标题推断章节号：{path}")

    content = normalize_text("\n".join(body_lines))
    if not title:
        title = f"第{chapter}章"
    return ChapterSource(
        chapter=chapter,
        title=title,
        content=content,
        source_type="local_file",
        source_ref=str(path),
    )
