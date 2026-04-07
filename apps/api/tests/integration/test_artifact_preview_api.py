import os
import tempfile
import unittest
import hashlib
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


class ArtifactPreviewIntegrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "integration-preview.db"
        self.artifact_root = Path(self.temp_dir.name) / "artifacts"
        self.archive_root = Path(self.temp_dir.name) / "archives"
        self.preview_root = Path(self.temp_dir.name) / "previews"
        self.object_storage_root = Path(self.temp_dir.name) / "object-storage"
        self.quark_pan_mirror_root = Path(self.temp_dir.name) / "quark-pan"
        self.aliyundrive_mirror_root = Path(self.temp_dir.name) / "aliyundrive"
        self.archive_index_path = self.archive_root / "index" / "artifact-manifest.json"
        os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{self.database_path}"
        os.environ["ARTIFACT_ROOT"] = str(self.artifact_root)
        os.environ["ARCHIVE_ROOT"] = str(self.archive_root)
        os.environ["PREVIEW_ROOT"] = str(self.preview_root)
        os.environ["ARCHIVE_TARGETS"] = "local-archive,object-storage"
        os.environ["ARCHIVE_INDEX_PATH"] = str(self.archive_index_path)
        os.environ["OBJECT_STORAGE_ROOT"] = str(self.object_storage_root)
        os.environ["OBJECT_STORAGE_BUCKET"] = "factory-tests"
        os.environ["QUARK_PAN_MIRROR_ROOT"] = str(self.quark_pan_mirror_root)
        os.environ["ALIYUNDRIVE_MIRROR_ROOT"] = str(self.aliyundrive_mirror_root)
        os.environ.pop("ARCHIVE_SYNC_MAX_ATTEMPTS", None)

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
        os.environ.pop("ARCHIVE_SYNC_MAX_ATTEMPTS", None)
        for env_key in [
            "OBJECT_STORAGE_MODE",
            "S3_ENDPOINT",
            "S3_BUCKET",
            "S3_ACCESS_KEY_ID",
            "S3_SECRET_ACCESS_KEY",
            "S3_REGION",
            "QUARK_PAN_MODE",
            "QUARK_PAN_MIRROR_ROOT",
            "QUARK_PAN_COOKIE_FILE",
            "AI_MANGA_FACTORY_QUARK_COOKIE",
            "QUARK_PAN_TOKEN",
            "ALIYUNDRIVE_MODE",
            "ALIYUNDRIVE_MIRROR_ROOT",
            "ALIYUNDRIVE_CONFIG_DIR",
            "ALIYUNDRIVE_NAME",
            "ALIYUNDRIVE_CHECK_NAME_MODE",
        ]:
            os.environ.pop(env_key, None)
        self.temp_dir.cleanup()

    def test_completed_job_creates_archived_preview_resources(self) -> None:
        project_id, chapter_id, workflow_id = self._bootstrap_project()

        job_response = self.client.post(
            "/api/v1/jobs",
            json={
                "project_id": project_id,
                "chapter_id": chapter_id,
                "workflow_id": workflow_id,
                "execution_mode": "sync",
                "input": {},
            },
        )
        self.assertEqual(job_response.status_code, 201)
        self.assertEqual(job_response.json()["status"], "completed")

        previews_response = self.client.get(f"/api/v1/projects/{project_id}/previews")
        self.assertEqual(previews_response.status_code, 200)
        items = previews_response.json()["items"]
        self.assertEqual(len(items), 3)
        self.assertTrue(all(item["playback_url"] for item in items))
        self.assertTrue(all(item["artifact_id"] for item in items))
        self.assertTrue(all(item["archive_status"] == "archived" for item in items))
        self.assertTrue(all(set(item["archive_targets"]) == {"local-archive", "object-storage"} for item in items))

        storyboard_item = next(item for item in items if item["stage_key"] == "storyboard")
        storyboard_response = self.client.get(storyboard_item["playback_url"])
        self.assertEqual(storyboard_response.status_code, 200)
        self.assertIn("text/html", storyboard_response.headers["content-type"])
        self.assertIn("分镜", storyboard_response.text)

        audio_item = next(item for item in items if item["stage_key"] == "voice")
        audio_response = self.client.get(audio_item["playback_url"])
        self.assertEqual(audio_response.status_code, 200)
        self.assertTrue(audio_response.headers["content-type"].startswith("audio/"))
        self.assertGreater(len(audio_response.content), 44)

        from src.infrastructure.db.base import get_session_factory
        from src.infrastructure.db.models import ArtifactArchiveModel, ArtifactModel

        session = get_session_factory()()
        try:
            artifacts = session.query(ArtifactModel).order_by(ArtifactModel.id.asc()).all()
            archives = session.query(ArtifactArchiveModel).order_by(ArtifactArchiveModel.id.asc()).all()
        finally:
            session.close()

        self.assertEqual(len(artifacts), 3)
        self.assertEqual(len(archives), 6)
        self.assertTrue(all((self.preview_root / artifact.preview_path).exists() for artifact in artifacts))
        local_archives = [archive for archive in archives if archive.archive_type == "local-archive"]
        object_archives = [archive for archive in archives if archive.archive_type == "object-storage"]
        self.assertEqual(len(local_archives), 3)
        self.assertEqual(len(object_archives), 3)
        self.assertTrue(all((self.archive_root / archive.archive_path).exists() for archive in local_archives))
        self.assertTrue(all((self.object_storage_root / archive.archive_path).exists() for archive in object_archives))

        import json

        manifest = json.loads(self.archive_index_path.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest), 6)
        self.assertEqual(
            {entry["archive_type"] for entry in manifest.values()},
            {"local-archive", "object-storage"},
        )

        artifacts_response = self.client.get(f"/api/v1/assets/artifacts?project_id={project_id}")
        self.assertEqual(artifacts_response.status_code, 200)
        artifact_items = artifacts_response.json()
        self.assertEqual(len(artifact_items), 3)
        self.assertTrue(all(len(item["archives"]) == 2 for item in artifact_items))

        first_artifact = artifact_items[0]
        object_storage_archive = next(
            archive for archive in first_artifact["archives"] if archive["archive_type"] == "object-storage"
        )
        self.assertEqual(object_storage_archive["status"], "archived")
        self.assertTrue(object_storage_archive["remote_url"].startswith("s3://factory-tests/"))
        self.assertIsNotNone(object_storage_archive["checksum_sha256"])

        detail_response = self.client.get(f"/api/v1/assets/artifacts/{first_artifact['id']}")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["id"], first_artifact["id"])
        self.assertEqual(len(detail_response.json()["archives"]), 2)
        self.assertEqual(detail_response.json()["preview_url"], f"/api/v1/previews/artifacts/{first_artifact['id']}")
        self.assertIn("checksum_sha256", detail_response.json()["artifact_metadata"])

        expected_checksum = hashlib.sha256(
            (self.artifact_root / detail_response.json()["artifact_path"]).read_bytes()
        ).hexdigest()
        self.assertEqual(detail_response.json()["artifact_metadata"]["checksum_sha256"], expected_checksum)
        self.assertTrue(
            all(archive["checksum_sha256"] == expected_checksum for archive in detail_response.json()["archives"])
        )

    def test_storage_targets_and_artifact_resync_are_available(self) -> None:
        project_id, chapter_id, workflow_id = self._bootstrap_project(name="归档补同步项目")

        job_response = self.client.post(
            "/api/v1/jobs",
            json={
                "project_id": project_id,
                "chapter_id": chapter_id,
                "workflow_id": workflow_id,
                "execution_mode": "sync",
                "input": {},
            },
        )
        self.assertEqual(job_response.status_code, 201)

        targets_response = self.client.get("/api/v1/storage/targets")
        self.assertEqual(targets_response.status_code, 200)
        self.assertEqual(
            [item["archive_type"] for item in targets_response.json()["items"]],
            ["local-archive", "object-storage"],
        )
        self.assertTrue(all(item["is_ready"] for item in targets_response.json()["items"]))

        artifacts_response = self.client.get(f"/api/v1/assets/artifacts?project_id={project_id}")
        self.assertEqual(artifacts_response.status_code, 200)
        artifact_id = artifacts_response.json()[0]["id"]

        from src.infrastructure.db.base import get_session_factory
        from src.infrastructure.db.models import ArtifactArchiveModel

        session = get_session_factory()()
        try:
            archive = (
                session.query(ArtifactArchiveModel)
                .filter(
                    ArtifactArchiveModel.artifact_id == artifact_id,
                    ArtifactArchiveModel.archive_type == "local-archive",
                )
                .one()
            )
            archive_path = self.archive_root / archive.archive_path
            if archive_path.exists():
                archive_path.unlink()
            session.delete(archive)
            session.commit()
        finally:
            session.close()

        resync_response = self.client.post(f"/api/v1/assets/artifacts/{artifact_id}/archives/sync")
        self.assertEqual(resync_response.status_code, 200)
        self.assertEqual(len(resync_response.json()["archives"]), 2)
        self.assertEqual(
            {archive["archive_type"] for archive in resync_response.json()["archives"]},
            {"local-archive", "object-storage"},
        )
        restored_archive = next(
            archive
            for archive in resync_response.json()["archives"]
            if archive["archive_type"] == "local-archive"
        )
        self.assertEqual(restored_archive["status"], "archived")
        self.assertTrue((self.archive_root / restored_archive["archive_path"]).exists())

    def test_project_batch_resync_restores_missing_archives(self) -> None:
        project_id, chapter_id, workflow_id = self._bootstrap_project(name="批量重同步项目")

        job_response = self.client.post(
            "/api/v1/jobs",
            json={
                "project_id": project_id,
                "chapter_id": chapter_id,
                "workflow_id": workflow_id,
                "execution_mode": "sync",
                "input": {},
            },
        )
        self.assertEqual(job_response.status_code, 201)

        artifacts_response = self.client.get(f"/api/v1/assets/artifacts?project_id={project_id}")
        self.assertEqual(artifacts_response.status_code, 200)
        artifact_ids = [item["id"] for item in artifacts_response.json()]

        from src.infrastructure.db.base import get_session_factory
        from src.infrastructure.db.models import ArtifactArchiveModel

        session = get_session_factory()()
        try:
            archives = (
                session.query(ArtifactArchiveModel)
                .filter(
                    ArtifactArchiveModel.artifact_id.in_(artifact_ids),
                    ArtifactArchiveModel.archive_type == "local-archive",
                )
                .all()
            )
            for archive in archives:
                archive_path = self.archive_root / archive.archive_path
                if archive_path.exists():
                    archive_path.unlink()
                session.delete(archive)
            session.commit()
        finally:
            session.close()

        batch_resync_response = self.client.post(f"/api/v1/projects/{project_id}/artifacts/archives/sync")
        self.assertEqual(batch_resync_response.status_code, 200)
        self.assertEqual(batch_resync_response.json()["synced_artifacts"], len(artifact_ids))
        self.assertEqual(batch_resync_response.json()["restored_targets"], len(artifact_ids) * 2)

        refreshed_response = self.client.get(f"/api/v1/assets/artifacts?project_id={project_id}")
        self.assertEqual(refreshed_response.status_code, 200)
        self.assertTrue(all(len(item["archives"]) == 2 for item in refreshed_response.json()))

    def test_archive_sync_runs_can_be_queued_and_consumed(self) -> None:
        project_id, chapter_id, workflow_id = self._bootstrap_project(name="远端归档队列项目")

        job_response = self.client.post(
            "/api/v1/jobs",
            json={
                "project_id": project_id,
                "chapter_id": chapter_id,
                "workflow_id": workflow_id,
                "execution_mode": "sync",
                "input": {},
            },
        )
        self.assertEqual(job_response.status_code, 201)

        artifacts_response = self.client.get(f"/api/v1/assets/artifacts?project_id={project_id}")
        self.assertEqual(artifacts_response.status_code, 200)
        artifact_id = artifacts_response.json()[0]["id"]

        enqueue_response = self.client.post(
            f"/api/v1/assets/artifacts/{artifact_id}/archive-sync-runs",
            json={"archive_types": ["object-storage"]},
        )
        self.assertEqual(enqueue_response.status_code, 201)
        self.assertEqual(len(enqueue_response.json()["items"]), 1)
        self.assertEqual(enqueue_response.json()["items"][0]["status"], "queued")

        from src.application.services.archive_sync_runner import ArchiveSyncRunner
        from src.infrastructure.db.base import get_session_factory

        runner = ArchiveSyncRunner(session_factory=get_session_factory(), worker_id="archive-sync-worker-1")
        consumed_run_id = runner.consume_next()
        self.assertEqual(consumed_run_id, enqueue_response.json()["items"][0]["id"])

        runs_response = self.client.get(f"/api/v1/assets/artifacts/{artifact_id}/archive-sync-runs")
        self.assertEqual(runs_response.status_code, 200)
        self.assertEqual(len(runs_response.json()["items"]), 1)
        self.assertEqual(runs_response.json()["items"][0]["status"], "completed")
        self.assertEqual(runs_response.json()["items"][0]["archive_type"], "object-storage")

        artifact_detail_response = self.client.get(f"/api/v1/assets/artifacts/{artifact_id}")
        self.assertEqual(artifact_detail_response.status_code, 200)
        self.assertEqual(len(artifact_detail_response.json()["sync_runs"]), 1)
        self.assertEqual(artifact_detail_response.json()["sync_runs"][0]["status"], "completed")

    def test_archive_sync_run_retries_until_attempt_limit_then_fails(self) -> None:
        os.environ["ARCHIVE_SYNC_MAX_ATTEMPTS"] = "2"

        project_id, chapter_id, workflow_id = self._bootstrap_project(name="归档重试项目")

        job_response = self.client.post(
            "/api/v1/jobs",
            json={
                "project_id": project_id,
                "chapter_id": chapter_id,
                "workflow_id": workflow_id,
                "execution_mode": "sync",
                "input": {},
            },
        )
        self.assertEqual(job_response.status_code, 201)

        artifacts_response = self.client.get(f"/api/v1/assets/artifacts?project_id={project_id}")
        self.assertEqual(artifacts_response.status_code, 200)
        artifact = artifacts_response.json()[0]
        artifact_id = artifact["id"]
        source_path = self.artifact_root / artifact["artifact_path"]
        source_path.unlink()

        enqueue_response = self.client.post(
            f"/api/v1/assets/artifacts/{artifact_id}/archive-sync-runs",
            json={"archive_types": ["object-storage"]},
        )
        self.assertEqual(enqueue_response.status_code, 201)
        sync_run_id = enqueue_response.json()["items"][0]["id"]

        from src.application.services.archive_sync_runner import ArchiveSyncRunner
        from src.core.config import reset_settings_cache
        from src.infrastructure.db.base import get_session_factory

        reset_settings_cache()
        runner = ArchiveSyncRunner(session_factory=get_session_factory(), worker_id="archive-sync-worker-retry")

        first_attempt_run_id = runner.consume_next()
        self.assertEqual(first_attempt_run_id, sync_run_id)

        runs_response = self.client.get(f"/api/v1/assets/artifacts/{artifact_id}/archive-sync-runs")
        self.assertEqual(runs_response.status_code, 200)
        self.assertEqual(runs_response.json()["items"][0]["status"], "queued")
        self.assertEqual(runs_response.json()["items"][0]["attempt_count"], 1)

        second_attempt_run_id = runner.consume_next()
        self.assertEqual(second_attempt_run_id, sync_run_id)

        failed_runs_response = self.client.get(f"/api/v1/assets/artifacts/{artifact_id}/archive-sync-runs")
        self.assertEqual(failed_runs_response.status_code, 200)
        self.assertEqual(failed_runs_response.json()["items"][0]["status"], "failed")
        self.assertEqual(failed_runs_response.json()["items"][0]["attempt_count"], 2)
        self.assertIn("missing", (failed_runs_response.json()["items"][0]["error_message"] or "").lower())

    def test_completed_job_uploads_to_remote_object_storage_when_s3_mode_enabled(self) -> None:
        os.environ["OBJECT_STORAGE_MODE"] = "s3"
        os.environ["S3_ENDPOINT"] = "https://s3.example.test"
        os.environ["S3_BUCKET"] = "remote-bucket"
        os.environ["S3_ACCESS_KEY_ID"] = "test-key"
        os.environ["S3_SECRET_ACCESS_KEY"] = "test-secret"

        from src.core.config import reset_settings_cache

        reset_settings_cache()

        project_id, chapter_id, workflow_id = self._bootstrap_project(name="远端对象存储项目")
        fake_uploader = _FakeS3Uploader()

        with patch("src.infrastructure.storage.archive_adapters.build_s3_uploader", return_value=fake_uploader):
            job_response = self.client.post(
                "/api/v1/jobs",
                json={
                    "project_id": project_id,
                    "chapter_id": chapter_id,
                    "workflow_id": workflow_id,
                    "execution_mode": "sync",
                    "input": {},
                },
            )

        self.assertEqual(job_response.status_code, 201)
        self.assertEqual(len(fake_uploader.calls), 3)

        artifacts_response = self.client.get(f"/api/v1/assets/artifacts?project_id={project_id}")
        self.assertEqual(artifacts_response.status_code, 200)
        storyboard_artifact = next(
            artifact for artifact in artifacts_response.json() if artifact["step_key"] == "storyboard"
        )
        object_storage_archive = next(
            archive
            for archive in storyboard_artifact["archives"]
            if archive["archive_type"] == "object-storage"
        )
        self.assertEqual(object_storage_archive["remote_url"], "s3://remote-bucket/project_1/chapter_1/job_1/storyboard-artifact.html")
        self.assertFalse(
            (
                self.object_storage_root
                / "remote-bucket"
                / "project_1/chapter_1/job_1/storyboard-artifact.html"
            ).exists()
        )

    def test_completed_job_uploads_to_quark_pan_when_api_mode_enabled(self) -> None:
        os.environ["ARCHIVE_TARGETS"] = "local-archive,quark-pan"
        os.environ["QUARK_PAN_MODE"] = "api"
        os.environ["AI_MANGA_FACTORY_QUARK_COOKIE"] = "quark-cookie"

        from src.core.config import reset_settings_cache

        reset_settings_cache()

        project_id, chapter_id, workflow_id = self._bootstrap_project(name="夸克远端归档项目")
        fake_uploader = _FakeRemoteArchiveUploader()

        with patch("src.infrastructure.storage.archive_adapters.build_quark_pan_remote_uploader", return_value=fake_uploader):
            job_response = self.client.post(
                "/api/v1/jobs",
                json={
                    "project_id": project_id,
                    "chapter_id": chapter_id,
                    "workflow_id": workflow_id,
                    "execution_mode": "sync",
                    "input": {},
                },
            )

        self.assertEqual(job_response.status_code, 201)
        self.assertEqual(len(fake_uploader.calls), 3)
        self.assertEqual(
            fake_uploader.calls[0]["remote_path"],
            "AI-Manga-Factory/project_1/chapter_1/job_1/storyboard-artifact.html",
        )

        artifacts_response = self.client.get(f"/api/v1/assets/artifacts?project_id={project_id}")
        self.assertEqual(artifacts_response.status_code, 200)
        storyboard_artifact = next(
            artifact for artifact in artifacts_response.json() if artifact["step_key"] == "storyboard"
        )
        quark_archive = next(
            archive
            for archive in storyboard_artifact["archives"]
            if archive["archive_type"] == "quark-pan"
        )
        self.assertEqual(quark_archive["remote_url"], "quark://AI-Manga-Factory/project_1/chapter_1/job_1/storyboard-artifact.html")
        self.assertFalse(
            (self.quark_pan_mirror_root / "project_1/chapter_1/job_1/storyboard-artifact.html").exists()
        )

    def _bootstrap_project(self, name: str = "预览归档项目") -> tuple[int, int, int]:
        project_response = self.client.post(
            "/api/v1/projects",
            json={"name": name, "description": "Step 6 integration"},
        )
        self.assertEqual(project_response.status_code, 201)
        project_id = project_response.json()["id"]

        chapter_response = self.client.post(
            f"/api/v1/projects/{project_id}/chapters",
            json={"chapter_number": 1, "title": "第一章", "summary": "预览服务起点"},
        )
        self.assertEqual(chapter_response.status_code, 201)
        chapter_id = chapter_response.json()["id"]

        workflow_response = self.client.post(
            "/api/v1/workflows",
            json={
                "project_id": project_id,
                "name": "预览归档流水线",
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


class _FakeS3Uploader:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def put_object(self, bucket: str, object_key: str, body: bytes, content_type: str | None) -> None:
        self.calls.append(
            {
                "bucket": bucket,
                "object_key": object_key,
                "body": body,
                "content_type": content_type,
            }
        )


class _FakeRemoteArchiveUploader:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def upload(self, remote_path: str, source_file: Path, content_type: str | None = None) -> None:
        self.calls.append(
            {
                "remote_path": remote_path,
                "source_path": str(source_file),
                "content_type": content_type,
            }
        )
