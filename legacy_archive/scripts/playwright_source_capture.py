#!/usr/bin/env python3
"""用 Playwright 为适配包抓取登录后阅读页的章节 HTML。"""

from __future__ import annotations

import argparse
import json
import sys
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
from shared.source_materials import normalize_text


@dataclass(frozen=True)
class ChapterCaptureSpec:
    chapter: int
    title: str
    url: str
    wait_selector: str = ""
    title_selector: str = ""


@dataclass(frozen=True)
class PackPaths:
    pack_name: str
    pack_root: Path
    runtime_dir: Path
    storage_state_path: Path
    session_storage_path: Path
    auth_meta_path: Path
    source_root: Path
    incoming_root: Path
    capture_output_dir: Path
    capture_manifest_path: Path
    capture_report_path: Path
    default_url_manifest_path: Path
    default_header_file_path: Path
    default_cookie_file_path: Path
    default_config_file_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="用 Playwright 抓取登录后阅读页的章节 HTML")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    for name in ("login", "capture"):
        command = subparsers.add_parser(name)
        command.add_argument("--pack-name", required=True, help="适配包名称，例如 dpcq_ch1_20")
        command.add_argument("--config-file", default=None, help="可选，JSON 配置文件")
        command.add_argument("--browser", default=None, help="chromium / firefox / webkit")
        command.add_argument("--channel", default=None, help="例如 msedge 或 chrome")
        command.add_argument("--slow-mo", dest="slow_mo", type=int, default=None, help="操作慢放毫秒数")
        command.add_argument("--timeout-ms", dest="timeout_ms", type=int, default=None, help="页面等待超时")
        command.add_argument("--wait-until", default=None, help="goto 的 wait_until 参数")
        command.add_argument("--storage-state-file", default=None, help="storage state 输出路径")
        command.add_argument("--session-storage-file", default=None, help="sessionStorage 输出路径")
        command.add_argument("--header-file", default=None, help="额外请求头 JSON 文件")
        command.add_argument("--user-agent", default=None, help="可选，自定义 User-Agent")

    login = subparsers.choices["login"]
    login.add_argument("--login-url", default=None, help="登录页 URL")
    login.add_argument("--session-origin", default=None, help="可选，sessionStorage 对应 origin；填 auto 表示登录后自动获取")
    login.add_argument("--headed", dest="headless", action="store_false", default=None, help="显式使用有界面浏览器")
    login.add_argument("--headless", dest="headless", action="store_true", default=None, help="显式使用无头浏览器")

    capture = subparsers.choices["capture"]
    capture.add_argument("--url-manifest", default=None, help="章节 URL 清单 JSON 或 txt")
    capture.add_argument("--output-dir", default=None, help="HTML 输出目录")
    capture.add_argument("--capture-manifest", default=None, help="抓取结果 JSON 路径")
    capture.add_argument("--report-path", default=None, help="抓取报告 Markdown 路径")
    capture.add_argument("--page-limit", type=int, default=None, help="限制抓取页数，便于试跑")
    capture.add_argument("--wait-selector", default=None, help="全局正文等待选择器")
    capture.add_argument("--wait-for-timeout-ms", type=int, default=None, help="页面打开后额外等待毫秒数")
    capture.add_argument("--cookie-file", default=None, help="额外 Cookie 文件；若不填则优先使用 storage state")
    capture.add_argument("--title-selector", default=None, help="标题选择器，用于补充记录标题")
    capture.add_argument("--save-screenshots", dest="save_screenshots", action="store_true", default=None, help="保存页面截图")
    capture.add_argument("--no-save-screenshots", dest="save_screenshots", action="store_false", default=None, help="不保存页面截图")
    capture.add_argument("--headed", dest="headless", action="store_false", default=None, help="使用有界面浏览器")
    capture.add_argument("--headless", dest="headless", action="store_true", default=None, help="使用无头浏览器")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config, config_base_dir = load_config(args.config_file)
    paths = build_pack_paths(args.pack_name)

    if args.mode == "login":
        run_login(args=args, config=config, config_base_dir=config_base_dir, paths=paths)
    else:
        run_capture(args=args, config=config, config_base_dir=config_base_dir, paths=paths)
    return 0


