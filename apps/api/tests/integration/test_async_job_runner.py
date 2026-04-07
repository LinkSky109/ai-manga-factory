import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


class AsyncJobRunnerIntegrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "integration-async.db"
        os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{self.database_path}"
        os.environ["ARTIFACT_ROOT"] = str(Path(self.temp_dir.name) / "artifacts")
        os.environ["ARCHIVE_ROOT"] = str(Path(self.temp_dir.name) / "archives")
        os.environ["PREVIEW_ROOT"] = str(Path(self.temp_dir.name) / "previews")

        from src.core.config import reset_settings_cache
        from src.infrastructure.db.base import reset_database_cache
        from src.main import create_app

        reset_settings_cache()
        reset_database_cache()
        self.client_manager = TestClient(create_app())
        self.client = self.client_manager.__enter__()

    def tearDown(self) -> None:
        from src.core.config import reset_settings_cache
        from src.infrastructure.db.base import reset_database_cache

        self.client_manager.__exit__(None, None, None)
        reset_database_cache()
        reset_settings_cache()
        self.temp_dir.cleanup()

    def test_async_job_is_consumed_by_worker_runner(self) -> None:
        project_id, chapter_id, workflow_id = self._bootstrap_project()

        job_response = self.client.post(
            "/api/v1/jobs",
            json={
                "project_id": project_id,
                "chapter_id": chapter_id,
                "workflow_id": workflow_id,
                "execution_mode": "async",
                "input": {},
            },
        )
        self.assertEqual(job_response.status_code, 201)
        self.assertEqual(job_response.json()["status"], "queued")

        from src.application.services.async_job_runner import AsyncJobRunner
        from src.infrastructure.db.base import get_session_factory

        runner = AsyncJobRunner(session_factory=get_session_factory(), worker_id="worker-test-1")
        consumed_job_id = runner.consume_next()

        self.assertEqual(consumed_job_id, job_response.json()["id"])

        final_job_response = self.client.get(f"/api/v1/jobs/{consumed_job_id}")
        self.assertEqual(final_job_response.status_code, 200)
        self.assertEqual(final_job_response.json()["status"], "completed")
        self.assertEqual(len(final_job_response.json()["steps"]), 3)

    def test_async_failed_job_can_resume_from_checkpoint(self) -> None:
        project_id, chapter_id, workflow_id = self._bootstrap_project()

        job_response = self.client.post(
            "/api/v1/jobs",
            json={
                "project_id": project_id,
                "chapter_id": chapter_id,
                "workflow_id": workflow_id,
                "execution_mode": "async",
                "input": {"simulate_failure_at_step": "video"},
            },
        )
        self.assertEqual(job_response.status_code, 201)

        from src.application.services.async_job_runner import AsyncJobRunner
        from src.infrastructure.db.base import get_session_factory

        runner = AsyncJobRunner(session_factory=get_session_factory(), worker_id="worker-test-2")
        failed_job_id = runner.consume_next()

        failed_job_response = self.client.get(f"/api/v1/jobs/{failed_job_id}")
        self.assertEqual(failed_job_response.status_code, 200)
        self.assertEqual(failed_job_response.json()["status"], "failed")
        self.assertEqual(failed_job_response.json()["current_step_key"], "video")
        self.assertEqual(len(failed_job_response.json()["checkpoints"]), 1)

        resume_response = self.client.post(
            f"/api/v1/jobs/{failed_job_id}/resume",
            json={"override_input": {}},
        )
        self.assertEqual(resume_response.status_code, 200)
        self.assertEqual(resume_response.json()["status"], "queued")

        resumed_job_id = runner.consume_next()
        self.assertEqual(resumed_job_id, failed_job_id)

        resumed_job_response = self.client.get(f"/api/v1/jobs/{failed_job_id}")
        self.assertEqual(resumed_job_response.status_code, 200)
        self.assertEqual(resumed_job_response.json()["status"], "completed")
        self.assertEqual(len(resumed_job_response.json()["steps"]), 3)
        self.assertIsNone(resumed_job_response.json()["current_step_key"])

    def _bootstrap_project(self) -> tuple[int, int, int]:
        project_response = self.client.post(
            "/api/v1/projects",
            json={"name": "异步执行项目", "description": "Step 5 integration"},
        )
        self.assertEqual(project_response.status_code, 201)
        project_id = project_response.json()["id"]

        chapter_response = self.client.post(
            f"/api/v1/projects/{project_id}/chapters",
            json={"chapter_number": 1, "title": "第一章", "summary": "异步执行起点"},
        )
        self.assertEqual(chapter_response.status_code, 201)
        chapter_id = chapter_response.json()["id"]

        workflow_response = self.client.post(
            "/api/v1/workflows",
            json={
                "project_id": project_id,
                "name": "异步流水线",
                "description": "分镜到配音",
                "routing_mode": "smart",
                "nodes": [
                    {"key": "storyboard", "title": "分镜", "provider_type": "llm"},
                    {"key": "video", "title": "视频", "provider_type": "video"},
                    {"key": "voice", "title": "配音", "provider_type": "voice"},
                ],
                "edges": [
                    {"source": "storyboard", "target": "video"},
                    {"source": "video", "target": "voice"},
                ],
            },
        )
        self.assertEqual(workflow_response.status_code, 201)
        workflow_id = workflow_response.json()["id"]
        return project_id, chapter_id, workflow_id


if __name__ == "__main__":
    unittest.main()
