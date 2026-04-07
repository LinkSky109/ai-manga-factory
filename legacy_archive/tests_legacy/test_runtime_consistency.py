from __future__ import annotations

import unittest
from urllib.error import HTTPError
from urllib.parse import urlparse

from shared.runtime_consistency import check_runtime_consistency, wait_for_runtime_consistency


class RuntimeConsistencyTests(unittest.TestCase):
    def test_check_runtime_consistency_reports_success(self) -> None:
        def reader(url: str) -> tuple[int, object]:
            endpoint = urlparse(url).path
            if endpoint == "/openapi.json":
                return 200, {
                    "openapi": "3.1.0",
                    "info": {"title": "AI Manga Factory API"},
                    "paths": {
                        "/health": {},
                        "/artifacts-index": {},
                        "/jobs/summary": {},
                        "/jobs": {},
                    },
                }
            return 200, {"endpoint": endpoint, "ok": True}

        report = check_runtime_consistency("http://127.0.0.1:8000/", reader=reader)

        self.assertTrue(report["ok"])
        self.assertEqual(report["base_url"], "http://127.0.0.1:8000")
        self.assertEqual(len(report["checks"]), 4)
        self.assertEqual(report["openapi"]["missing_paths"], [])

    def test_check_runtime_consistency_surfaces_endpoint_and_openapi_failures(self) -> None:
        def reader(url: str) -> tuple[int, object]:
            endpoint = urlparse(url).path
            if endpoint == "/openapi.json":
                return 200, {
                    "openapi": "3.1.0",
                    "info": {"title": "AI Manga Factory API"},
                    "paths": {"/health": {}, "/jobs": {}},
                }
            if endpoint == "/jobs/summary":
                raise HTTPError(url, 503, "Service Unavailable", hdrs=None, fp=None)
            return 200, {"endpoint": endpoint, "ok": True}

        report = check_runtime_consistency("http://127.0.0.1:8000", reader=reader)

        self.assertFalse(report["ok"])
        self.assertEqual(report["openapi"]["missing_paths"], ["/artifacts-index", "/jobs/summary"])
        jobs_summary = next(item for item in report["checks"] if item["endpoint"] == "/jobs/summary")
        self.assertEqual(jobs_summary["status"], 503)
        self.assertFalse(jobs_summary["ok"])

    def test_wait_for_runtime_consistency_retries_until_checker_passes(self) -> None:
        attempts: list[str] = []
        current_time = [0.0]

        def checker(base_url: str) -> dict[str, object]:
            attempts.append(base_url)
            return {"ok": len(attempts) >= 2}

        def now() -> float:
            return current_time[0]

        def sleep(seconds: float) -> None:
            current_time[0] += seconds

        ok = wait_for_runtime_consistency(
            "http://127.0.0.1:8000",
            timeout_seconds=5,
            checker=checker,
            now=now,
            sleep=sleep,
        )

        self.assertTrue(ok)
        self.assertEqual(attempts, ["http://127.0.0.1:8000", "http://127.0.0.1:8000"])
