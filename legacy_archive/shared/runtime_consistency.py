from __future__ import annotations

import json
import time
from collections.abc import Callable
from urllib.error import HTTPError, URLError

RUNTIME_CHECK_ENDPOINTS = ("/health", "/openapi.json", "/artifacts-index", "/jobs/summary")
REQUIRED_OPENAPI_PATHS = frozenset({"/health", "/artifacts-index", "/jobs/summary"})

RuntimeReader = Callable[[str], tuple[int, object]]
RuntimeChecker = Callable[[str], dict[str, object]]


def read_json_url(url: str, *, timeout: int = 10) -> tuple[int, object]:
    import urllib.request

    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = response.read().decode("utf-8", errors="replace")
        try:
            return response.status, json.loads(payload)
        except json.JSONDecodeError:
            return response.status, payload


def check_runtime_consistency(
    base_url: str,
    *,
    reader: RuntimeReader | None = None,
) -> dict[str, object]:
    normalized_base_url = base_url.rstrip("/")
    runtime_reader = reader or read_json_url
    checks: list[dict[str, object]] = []
    openapi_paths: list[str] = []

    for endpoint in RUNTIME_CHECK_ENDPOINTS:
        url = f"{normalized_base_url}{endpoint}"
        item: dict[str, object] = {"endpoint": endpoint, "url": url}
        try:
            status, payload = runtime_reader(url)
            item["status"] = status
            item["ok"] = status == 200
            if endpoint == "/openapi.json" and isinstance(payload, dict):
                paths = payload.get("paths", {})
                if isinstance(paths, dict):
                    openapi_paths = sorted(str(path) for path in paths)
                info = payload.get("info", {})
                item["openapi_title"] = info.get("title") if isinstance(info, dict) else None
                item["openapi_version"] = payload.get("openapi")
            else:
                item["sample"] = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)[:200]
        except HTTPError as exc:
            item["status"] = exc.code
            item["ok"] = False
            item["error"] = str(exc.reason or exc)
        except URLError as exc:
            item["status"] = "error"
            item["ok"] = False
            item["error"] = str(exc.reason or exc)
        except Exception as exc:
            item["status"] = "error"
            item["ok"] = False
            item["error"] = str(exc)
        checks.append(item)

    missing_paths = sorted(path for path in REQUIRED_OPENAPI_PATHS if path not in openapi_paths)
    openapi_ok = bool(openapi_paths) and not missing_paths
    return {
        "base_url": normalized_base_url,
        "checks": checks,
        "openapi": {
            "paths": openapi_paths,
            "required_paths": sorted(REQUIRED_OPENAPI_PATHS),
            "missing_paths": missing_paths,
            "ok": openapi_ok,
        },
        "ok": all(bool(item.get("ok")) for item in checks) and openapi_ok,
    }


def print_runtime_consistency(report: dict[str, object]) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=2))


def wait_for_runtime_consistency(
    base_url: str,
    timeout_seconds: int,
    *,
    checker: RuntimeChecker | None = None,
    now: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> bool:
    runtime_checker = checker or check_runtime_consistency
    now_fn = now or time.time
    sleep_fn = sleep or time.sleep
    deadline = now_fn() + timeout_seconds

    while now_fn() < deadline:
        report = runtime_checker(base_url)
        if bool(report.get("ok")):
            return True
        sleep_fn(1)
    return False
