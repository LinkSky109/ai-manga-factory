#!/usr/bin/env python3
"""Capture chapter pages by attaching to an already authenticated Chromium session over CDP."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.adaptation_packs import get_adaptation_pack
from shared.source_materials import normalize_text


@dataclass(frozen=True)
class ChapterSpec:
    chapter: int
    title: str
    url: str
    wait_selector: str = "body"
    title_selector: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture chapter HTML through an existing authenticated browser.")
    parser.add_argument("--pack-name", required=True, help="Adaptation pack name, for example dpcq_ch1_20")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9333", help="Chrome DevTools Protocol endpoint")
    parser.add_argument("--url-manifest", default=None, help="Chapter URL manifest JSON")
    parser.add_argument("--output-dir", default=None, help="Output directory for captured HTML")
    parser.add_argument("--capture-manifest", default=None, help="Capture manifest JSON output path")
    parser.add_argument("--report-path", default=None, help="Markdown report output path")
    parser.add_argument("--chapter-start", type=int, default=None, help="First chapter to capture")
    parser.add_argument("--chapter-end", type=int, default=None, help="Last chapter to capture")
    parser.add_argument("--page-limit", type=int, default=None, help="Limit the number of pages captured")
    parser.add_argument("--wait-selector", default=None, help="Override wait selector for all chapters")
    parser.add_argument("--wait-for-timeout-ms", type=int, default=2500, help="Extra wait after navigation")
    parser.add_argument("--delay-ms", type=int, default=1500, help="Delay between chapters")
    parser.add_argument("--retry-count", type=int, default=2, help="Retries when a challenge page is detected")
    parser.add_argument("--continue-on-error", action="store_true", help="Keep going after a failed chapter")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = build_paths(
        pack_name=args.pack_name,
        output_dir=args.output_dir,
        capture_manifest=args.capture_manifest,
        report_path=args.report_path,
    )
    specs = load_specs(
        pack_name=args.pack_name,
        url_manifest=args.url_manifest,
        chapter_start=args.chapter_start,
        chapter_end=args.chapter_end,
        page_limit=args.page_limit,
        wait_selector_override=args.wait_selector,
    )
    if not specs:
        raise SystemExit("No chapter specs matched the requested range.")

    sync_playwright = require_playwright()
    results: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(args.cdp_url)
        if not browser.contexts:
            raise SystemExit("No browser context found on the CDP endpoint.")
        context = browser.contexts[0]
        page = context.new_page()

        for index, spec in enumerate(specs):
            result = capture_one(
                page=page,
                spec=spec,
                output_dir=paths["output_dir"],
                wait_for_timeout_ms=args.wait_for_timeout_ms,
                retry_count=args.retry_count,
            )
            results.append(result)
            if result.get("status") != "captured" and not args.continue_on_error:
                page.close()
                browser.close()
                write_outputs(paths=paths, pack_name=args.pack_name, cdp_url=args.cdp_url, results=results)
                raise SystemExit(f"Capture stopped on chapter {spec.chapter}: {result.get('error', 'unknown error')}")
            if index < len(specs) - 1 and args.delay_ms > 0:
                page.wait_for_timeout(args.delay_ms)

        page.close()
        browser.close()

    write_outputs(paths=paths, pack_name=args.pack_name, cdp_url=args.cdp_url, results=results)
    success_count = sum(1 for item in results if item.get("status") == "captured")
    failed_count = len(results) - success_count
    print(f"Captured chapters: success {success_count} / failed {failed_count}")
    print(f"HTML output: {paths['output_dir']}")
    print(f"Manifest: {paths['capture_manifest']}")
    print(f"Report: {paths['report_path']}")
    return 0


def build_paths(*, pack_name: str, output_dir: str | None, capture_manifest: str | None, report_path: str | None) -> dict[str, Path]:
    pack = get_adaptation_pack(pack_name)
    output = resolve_path(output_dir) if output_dir else pack.root_dir / "source" / "incoming" / "manual_browser_html"
    manifest = resolve_path(capture_manifest) if capture_manifest else pack.root_dir / "source" / "incoming" / "manual_browser_capture_manifest.json"
    report = resolve_path(report_path) if report_path else pack.root_dir / "reports" / "manual_browser_capture_report.md"
    output.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    return {
        "output_dir": output,
        "capture_manifest": manifest,
        "report_path": report,
    }


def load_specs(
    *,
    pack_name: str,
    url_manifest: str | None,
    chapter_start: int | None,
    chapter_end: int | None,
    page_limit: int | None,
    wait_selector_override: str | None,
) -> list[ChapterSpec]:
    if url_manifest:
        path = resolve_path(url_manifest)
    else:
        pack = get_adaptation_pack(pack_name)
        path = pack.root_dir / "source" / "incoming" / "source_urls.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit(f"Invalid URL manifest: {path}")
    items: list[ChapterSpec] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        chapter = int(item.get("chapter", 0) or 0)
        url = str(item.get("url", "")).strip()
        if chapter <= 0 or not url:
            continue
        if chapter_start is not None and chapter < chapter_start:
            continue
        if chapter_end is not None and chapter > chapter_end:
            continue
        title = normalize_text(str(item.get("catalog_title", "")).strip() or str(item.get("title", "")).strip())
        items.append(
            ChapterSpec(
                chapter=chapter,
                title=title or f"第{chapter}章",
                url=url,
                wait_selector=wait_selector_override or str(item.get("wait_selector", "")).strip() or "body",
                title_selector=str(item.get("title_selector", "")).strip(),
            )
        )
    items.sort(key=lambda value: value.chapter)
    if page_limit is not None:
        items = items[:page_limit]
    return items


def capture_one(*, page, spec: ChapterSpec, output_dir: Path, wait_for_timeout_ms: int, retry_count: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "chapter": spec.chapter,
        "title": spec.title,
        "url": spec.url,
        "started_at": datetime.now().isoformat(),
        "status": "pending",
        "html_path": "",
        "final_url": "",
        "page_title": "",
    }
    last_error = ""
    for attempt in range(retry_count + 1):
        try:
            page.goto(spec.url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector(spec.wait_selector, timeout=60000)
            if wait_for_timeout_ms > 0:
                page.wait_for_timeout(wait_for_timeout_ms)
            html = page.content()
            if looks_like_bot_challenge(html):
                last_error = "bot_challenge"
                continue

            html_path = output_dir / f"chapter_{spec.chapter:04d}.html"
            html_path.write_text(html, encoding="utf-8")
            result.update(
                {
                    "status": "captured",
                    "final_url": page.url,
                    "page_title": safe_page_title(page),
                    "html_path": str(html_path),
                    "finished_at": datetime.now().isoformat(),
                    "attempts": attempt + 1,
                }
            )
            return result
        except Exception as exc:  # pragma: no cover - depends on live browser/backend
            last_error = str(exc)
    result.update(
        {
            "status": "failed",
            "final_url": page.url,
            "page_title": safe_page_title(page),
            "error": last_error or "unknown error",
            "finished_at": datetime.now().isoformat(),
            "attempts": retry_count + 1,
        }
    )
    return result


def write_outputs(*, paths: dict[str, Path], pack_name: str, cdp_url: str, results: list[dict[str, Any]]) -> None:
    manifest = {
        "captured_at": datetime.now().isoformat(),
        "pack_name": pack_name,
        "cdp_url": cdp_url,
        "output_dir": str(paths["output_dir"]),
        "results": results,
    }
    paths["capture_manifest"].write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    success_count = sum(1 for item in results if item.get("status") == "captured")
    failed_count = len(results) - success_count
    lines = [
        "# Manual Browser Chapter Capture Report",
        "",
        f"- Time: {manifest['captured_at']}",
        f"- Pack: {pack_name}",
        f"- CDP URL: {cdp_url}",
        f"- Success: {success_count}",
        f"- Failed: {failed_count}",
        f"- Output Dir: {paths['output_dir']}",
        f"- Manifest: {paths['capture_manifest']}",
        "",
        "## Results",
    ]
    for item in results:
        status = item.get("status", "unknown")
        title = item.get("title", "")
        html_path = item.get("html_path", "") or "-"
        error = item.get("error", "")
        lines.append(f"- Chapter {item.get('chapter')}: {status} | {title} | {html_path}")
        if error:
            lines.append(f"  Error: {error}")
    paths["report_path"].write_text("\n".join(lines), encoding="utf-8")


def looks_like_bot_challenge(html: str) -> bool:
    text = str(html or "")
    markers = (
        "TencentCaptcha",
        "尝试太多",
        "自动为您刷新验证码",
        "/WafCaptcha",
    )
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def require_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise SystemExit("Playwright is required. Install it with requirements-source-ingestion.txt.") from exc
    return sync_playwright


def resolve_path(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / raw
    return path


def safe_page_title(page) -> str:
    try:
        return page.title()
    except Exception:  # pragma: no cover - depends on live browser/backend
        return ""


if __name__ == "__main__":
    raise SystemExit(main())
