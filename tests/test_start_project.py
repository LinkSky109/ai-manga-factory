from __future__ import annotations

import unittest
from argparse import Namespace
from unittest import mock

import start_project


class StartProjectSmokeTests(unittest.TestCase):
    def test_cmd_smoke_browser_stops_when_runtime_check_fails(self) -> None:
        args = Namespace(
            app_url="http://127.0.0.1:8000",
            pack_name=None,
            project_name=None,
            scene_count=None,
            chapter_start=None,
            chapter_end=None,
            target_duration_seconds=None,
            output_dir=None,
            timeout_ms=None,
        )
        with mock.patch.object(start_project, "check_runtime_consistency", return_value={"ok": False}):
            with mock.patch.object(start_project, "print_runtime_consistency") as printer:
                with mock.patch.object(start_project, "resolve_node") as resolve_node:
                    result = start_project.cmd_smoke_browser(args)

        self.assertEqual(result, 1)
        printer.assert_called_once()
        resolve_node.assert_not_called()

    def test_cmd_smoke_browser_forwards_runtime_arguments_to_env(self) -> None:
        args = Namespace(
            app_url="http://127.0.0.1:8000",
            pack_name="dgyx_ch1_20",
            project_name="runtime-smoke",
            scene_count=2,
            chapter_start=1,
            chapter_end=3,
            target_duration_seconds=60,
            output_dir="E:/work/reports/runtime-smoke",
            timeout_ms=120000,
        )
        with mock.patch.object(start_project, "check_runtime_consistency", return_value={"ok": True}):
            with mock.patch.object(start_project, "print_runtime_consistency"):
                with mock.patch.object(start_project, "resolve_node", return_value="node.exe"):
                    with mock.patch.object(start_project, "run", return_value=0) as run_mock:
                        result = start_project.cmd_smoke_browser(args)

        self.assertEqual(result, 0)
        run_mock.assert_called_once()
        call = run_mock.call_args
        self.assertEqual(call.args[0], ["node.exe", str(start_project.SMOKE_SCRIPT)])
        self.assertEqual(call.kwargs["cwd"], start_project.ROOT)
        env = call.kwargs["env"]
        self.assertEqual(env["AMF_APP_URL"], "http://127.0.0.1:8000")
        self.assertEqual(env["AMF_PACK_NAME"], "dgyx_ch1_20")
        self.assertEqual(env["AMF_PROJECT_NAME"], "runtime-smoke")
        self.assertEqual(env["AMF_SCENE_COUNT"], "2")
        self.assertEqual(env["AMF_CHAPTER_START"], "1")
        self.assertEqual(env["AMF_CHAPTER_END"], "3")
        self.assertEqual(env["AMF_TARGET_DURATION_SECONDS"], "60")
        self.assertEqual(env["AMF_OUTPUT_DIR"], "E:/work/reports/runtime-smoke")
        self.assertEqual(env["AMF_TIMEOUT_MS"], "120000")
