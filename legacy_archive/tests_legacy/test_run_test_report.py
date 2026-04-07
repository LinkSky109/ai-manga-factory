from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import run_test_report


class RunTestReportTests(unittest.TestCase):
    def test_build_report_uses_requested_base_url_for_smoke_command(self) -> None:
        runtime_report = {
            "ok": True,
            "openapi": {"missing_paths": []},
        }
        with mock.patch.object(run_test_report, "check_runtime_consistency", return_value=runtime_report):
            report = run_test_report.build_report("http://127.0.0.1:8010")

        self.assertEqual(report["smoke_entry"]["command"], "python start_project.py smoke-browser --app-url http://127.0.0.1:8010")
        self.assertEqual(report["recommendations"], [])

    def test_build_report_adds_recommendations_for_missing_runtime_requirements(self) -> None:
        runtime_report = {
            "ok": False,
            "openapi": {"missing_paths": ["/artifacts-index", "/jobs/summary"]},
        }
        with mock.patch.object(run_test_report, "check_runtime_consistency", return_value=runtime_report):
            with mock.patch.object(run_test_report, "SMOKE_SCRIPT", Path("E:/missing/run_frontend_real_media_smoke.mjs")):
                report = run_test_report.build_report("http://127.0.0.1:8000")

        self.assertEqual(len(report["recommendations"]), 3)
        self.assertIn("Fix missing OpenAPI routes: /artifacts-index, /jobs/summary", report["recommendations"])
        self.assertIn("Run `python start_project.py verify-deploy --base-url ...` after restart or deploy.", report["recommendations"])
        self.assertIn("Restore the browser smoke script before enabling the smoke entry.", report["recommendations"])
