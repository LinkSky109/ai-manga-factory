#!/usr/bin/env python3
"""Attach to an existing Chromium browser session over CDP and export source artifacts."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.adaptation_packs import get_adaptation_pack


@dataclass(frozen=True)
class ExportPaths:
    pack_name: str
    runtime_dir: Path
    incoming_root: Path
    report_path: Path
    targets_path: Path
    storage_state_path: Path
    session_storage_path: Path
    meta_path: Path
    raw_cookies_path: Path
    request_cookies_path: Path
    html_path: Path
    screenshot_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Attach to a live browser session and export source artifacts.")
    parser.add_argument("--pack-name", required=True, help="Adaptation pack name, for example dpcq_ch1_20")
    parser.add_argument("--cdp-url", default="http://127.0.0.1:9333", help="Chrome DevTools Protocol endpoint")
    parser.add_argument("--target-url", default="", help="Preferred target page URL after login succeeds")
    parser.add_argument(
        "--url-contains",
        action="append",
        default=[],
        help="Select a page whose URL contains this text; can be passed multiple times",
    )
    parser.add_argument(
        "--title-contains",
        action="append",
        default=[],
        help="Select a page whose title contains this text; can be passed multiple times",
    )
    parser.add_argument("--wait-selector", default="body", help="Selector that marks the page as ready")
    parser.add_argument("--wait-seconds", type=int, default=900, help="Maximum time to wait for a usable page")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Polling interval while waiting")
    parser.add_argument(
        "--session-origin",
        default="auto",
        help="Capture sessionStorage for this origin, or use auto to read from the target page",
    )
    parser.add_argument("--label", default="manual_catalog_capture", help="Label prefix for exported files")
    parser.add_argument("--skip-screenshot", action="store_true", help="Do not save a screenshot")
    parser.add_argument(
        "--export-page-list-only",
        action="store_true",
        help="Only export current browser targets and exit without waiting",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = build_paths(pack_name=args.pack_name, label=args.label)
    sync_playwright = require_playwright()

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(args.cdp_url)
        contexts = list(browser.contexts)
        if not contexts:
            raise SystemExit("No browser context found on the CDP endpoint.")

        all_pages = collect_pages(contexts)
        targets_payload = build_targets_payload(contexts)
        write_json(paths.targets_path, targets_payload)
        if args.export_page_list_only:
            print(f"Exported current page list: {paths.targets_path}")
            browser.close()
            return 0

        page = wait_for_target_page(
            contexts=contexts,
            target_url=args.target_url,
            url_contains=args.url_contains,
            title_contains=args.title_contains,
            wait_seconds=args.wait_seconds,
            poll_interval=args.poll_interval,
        )

        if args.target_url and normalize_url(page.url) != normalize_url(args.target_url):
            page.goto(args.target_url, wait_until="domcontentloaded", timeout=60000)

        page.wait_for_load_state("domcontentloaded", timeout=60000)
        if args.wait_selector:
            page.wait_for_selector(args.wait_selector, timeout=60000)
        page.wait_for_timeout(1500)

        page_html = page.content()
        paths.html_path.parent.mkdir(parents=True, exist_ok=True)
        paths.html_path.write_text(page_html, encoding="utf-8")

        if not args.skip_screenshot:
            page.screenshot(path=str(paths.screenshot_path), full_page=True)

        context = page.context
        storage_state_saved = False
        try:
            paths.storage_state_path.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(paths.storage_state_path))
            storage_state_saved = True
        except Exception as exc:  # pragma: no cover - depends on live browser backend
            write_json(paths.storage_state_path, {"error": str(exc), "captured_at": datetime.now().isoformat()})

        session_storage = capture_session_storage(page=page, session_origin=args.session_origin)
        if session_storage is not None:
            write_json(paths.session_storage_path, session_storage)

        raw_cookies = context.cookies()
        write_json(paths.raw_cookies_path, raw_cookies)
        request_cookie_payload = build_request_cookie_payload(raw_cookies, page.url)
        write_json(paths.request_cookies_path, request_cookie_payload)

        targets_payload = build_targets_payload(contexts)
        write_json(paths.targets_path, targets_payload)
        meta = {
            "captured_at": datetime.now().isoformat(),
            "pack_name": args.pack_name,
            "cdp_url": args.cdp_url,
            "target_url": args.target_url,
            "selected_page_url": page.url,
            "selected_page_title": page.title(),
            "selected_page_host": urlparse(page.url).netloc,
            "html_path": str(paths.html_path),
            "screenshot_path": str(paths.screenshot_path) if not args.skip_screenshot else "",
            "storage_state_path": str(paths.storage_state_path),
            "session_storage_path": str(paths.session_storage_path) if session_storage is not None else "",
            "raw_cookies_path": str(paths.raw_cookies_path),
            "request_cookies_path": str(paths.request_cookies_path),
            "targets_path": str(paths.targets_path),
            "storage_state_saved": storage_state_saved,
        }
        write_json(paths.meta_path, meta)
        write_report(paths=paths, meta=meta, cookie_count=len(raw_cookies))

        browser.close()

    print(f"Selected page: {meta['selected_page_title']} | {meta['selected_page_url']}")
    print(f"HTML saved to: {paths.html_path}")
    print(f"Request cookies saved to: {paths.request_cookies_path}")
    print(f"Report saved to: {paths.report_path}")
    return 0


def build_paths(*, pack_name: str, label: str) -> ExportPaths:
    pack = get_adaptation_pack(pack_name)
    runtime_dir = PROJECT_ROOT / "data" / "source_sessions" / pack_name / "manual_browser"
    incoming_root = pack.root_dir / "source" / "incoming"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    incoming_root.mkdir(parents=True, exist_ok=True)
    return ExportPaths(
        pack_name=pack_name,
        runtime_dir=runtime_dir,
        incoming_root=incoming_root,
        report_path=pack.root_dir / "reports" / f"{label}_report.md",
        targets_path=runtime_dir / f"{label}_targets.json",
        storage_state_path=runtime_dir / f"{label}_storage_state.json",
        session_storage_path=runtime_dir / f"{label}_session_storage.json",
        meta_path=runtime_dir / f"{label}_meta.json",
        raw_cookies_path=runtime_dir / f"{label}_cookies.json",
        request_cookies_path=incoming_root / "request_cookies.json",
        html_path=incoming_root / f"{label}.html",
        screenshot_path=incoming_root / f"{label}.png",
    )


def require_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise SystemExit("Playwright is required. Install it with requirements-source-ingestion.txt.") from exc
    return sync_playwright


def collect_pages(contexts: list[Any]) -> list[Any]:
    pages: list[Any] = []
    for context in contexts:
        pages.extend(context.pages)
    return pages


def build_targets_payload(contexts: list[Any]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for context_index, context in enumerate(contexts):
        for page_index, page in enumerate(context.pages):
            try:
                title = page.title()
            except Exception:  # pragma: no cover - depends on live browser backend
                title = ""
            entries.append(
                {
                    "context_index": context_index,
                    "page_index": page_index,
                    "url": page.url,
                    "title": title,
                }
            )
    return {
        "captured_at": datetime.now().isoformat(),
        "targets": entries,
    }


def wait_for_target_page(
    *,
    contexts: list[Any],
    target_url: str,
    url_contains: list[str],
    title_contains: list[str],
    wait_seconds: int,
    poll_interval: float,
):
    deadline = time.monotonic() + max(wait_seconds, 1)
    last_seen: list[str] = []
    while time.monotonic() <= deadline:
        pages = collect_pages(contexts)
        page = select_target_page(
            pages=pages,
            target_url=target_url,
            url_contains=url_contains,
            title_contains=title_contains,
        )
        if page is not None:
            return page
        last_seen = [f"{safe_page_title(item)} | {item.url}" for item in pages if item.url]
        time.sleep(max(poll_interval, 0.5))
    detail = "\n".join(last_seen) if last_seen else "(no pages detected)"
    raise SystemExit(f"Timed out waiting for the target page.\nLast seen pages:\n{detail}")


def select_target_page(
    *,
    pages: list[Any],
    target_url: str,
    url_contains: list[str],
    title_contains: list[str],
):
    preferred_host = urlparse(target_url).netloc if target_url else ""
    normalized_target = normalize_url(target_url)
    cleaned_url_contains = [item.strip() for item in url_contains if item.strip()]
    cleaned_title_contains = [item.strip() for item in title_contains if item.strip()]

    exact_match = None
    fuzzy_matches: list[Any] = []
    fallback_matches: list[Any] = []

    for page in pages:
        url = str(page.url or "").strip()
        if not url.startswith("http"):
            continue
        title = safe_page_title(page)
        normalized_url = normalize_url(url)
        host = urlparse(url).netloc

        if normalized_target and normalized_url == normalized_target:
            exact_match = page
            break

        url_hit = any(token in url for token in cleaned_url_contains)
        title_hit = any(token in title for token in cleaned_title_contains)
        if url_hit or title_hit:
            fuzzy_matches.append(page)
            continue

        if preferred_host and host == preferred_host and "passport.yuewen.com" not in host:
            fallback_matches.append(page)
            continue

        if host.endswith("qidian.com") and "passport.yuewen.com" not in host:
            fallback_matches.append(page)

    if exact_match is not None:
        return exact_match
    if fuzzy_matches:
        return fuzzy_matches[0]
    if fallback_matches:
        return fallback_matches[0]
    return None


def capture_session_storage(*, page, session_origin: str) -> dict[str, Any] | None:
    origin = session_origin.strip()
    if not origin:
        return None
    if origin == "auto":
        try:
            origin = page.evaluate("() => window.location.origin")
        except Exception:  # pragma: no cover - depends on live browser backend
            return None
    try:
        items = page.evaluate(
            """() => {
                const result = {};
                for (let index = 0; index < window.sessionStorage.length; index += 1) {
                    const key = window.sessionStorage.key(index);
                    if (key) {
                        result[key] = window.sessionStorage.getItem(key);
                    }
                }
                return result;
            }"""
        )
    except Exception:  # pragma: no cover - depends on live browser backend
        return None
    if not isinstance(items, dict):
        return None
    return {
        "origin": origin,
        "items": items,
    }


def build_request_cookie_payload(cookies: list[dict[str, Any]], page_url: str) -> dict[str, str]:
    host = urlparse(page_url).netloc.lower()
    filtered: dict[str, str] = {}
    for item in cookies:
        name = str(item.get("name", "")).strip()
        value = str(item.get("value", "")).strip()
        domain = str(item.get("domain", "")).lstrip(".").lower()
        if not name or not value:
            continue
        if domain and host and domain not in host and host not in domain:
            if not domain.endswith("qidian.com") and not domain.endswith("yuewen.com"):
                continue
        filtered[name] = value
    return filtered


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_report(*, paths: ExportPaths, meta: dict[str, Any], cookie_count: int) -> None:
    lines = [
        "# Manual Browser Capture Report",
        "",
        f"- Captured At: {meta['captured_at']}",
        f"- Pack: {meta['pack_name']}",
        f"- CDP URL: {meta['cdp_url']}",
        f"- Selected Page: {meta['selected_page_title']}",
        f"- Selected URL: {meta['selected_page_url']}",
        f"- HTML: {meta['html_path']}",
        f"- Screenshot: {meta['screenshot_path'] or 'skipped'}",
        f"- Storage State: {meta['storage_state_path']}",
        f"- Session Storage: {meta['session_storage_path'] or 'not captured'}",
        f"- Raw Cookies: {meta['raw_cookies_path']}",
        f"- Request Cookies: {meta['request_cookies_path']}",
        f"- Targets: {meta['targets_path']}",
        f"- Cookie Count: {cookie_count}",
        "",
    ]
    paths.report_path.parent.mkdir(parents=True, exist_ok=True)
    paths.report_path.write_text("\n".join(lines), encoding="utf-8")


def safe_page_title(page) -> str:
    try:
        return page.title()
    except Exception:  # pragma: no cover - depends on live browser backend
        return ""


def normalize_url(url: str) -> str:
    return str(url or "").strip().rstrip("/")


if __name__ == "__main__":
    raise SystemExit(main())