def run_login(*, args: argparse.Namespace, config: dict[str, Any], config_base_dir: Path | None, paths: PackPaths) -> None:
    sync_playwright = require_playwright()
    browser_name = str(resolve_option(args, config, "browser", "chromium")).strip() or "chromium"
    headless = bool(resolve_option(args, config, "headless", False))
    login_url = str(resolve_option(args, config, "login_url", "")).strip()
    if not login_url:
        raise SystemExit("login 模式必须提供 --login-url 或在配置文件中提供 login_url。")

    channel = normalize_optional_text(resolve_option(args, config, "channel", ""))
    slow_mo = int(resolve_option(args, config, "slow_mo", 0) or 0)
    timeout_ms = int(resolve_option(args, config, "timeout_ms", 30000) or 30000)
    wait_until = str(resolve_option(args, config, "wait_until", "domcontentloaded")).strip() or "domcontentloaded"
    storage_state_path = resolve_path_option(
        value=resolve_option(args, config, "storage_state_file", str(paths.storage_state_path)),
        pack_name=paths.pack_name,
        config_base_dir=config_base_dir,
    )
    session_storage_path = resolve_path_option(
        value=resolve_option(args, config, "session_storage_file", str(paths.session_storage_path)),
        pack_name=paths.pack_name,
        config_base_dir=config_base_dir,
    )
    session_origin = normalize_optional_text(resolve_option(args, config, "session_origin", ""))
    header_file = normalize_optional_text(resolve_option(args, config, "header_file", ""))
    user_agent = normalize_optional_text(resolve_option(args, config, "user_agent", ""))
    extra_headers = load_header_mapping(header_file, pack_name=paths.pack_name, config_base_dir=config_base_dir)

    with sync_playwright() as playwright:
        browser_type = getattr(playwright, browser_name, None)
        if browser_type is None:
            raise SystemExit(f"未知浏览器类型：{browser_name}")

        launch_kwargs: dict[str, Any] = {"headless": headless, "slow_mo": slow_mo}
        if channel:
            launch_kwargs["channel"] = channel
        browser = browser_type.launch(**launch_kwargs)

        context_kwargs: dict[str, Any] = {}
        if user_agent:
            context_kwargs["user_agent"] = user_agent
        if extra_headers:
            context_kwargs["extra_http_headers"] = extra_headers
        context = browser.new_context(**context_kwargs)

        page = context.new_page()
        page.goto(login_url, wait_until=wait_until, timeout=timeout_ms)
        print("浏览器已打开，请在页面里完成登录。")
        input("登录完成后回到终端，按回车继续保存认证状态...")

        storage_state_path.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(storage_state_path))

        session_snapshot = capture_session_storage(page=page, session_origin=session_origin)
        if session_snapshot is not None:
            session_storage_path.parent.mkdir(parents=True, exist_ok=True)
            session_storage_path.write_text(json.dumps(session_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

        auth_meta = {
            "captured_at": datetime.now().isoformat(),
            "pack_name": paths.pack_name,
            "login_url": login_url,
            "browser": browser_name,
            "channel": channel,
            "storage_state_path": str(storage_state_path),
            "session_storage_path": str(session_storage_path) if session_snapshot is not None else "",
            "final_url": page.url,
        }
        paths.auth_meta_path.parent.mkdir(parents=True, exist_ok=True)
        paths.auth_meta_path.write_text(json.dumps(auth_meta, ensure_ascii=False, indent=2), encoding="utf-8")

        context.close()
        browser.close()

    report_path = write_login_report(paths=paths, auth_meta=auth_meta, session_snapshot=session_snapshot)
    print(f"已保存登录态：{storage_state_path}")
    if session_snapshot is not None:
        print(f"已保存 sessionStorage：{session_storage_path}")
    print(f"沉淀报告：{report_path}")


def run_capture(*, args: argparse.Namespace, config: dict[str, Any], config_base_dir: Path | None, paths: PackPaths) -> None:
    sync_playwright = require_playwright()
    browser_name = str(resolve_option(args, config, "browser", "chromium")).strip() or "chromium"
    headless = bool(resolve_option(args, config, "headless", True))
    channel = normalize_optional_text(resolve_option(args, config, "channel", ""))
    slow_mo = int(resolve_option(args, config, "slow_mo", 0) or 0)
    timeout_ms = int(resolve_option(args, config, "timeout_ms", 30000) or 30000)
    wait_until = str(resolve_option(args, config, "wait_until", "domcontentloaded")).strip() or "domcontentloaded"
    wait_selector = normalize_optional_text(resolve_option(args, config, "wait_selector", ""))
    title_selector = normalize_optional_text(resolve_option(args, config, "title_selector", ""))
    wait_for_timeout_ms = int(resolve_option(args, config, "wait_for_timeout_ms", 1500) or 1500)
    save_screenshots = bool(resolve_option(args, config, "save_screenshots", False))
    page_limit = resolve_option(args, config, "page_limit", None)
    page_limit = int(page_limit) if page_limit is not None else None

    storage_state_path = resolve_path_option(
        value=resolve_option(args, config, "storage_state_file", str(paths.storage_state_path)),
        pack_name=paths.pack_name,
        config_base_dir=config_base_dir,
    )
    session_storage_path = resolve_path_option(
        value=resolve_option(args, config, "session_storage_file", str(paths.session_storage_path)),
        pack_name=paths.pack_name,
        config_base_dir=config_base_dir,
    )
    output_dir = resolve_path_option(
        value=resolve_option(args, config, "output_dir", str(paths.capture_output_dir)),
        pack_name=paths.pack_name,
        config_base_dir=config_base_dir,
    )
    capture_manifest_path = resolve_path_option(
        value=resolve_option(args, config, "capture_manifest", str(paths.capture_manifest_path)),
        pack_name=paths.pack_name,
        config_base_dir=config_base_dir,
    )
    report_path = resolve_path_option(
        value=resolve_option(args, config, "report_path", str(paths.capture_report_path)),
        pack_name=paths.pack_name,
        config_base_dir=config_base_dir,
    )
    url_manifest_path = resolve_path_option(
        value=resolve_option(args, config, "url_manifest", str(paths.default_url_manifest_path)),
        pack_name=paths.pack_name,
        config_base_dir=config_base_dir,
    )
    header_file = normalize_optional_text(resolve_option(args, config, "header_file", ""))
    cookie_file = normalize_optional_text(resolve_option(args, config, "cookie_file", ""))
    user_agent = normalize_optional_text(resolve_option(args, config, "user_agent", ""))

    specs = load_capture_specs(url_manifest_path)
    if page_limit is not None:
        specs = specs[:page_limit]
    if not specs:
        raise SystemExit(f"URL 清单为空：{url_manifest_path}")

    extra_headers = load_header_mapping(header_file, pack_name=paths.pack_name, config_base_dir=config_base_dir)
    cookies = load_cookie_entries(
        cookie_file,
        pack_name=paths.pack_name,
        config_base_dir=config_base_dir,
        fallback_url=specs[0].url,
    )
    session_snapshot = load_session_storage(session_storage_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir = output_dir / "screenshots"
    if save_screenshots:
        screenshots_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        browser_type = getattr(playwright, browser_name, None)
        if browser_type is None:
            raise SystemExit(f"未知浏览器类型：{browser_name}")

        launch_kwargs: dict[str, Any] = {"headless": headless, "slow_mo": slow_mo}
        if channel:
            launch_kwargs["channel"] = channel
        browser = browser_type.launch(**launch_kwargs)

        context_kwargs: dict[str, Any] = {}
        if storage_state_path.exists():
            context_kwargs["storage_state"] = str(storage_state_path)
        if user_agent:
            context_kwargs["user_agent"] = user_agent
        if extra_headers:
            context_kwargs["extra_http_headers"] = extra_headers
        context = browser.new_context(**context_kwargs)
        if cookies:
            add_cookies_to_context(context=context, cookies=cookies)
        if session_snapshot is not None:
            install_session_storage(context=context, session_snapshot=session_snapshot)

        # 每一章都新开一页，避免前一页的脚本状态污染后续章节。
        for spec in specs:
            page = context.new_page()
            started_at = datetime.now().isoformat()
            record: dict[str, Any] = {
                "chapter": spec.chapter,
                "title": spec.title,
                "url": spec.url,
                "started_at": started_at,
                "status": "pending",
            }
            try:
                page.goto(spec.url, wait_until=wait_until, timeout=timeout_ms)
                selector_to_wait = spec.wait_selector or wait_selector
                if selector_to_wait:
                    page.wait_for_selector(selector_to_wait, timeout=timeout_ms)
                if wait_for_timeout_ms > 0:
                    page.wait_for_timeout(wait_for_timeout_ms)

                html_path = output_dir / f"chapter_{spec.chapter:04d}.html"
                html_path.write_text(page.content(), encoding="utf-8")

                screenshot_path = ""
                if save_screenshots:
                    screenshot_file = screenshots_dir / f"chapter_{spec.chapter:04d}.png"
                    page.screenshot(path=str(screenshot_file), full_page=True)
                    screenshot_path = str(screenshot_file)

                page_title = page.title()
                resolved_title = page_title
                if spec.title_selector:
                    locator = page.locator(spec.title_selector).first
                    if locator.count() > 0:
                        resolved_title = locator.text_content() or page_title
                elif title_selector:
                    locator = page.locator(title_selector).first
                    if locator.count() > 0:
                        resolved_title = locator.text_content() or page_title

                record.update(
                    {
                        "status": "captured",
                        "page_title": normalize_text(resolved_title) or page_title,
                        "final_url": page.url,
                        "html_path": str(html_path),
                        "screenshot_path": screenshot_path,
                        "finished_at": datetime.now().isoformat(),
                    }
                )
            except Exception as exc:
                record.update(
                    {
                        "status": "failed",
                        "error": str(exc),
                        "final_url": page.url,
                        "finished_at": datetime.now().isoformat(),
                    }
                )
            finally:
                page.close()
            results.append(record)

        context.close()
        browser.close()

    capture_manifest = {
        "captured_at": datetime.now().isoformat(),
        "pack_name": paths.pack_name,
        "browser": browser_name,
        "channel": channel,
        "storage_state_path": str(storage_state_path) if storage_state_path.exists() else "",
        "session_storage_path": str(session_storage_path) if session_storage_path.exists() else "",
        "url_manifest_path": str(url_manifest_path),
        "output_dir": str(output_dir),
        "results": results,
    }
    capture_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    capture_manifest_path.write_text(json.dumps(capture_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_capture_report(
        report_path=report_path,
        capture_manifest=capture_manifest,
        save_screenshots=save_screenshots,
    )

    success_count = sum(1 for item in results if item.get("status") == "captured")
    failed_count = len(results) - success_count
    print(f"已抓取章节：成功 {success_count} / 失败 {failed_count}")
    print(f"HTML 输出目录：{output_dir}")
    print(f"抓取清单：{capture_manifest_path}")
    print(f"沉淀报告：{report_path}")


def require_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "未安装 Playwright。请先执行：\n"
            "pip install playwright\n"
            "playwright install"
        ) from exc
    return sync_playwright


def build_pack_paths(pack_name: str) -> PackPaths:
    pack = get_adaptation_pack(pack_name)
    source_root = pack.root_dir / "source"
    incoming_root = source_root / "incoming"
    runtime_dir = PROJECT_ROOT / "data" / "source_sessions" / pack_name
    runtime_dir.mkdir(parents=True, exist_ok=True)
    incoming_root.mkdir(parents=True, exist_ok=True)
    return PackPaths(
        pack_name=pack_name,
        pack_root=pack.root_dir,
        runtime_dir=runtime_dir,
        storage_state_path=runtime_dir / "playwright_auth.json",
        session_storage_path=runtime_dir / "playwright_session_storage.json",
        auth_meta_path=runtime_dir / "playwright_auth_meta.json",
        source_root=source_root,
        incoming_root=incoming_root,
        capture_output_dir=incoming_root / "playwright_html",
        capture_manifest_path=incoming_root / "playwright_capture_manifest.json",
        capture_report_path=pack.root_dir / "reports" / "playwright_capture_report.md",
        default_url_manifest_path=incoming_root / "source_urls.json",
        default_header_file_path=incoming_root / "request_headers.json",
        default_cookie_file_path=incoming_root / "request_cookies.json",
        default_config_file_path=source_root / "playwright_capture.template.json",
    )


def load_config(config_file: str | None) -> tuple[dict[str, Any], Path | None]:
    if not config_file:
        return {}, None
    path = Path(config_file)
    if not path.is_absolute():
        path = PROJECT_ROOT / config_file
    if not path.exists():
        raise SystemExit(f"配置文件不存在：{path}")
    return json.loads(path.read_text(encoding="utf-8")), path.parent


def resolve_option(args: argparse.Namespace, config: dict[str, Any], key: str, default: Any) -> Any:
    value = getattr(args, key, None)
    if value is not None:
        return value
    return config.get(key, default)


def resolve_path_option(*, value: str | Path, pack_name: str, config_base_dir: Path | None) -> Path:
    text = str(value).replace("<pack_name>", pack_name)
    path = Path(text)
    if path.is_absolute():
        return path
    if config_base_dir is not None:
        config_relative = config_base_dir / path
        project_relative = PROJECT_ROOT / path
        if project_relative.exists() and not config_relative.exists():
            return project_relative
        if config_relative.exists():
            return config_relative
        if str(path).startswith(("adaptations\\", "adaptations/", "data\\", "data/")):
            return project_relative
        return config_relative
    return PROJECT_ROOT / path


def normalize_optional_text(value: Any) -> str:
    text = str(value or "").strip()
    return text


def load_capture_specs(path: Path) -> list[ChapterCaptureSpec]:
    if not path.exists():
        raise SystemExit(f"URL 清单不存在：{path}")
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise SystemExit("URL 清单 JSON 必须是数组。")
        specs: list[ChapterCaptureSpec] = []
        for index, item in enumerate(payload, start=1):
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", "")).strip()
            if not url:
                continue
            chapter = int(item.get("chapter", 0) or index)
            title = (
                str(item.get("catalog_title", "")).strip()
                or str(item.get("title", "")).strip()
                or f"第{chapter}章"
            )
            specs.append(
                ChapterCaptureSpec(
                    chapter=chapter,
                    title=title,
                    url=url,
                    wait_selector=str(item.get("wait_selector", "")).strip(),
                    title_selector=str(item.get("title_selector", "")).strip(),
                )
            )
        return [item for item in specs if item.chapter > 0]

    specs = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        url = line.strip()
        if not url:
            continue
        specs.append(ChapterCaptureSpec(chapter=index, title=f"第{index}章", url=url))
    return specs


def capture_session_storage(*, page, session_origin: str) -> dict[str, Any] | None:
    if not session_origin:
        return None
    origin = session_origin
    if session_origin == "auto":
        origin = page.evaluate("() => window.location.origin")
    storage = page.evaluate(
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
    return {
        "origin": origin,
        "items": storage,
    }


def load_session_storage(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return payload


def install_session_storage(*, context, session_snapshot: dict[str, Any]) -> None:
    origin = str(session_snapshot.get("origin", "")).strip()
    items = session_snapshot.get("items", {})
    if not origin or not isinstance(items, dict):
        return
    script = f"""
(() => {{
  const targetOrigin = {json.dumps(origin, ensure_ascii=False)};
  const sessionItems = {json.dumps(items, ensure_ascii=False)};
  if (window.location.origin === targetOrigin) {{
    for (const [key, value] of Object.entries(sessionItems)) {{
      window.sessionStorage.setItem(key, String(value));
    }}
  }}
}})();
"""
    # sessionStorage 不在 Playwright 的 storage_state 中，这里在每个文档加载前主动回填。
    context.add_init_script(script=script)


def load_header_mapping(header_file: str, *, pack_name: str, config_base_dir: Path | None) -> dict[str, str]:
    if not header_file:
        return {}
    path = resolve_path_option(value=header_file, pack_name=pack_name, config_base_dir=config_base_dir)
    if not path.exists():
        raise SystemExit(f"请求头文件不存在：{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("请求头文件必须是 JSON 对象。")
    return {str(key): str(value) for key, value in payload.items() if str(value).strip()}


def load_cookie_entries(
    cookie_file: str,
    *,
    pack_name: str,
    config_base_dir: Path | None,
    fallback_url: str,
) -> list[dict[str, Any]]:
    if not cookie_file:
        return []
    path = resolve_path_option(value=cookie_file, pack_name=pack_name, config_base_dir=config_base_dir)
    if not path.exists():
        raise SystemExit(f"Cookie 文件不存在：{path}")
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            result = []
            for item in payload:
                if not isinstance(item, dict):
                    continue
                if not str(item.get("name", "")).strip():
                    continue
                if "url" not in item and "domain" not in item:
                    item = {**item, "url": fallback_url}
                if "path" not in item:
                    item = {**item, "path": "/"}
                result.append(item)
            return result
        if isinstance(payload, dict):
            return [
                {
                    "name": str(key),
                    "value": str(value),
                    "url": fallback_url,
                    "path": "/",
                }
                for key, value in payload.items()
                if str(value).strip()
            ]
        raise SystemExit("Cookie JSON 必须是对象或数组。")

    cookies: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        cookies.append(
            {
                "name": key.strip(),
                "value": value.strip(),
                "url": fallback_url,
                "path": "/",
            }
        )
    return cookies


def add_cookies_to_context(*, context, cookies: list[dict[str, Any]]) -> None:
    if not cookies:
        return
    normalized = []
    for item in cookies:
        cookie = dict(item)
        url_value = str(cookie.get("url", "")).strip()
        domain_value = str(cookie.get("domain", "")).strip()
        if url_value:
            # Playwright requires either url or domain/path, not both.
            cookie.pop("domain", None)
            cookie.pop("path", None)
        elif domain_value:
            cookie["domain"] = domain_value
            cookie["path"] = str(cookie.get("path", "")).strip() or "/"
        else:
            continue
        normalized.append(cookie)
    context.add_cookies(normalized)


def write_login_report(*, paths: PackPaths, auth_meta: dict[str, Any], session_snapshot: dict[str, Any] | None) -> Path:
    report_path = paths.pack_root / "reports" / "playwright_login_report.md"
    lines = [
        "# Playwright 登录态保存报告",
        "",
        f"- 时间：{auth_meta['captured_at']}",
        f"- 适配包：{paths.pack_name}",
        f"- 登录页：{auth_meta['login_url']}",
        f"- 浏览器：{auth_meta['browser']}",
        f"- 渠道：{auth_meta['channel'] or '默认'}",
        f"- storage state：{auth_meta['storage_state_path']}",
        f"- sessionStorage：{auth_meta['session_storage_path'] or '未保存'}",
        f"- 最终页面：{auth_meta['final_url']}",
        f"- 说明：sessionStorage {'已保存' if session_snapshot is not None else '未保存'}。",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def write_capture_report(*, report_path: Path, capture_manifest: dict[str, Any], save_screenshots: bool) -> None:
    results = list(capture_manifest.get("results", []))
    success_count = sum(1 for item in results if item.get("status") == "captured")
    failed_count = len(results) - success_count
    lines = [
        "# Playwright 章节抓取报告",
        "",
        f"- 时间：{capture_manifest['captured_at']}",
        f"- 适配包：{capture_manifest['pack_name']}",
        f"- 浏览器：{capture_manifest['browser']}",
        f"- 渠道：{capture_manifest.get('channel') or '默认'}",
        f"- URL 清单：{capture_manifest['url_manifest_path']}",
        f"- 输出目录：{capture_manifest['output_dir']}",
        f"- 抓取成功：{success_count}",
        f"- 抓取失败：{failed_count}",
        f"- 截图：{'已开启' if save_screenshots else '未开启'}",
        "",
        "## 结果明细",
    ]
    for item in results:
        status = str(item.get("status", "unknown"))
        title = str(item.get("title", "")).strip() or f"第{item.get('chapter')}章"
        html_path = str(item.get("html_path", "")).strip() or "无"
        error = str(item.get("error", "")).strip()
        lines.append(f"- 第 {item.get('chapter')} 章 | {status} | {title} | {html_path}")
        if error:
            lines.append(f"  错误：{error}")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
