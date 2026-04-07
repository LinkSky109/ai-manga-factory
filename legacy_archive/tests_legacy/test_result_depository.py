from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from backend.schemas import ArtifactPreview, JobResponse, WorkflowStep
from shared import quark_pan_sync, result_depository


def make_job(*, job_id: int = 7, pack_name: str = "demo_pack") -> JobResponse:
    now = datetime(2026, 3, 30, 12, 0, tzinfo=timezone.utc)
    return JobResponse(
        id=job_id,
        project_id=1,
        project_name="demo-project",
        capability_id="generic",
        status="completed",
        input={
            "adaptation_pack": pack_name,
            "source_title": "测试原作",
            "chapter_range": "1-1",
        },
        workflow=[WorkflowStep(key="run", title="run", description="")],
        artifacts=[ArtifactPreview(artifact_type="markdown", label="说明", path_hint=f"job_{job_id}/notes.md")],
        summary="已完成交付。",
        error=None,
        created_at=now,
        updated_at=now,
    )


class ResultDepositoryRuntimePackReportTests(unittest.TestCase):
    def test_record_job_result_writes_pack_reports_to_runtime_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            artifacts_dir = root / "artifacts"
            adaptations_dir = root / "adaptations"
            job = make_job()
            job_dir = artifacts_dir / "job_7"
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / "notes.md").write_text("ok", encoding="utf-8")

            with mock.patch.object(result_depository, "ARTIFACTS_DIR", artifacts_dir):
                with mock.patch.object(result_depository, "ADAPTATIONS_DIR", adaptations_dir):
                    result_depository.record_job_result(job, "demo-project")

            runtime_reports_dir = artifacts_dir / "pack_reports" / "demo_pack" / "reports"
            self.assertTrue((runtime_reports_dir / "job_7_summary.md").exists())
            self.assertTrue((runtime_reports_dir / "job_7_validation.md").exists())
            self.assertTrue((runtime_reports_dir / "latest_result.md").exists())
            self.assertFalse((adaptations_dir / "demo_pack" / "reports").exists())

    def test_get_latest_pack_result_reads_runtime_pack_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            artifacts_dir = root / "artifacts"
            adaptations_dir = root / "adaptations"
            job = make_job()
            job_dir = artifacts_dir / "job_7"
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / "notes.md").write_text("ok", encoding="utf-8")

            with mock.patch.object(result_depository, "ARTIFACTS_DIR", artifacts_dir):
                with mock.patch.object(result_depository, "ADAPTATIONS_DIR", adaptations_dir):
                    result_depository.record_job_result(job, "demo-project")
                    latest = result_depository.get_latest_pack_result("demo_pack")

            self.assertEqual(latest["job_id"], 7)
            self.assertEqual(latest["source"], "pointer")
            self.assertTrue(latest["pack_summary_url"].startswith("/artifacts/pack_reports/demo_pack/reports/"))
            self.assertTrue(latest["pack_validation_url"].startswith("/artifacts/pack_reports/demo_pack/reports/"))
            self.assertTrue(latest["shared_summary_url"].startswith("/artifacts/pack_reports/demo_pack/reports/"))
            self.assertTrue(latest["shared_validation_url"].startswith("/artifacts/pack_reports/demo_pack/reports/"))

    def test_quark_sync_collects_runtime_pack_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            artifacts_dir = root / "artifacts"
            adaptations_dir = root / "adaptations"
            job = make_job()
            job_dir = artifacts_dir / "job_7"
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / "notes.md").write_text("ok", encoding="utf-8")

            with mock.patch.object(result_depository, "ARTIFACTS_DIR", artifacts_dir):
                with mock.patch.object(result_depository, "ADAPTATIONS_DIR", adaptations_dir):
                    result_depository.record_job_result(job, "demo-project")

            config = quark_pan_sync.build_quark_sync_config(
                {
                    "root_folder": "AI-Manga-Factory",
                    "business_folder": "业务产物",
                    "pack_reports_folder": "适配包汇总",
                    "upload_pack_reports": True,
                    "only_completed_jobs": True,
                }
            )
            with mock.patch.object(quark_pan_sync, "ARTIFACTS_DIR", artifacts_dir):
                with mock.patch.object(quark_pan_sync, "ADAPTATIONS_DIR", adaptations_dir):
                    entries = quark_pan_sync.collect_business_output_entries(config=config, job_ids={7})

            pack_entries = [entry for entry in entries if "适配包汇总" in "/".join(entry.remote_parts)]
            self.assertEqual(len(pack_entries), 3)
            self.assertTrue(
                any(
                    str(entry.local_path).endswith("artifacts\\pack_reports\\demo_pack\\reports\\latest_result.md")
                    for entry in pack_entries
                )
            )


if __name__ == "__main__":
    unittest.main()
