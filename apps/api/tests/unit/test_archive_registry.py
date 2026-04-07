import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class ArchiveRegistryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["ARCHIVE_ROOT"] = str(Path(self.temp_dir.name) / "archives")
        os.environ["ARCHIVE_INDEX_PATH"] = str(Path(self.temp_dir.name) / "archives" / "index" / "manifest.json")
        os.environ["OBJECT_STORAGE_ROOT"] = str(Path(self.temp_dir.name) / "object-storage")
        os.environ["QUARK_PAN_MIRROR_ROOT"] = str(Path(self.temp_dir.name) / "quark-pan")
        os.environ["ALIYUNDRIVE_MIRROR_ROOT"] = str(Path(self.temp_dir.name) / "aliyundrive")
        os.environ["ARCHIVE_TARGETS"] = "local-archive,object-storage,quark-pan,aliyundrive"

        from src.core.config import reset_settings_cache

        reset_settings_cache()

    def tearDown(self) -> None:
        from src.core.config import reset_settings_cache

        reset_settings_cache()
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

    def test_registry_builds_supported_adapters_in_declared_order(self) -> None:
        from src.infrastructure.storage.archive_registry import build_archive_adapters

        adapters = build_archive_adapters()

        self.assertEqual(
            [adapter.archive_type for adapter in adapters],
            ["local-archive", "object-storage", "quark-pan", "aliyundrive"],
        )

    def test_object_storage_adapter_uses_remote_uploader_in_s3_mode(self) -> None:
        os.environ["OBJECT_STORAGE_MODE"] = "s3"
        os.environ["S3_ENDPOINT"] = "https://s3.example.test"
        os.environ["S3_BUCKET"] = "remote-bucket"
        os.environ["S3_ACCESS_KEY_ID"] = "test-key"
        os.environ["S3_SECRET_ACCESS_KEY"] = "test-secret"

        from src.core.config import get_settings, reset_settings_cache
        from src.infrastructure.storage.archive_adapters import ObjectStorageArchiveAdapter

        reset_settings_cache()
        settings = get_settings()
        adapter = ObjectStorageArchiveAdapter(settings)

        source_file = Path(self.temp_dir.name) / "artifact.bin"
        source_file.write_bytes(b"remote-object-payload")
        artifact = SimpleNamespace(
            id=11,
            artifact_path="project_1/chapter_1/job_8/storyboard-artifact.html",
            mime_type="text/html",
        )

        fake_uploader = _FakeS3Uploader()
        with patch("src.infrastructure.storage.archive_adapters.build_s3_uploader", return_value=fake_uploader):
            result = adapter.write(artifact=artifact, source_file=source_file)

        self.assertEqual(adapter.mode, "s3")
        self.assertEqual(result.archive_path, "remote-bucket/project_1/chapter_1/job_8/storyboard-artifact.html")
        self.assertEqual(result.public_url, "s3://remote-bucket/project_1/chapter_1/job_8/storyboard-artifact.html")
        self.assertEqual(len(fake_uploader.calls), 1)
        self.assertEqual(fake_uploader.calls[0]["bucket"], "remote-bucket")
        self.assertEqual(fake_uploader.calls[0]["object_key"], "project_1/chapter_1/job_8/storyboard-artifact.html")
        self.assertEqual(fake_uploader.calls[0]["body"], b"remote-object-payload")
        self.assertFalse(
            (settings.object_storage_root / "remote-bucket" / "project_1/chapter_1/job_8/storyboard-artifact.html").exists()
        )

    def test_object_storage_adapter_reports_blocked_when_s3_config_is_incomplete(self) -> None:
        os.environ["OBJECT_STORAGE_MODE"] = "s3"
        os.environ["S3_ENDPOINT"] = ""
        os.environ["S3_BUCKET"] = ""
        os.environ["S3_ACCESS_KEY_ID"] = ""
        os.environ["S3_SECRET_ACCESS_KEY"] = ""

        from src.core.config import get_settings, reset_settings_cache
        from src.infrastructure.storage.archive_adapters import ObjectStorageArchiveAdapter

        reset_settings_cache()
        adapter = ObjectStorageArchiveAdapter(get_settings())

        description = adapter.describe()

        self.assertEqual(description["mode"], "s3")
        self.assertFalse(description["is_ready"])
        self.assertIn("missing", description["readiness_reason"].lower())

    def test_quark_pan_api_mode_uses_remote_uploader_when_cookie_available(self) -> None:
        cookie_file = Path(self.temp_dir.name) / "secrets" / "quark_cookie.txt"
        cookie_file.parent.mkdir(parents=True, exist_ok=True)
        cookie_file.write_text("quark-cookie", encoding="utf-8")
        os.environ["QUARK_PAN_MODE"] = "api"
        os.environ["QUARK_PAN_COOKIE_FILE"] = str(cookie_file)

        from src.core.config import get_settings, reset_settings_cache
        from src.infrastructure.storage.archive_adapters import QuarkPanArchiveAdapter

        reset_settings_cache()
        settings = get_settings()
        adapter = QuarkPanArchiveAdapter(settings)

        source_file = Path(self.temp_dir.name) / "artifact.bin"
        source_file.write_bytes(b"quark-remote-payload")
        artifact = SimpleNamespace(
            id=12,
            artifact_path="project_1/chapter_1/job_8/storyboard-artifact.html",
            mime_type="text/html",
        )

        fake_uploader = _FakeRemoteArchiveUploader()
        with patch("src.infrastructure.storage.archive_adapters.build_quark_pan_remote_uploader", return_value=fake_uploader):
            result = adapter.write(artifact=artifact, source_file=source_file)

        self.assertEqual(adapter.mode, "api")
        self.assertEqual(result.archive_path, "project_1/chapter_1/job_8/storyboard-artifact.html")
        self.assertEqual(result.public_url, "quark://AI-Manga-Factory/project_1/chapter_1/job_8/storyboard-artifact.html")
        self.assertEqual(
            fake_uploader.calls,
            [
                {
                    "remote_path": "AI-Manga-Factory/project_1/chapter_1/job_8/storyboard-artifact.html",
                    "source_path": str(source_file),
                    "content_type": "text/html",
                }
            ],
        )
        self.assertFalse(
            (settings.quark_pan_mirror_root / "project_1/chapter_1/job_8/storyboard-artifact.html").exists()
        )

    def test_quark_pan_api_mode_reports_blocked_when_cookie_missing(self) -> None:
        os.environ["QUARK_PAN_MODE"] = "api"
        os.environ["QUARK_PAN_COOKIE_FILE"] = str(Path(self.temp_dir.name) / "missing_cookie.txt")

        from src.core.config import get_settings, reset_settings_cache
        from src.infrastructure.storage.archive_adapters import QuarkPanArchiveAdapter

        reset_settings_cache()
        adapter = QuarkPanArchiveAdapter(get_settings())

        with patch("src.infrastructure.storage.archive_adapters.has_quark_pan_dependency", return_value=True):
            description = adapter.describe()

        self.assertEqual(description["mode"], "api")
        self.assertFalse(description["is_ready"])
        self.assertIn("cookie", description["readiness_reason"].lower())

    def test_aliyundrive_api_mode_uses_remote_uploader_when_config_available(self) -> None:
        config_dir = Path(self.temp_dir.name) / "secrets" / "aliyundrive"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "aligo.json").write_text('{"refresh_token": "cached"}', encoding="utf-8")
        os.environ["ALIYUNDRIVE_MODE"] = "api"
        os.environ["ALIYUNDRIVE_CONFIG_DIR"] = str(config_dir)

        from src.core.config import get_settings, reset_settings_cache
        from src.infrastructure.storage.archive_adapters import AliyunDriveArchiveAdapter

        reset_settings_cache()
        settings = get_settings()
        adapter = AliyunDriveArchiveAdapter(settings)

        source_file = Path(self.temp_dir.name) / "voice.wav"
        source_file.write_bytes(b"aliyundrive-remote-payload")
        artifact = SimpleNamespace(
            id=13,
            artifact_path="project_1/chapter_2/job_9/voice-artifact.wav",
            mime_type="audio/wav",
        )

        fake_uploader = _FakeRemoteArchiveUploader()
        with patch("src.infrastructure.storage.archive_adapters.build_aliyundrive_remote_uploader", return_value=fake_uploader):
            result = adapter.write(artifact=artifact, source_file=source_file)

        self.assertEqual(adapter.mode, "api")
        self.assertEqual(result.archive_path, "project_1/chapter_2/job_9/voice-artifact.wav")
        self.assertEqual(result.public_url, "aliyundrive://AI-Manga-Factory/project_1/chapter_2/job_9/voice-artifact.wav")
        self.assertEqual(
            fake_uploader.calls,
            [
                {
                    "remote_path": "AI-Manga-Factory/project_1/chapter_2/job_9/voice-artifact.wav",
                    "source_path": str(source_file),
                    "content_type": "audio/wav",
                }
            ],
        )
        self.assertFalse(
            (settings.aliyundrive_mirror_root / "project_1/chapter_2/job_9/voice-artifact.wav").exists()
        )

    def test_aliyundrive_api_mode_reports_blocked_when_config_missing(self) -> None:
        os.environ["ALIYUNDRIVE_MODE"] = "api"
        os.environ["ALIYUNDRIVE_CONFIG_DIR"] = str(Path(self.temp_dir.name) / "empty_aliyundrive")

        from src.core.config import get_settings, reset_settings_cache
        from src.infrastructure.storage.archive_adapters import AliyunDriveArchiveAdapter

        reset_settings_cache()
        adapter = AliyunDriveArchiveAdapter(get_settings())

        with patch("src.infrastructure.storage.archive_adapters.has_aliyundrive_dependency", return_value=True):
            description = adapter.describe()

        self.assertEqual(description["mode"], "api")
        self.assertFalse(description["is_ready"])
        self.assertIn("config", description["readiness_reason"].lower())


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


if __name__ == "__main__":
    unittest.main()
