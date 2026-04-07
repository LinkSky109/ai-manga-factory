import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient


class MonitoringApiIntegrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "monitoring.db"
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

    def test_monitoring_overview_reports_budget_alerts_and_worker_health(self) -> None:
        project_response = self.client.post(
            "/api/v1/projects",
            json={"name": "监控项目", "description": "Step 10 integration"},
        )
        self.assertEqual(project_response.status_code, 201)
        project_id = project_response.json()["id"]

        from src.infrastructure.db.base import get_session_factory
        from src.infrastructure.db.repositories.monitoring_repository import MonitoringRepository
        from src.infrastructure.db.repositories.provider_repository import ProviderRepository

        session = get_session_factory()()
        try:
            providers = ProviderRepository(session)
            providers.update_provider_config("llm-story", budget_threshold=100)
            providers.log_usage(
                provider_key="llm-story",
                provider_type="llm",
                project_id=project_id,
                job_run_id=None,
                metric_name="token",
                usage_amount=128,
                usage_unit="tokens",
            )

            monitoring = MonitoringRepository(session)
            monitoring.record_worker_heartbeat(
                worker_id="worker-alpha",
                worker_type="hybrid",
                status="idle",
                seen_at=datetime.now(timezone.utc),
            )
            monitoring.record_worker_heartbeat(
                worker_id="worker-stale",
                worker_type="archive-sync",
                status="idle",
                seen_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            )
            session.commit()
        finally:
            session.close()

        providers_response = self.client.get("/api/v1/monitoring/providers")
        self.assertEqual(providers_response.status_code, 200)
        self.assertTrue(any(item["provider_key"] == "llm-story" for item in providers_response.json()["items"]))

        overview_response = self.client.get("/api/v1/monitoring/overview")
        self.assertEqual(overview_response.status_code, 200)

        payload = overview_response.json()
        self.assertGreaterEqual(payload["summary"]["active_alerts"], 1)
        self.assertGreaterEqual(payload["summary"]["healthy_workers"], 1)
        self.assertGreaterEqual(payload["summary"]["stale_workers"], 1)
        self.assertTrue(any(alert["scope_key"] == "llm-story" for alert in payload["alerts"]))
        self.assertTrue(any(worker["worker_id"] == "worker-alpha" and worker["health_status"] == "healthy" for worker in payload["workers"]))
        self.assertTrue(any(worker["worker_id"] == "worker-stale" and worker["health_status"] == "stale" for worker in payload["workers"]))

    def test_metrics_endpoint_exposes_prometheus_series(self) -> None:
        project_response = self.client.post(
            "/api/v1/projects",
            json={"name": "指标项目", "description": "metrics integration"},
        )
        self.assertEqual(project_response.status_code, 201)
        project_id = project_response.json()["id"]

        from src.infrastructure.db.base import get_session_factory
        from src.infrastructure.db.repositories.monitoring_repository import MonitoringRepository
        from src.infrastructure.db.repositories.provider_repository import ProviderRepository

        session = get_session_factory()()
        try:
            providers = ProviderRepository(session)
            providers.update_provider_config("llm-story", budget_threshold=50)
            providers.log_usage(
                provider_key="llm-story",
                provider_type="llm",
                project_id=project_id,
                job_run_id=None,
                metric_name="token",
                usage_amount=75,
                usage_unit="tokens",
            )
            MonitoringRepository(session).record_worker_heartbeat(
                worker_id="worker-metrics",
                worker_type="hybrid",
                status="idle",
                seen_at=datetime.now(timezone.utc),
            )
            session.commit()
        finally:
            session.close()

        metrics_response = self.client.get("/metrics")
        self.assertEqual(metrics_response.status_code, 200)
        self.assertIn("text/plain", metrics_response.headers["content-type"])
        body = metrics_response.text
        self.assertIn('ai_manga_factory_provider_consumed{provider_key="llm-story"', body)
        self.assertIn('ai_manga_factory_provider_budget_threshold{provider_key="llm-story"', body)
        self.assertIn('ai_manga_factory_provider_alert_active{provider_key="llm-story"', body)
        self.assertIn('ai_manga_factory_worker_up{worker_id="worker-metrics"', body)
        self.assertIn('ai_manga_factory_job_runs_total{status="completed"}', body)


if __name__ == "__main__":
    unittest.main()
