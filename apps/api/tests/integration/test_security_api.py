import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


class SecurityApiIntegrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "security.db"
        os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{self.database_path}"
        os.environ["ARTIFACT_ROOT"] = str(Path(self.temp_dir.name) / "artifacts")
        os.environ["ARCHIVE_ROOT"] = str(Path(self.temp_dir.name) / "archives")
        os.environ["PREVIEW_ROOT"] = str(Path(self.temp_dir.name) / "previews")
        os.environ["AUTH_BOOTSTRAP_ADMIN_TOKEN"] = "admin-test-token"
        os.environ["AUTH_BOOTSTRAP_VIEWER_TOKEN"] = "viewer-test-token"
        os.environ["AUTH_BOOTSTRAP_REVIEWER_TOKEN"] = "reviewer-test-token"

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
        for env_key in [
            "AUTH_BOOTSTRAP_ADMIN_TOKEN",
            "AUTH_BOOTSTRAP_VIEWER_TOKEN",
            "AUTH_BOOTSTRAP_REVIEWER_TOKEN",
            "AUTH_BOOTSTRAP_OPERATOR_TOKEN",
        ]:
            os.environ.pop(env_key, None)
        self.temp_dir.cleanup()

    def test_auth_requires_bearer_token_and_exposes_current_actor(self) -> None:
        unauthenticated = self.client.get("/api/v1/projects")
        self.assertEqual(unauthenticated.status_code, 401)

        me_response = self.client.get("/api/v1/auth/me", headers=self._auth_headers("admin-test-token"))
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["role"], "admin")

        viewer_projects = self.client.get("/api/v1/projects", headers=self._auth_headers("viewer-test-token"))
        self.assertEqual(viewer_projects.status_code, 200)
        self.assertEqual(viewer_projects.json(), [])

    def test_rbac_config_center_and_audit_logs(self) -> None:
        forbidden_create = self.client.post(
            "/api/v1/projects",
            json={"name": "viewer cannot create", "description": "forbidden"},
            headers=self._auth_headers("viewer-test-token"),
        )
        self.assertEqual(forbidden_create.status_code, 403)

        project_response = self.client.post(
            "/api/v1/projects",
            json={"name": "secure factory", "description": "admin create"},
            headers=self._auth_headers("admin-test-token"),
        )
        self.assertEqual(project_response.status_code, 201)
        project_id = project_response.json()["id"]

        review_response = self.client.post(
            "/api/v1/reviews",
            json={
                "project_id": project_id,
                "review_stage": "script",
                "review_type": "multi-agent",
                "assigned_agents": ["logic-auditor"],
                "checklist": ["剧情逻辑"],
                "auto_run": False,
            },
            headers=self._auth_headers("reviewer-test-token"),
        )
        self.assertEqual(review_response.status_code, 201)
        self.assertEqual(review_response.json()["status"], "pending")

        settings_response = self.client.get(
            "/api/v1/settings/overview",
            headers=self._auth_headers("admin-test-token"),
        )
        self.assertEqual(settings_response.status_code, 200)
        self.assertTrue(settings_response.json()["auth"]["enabled"])
        self.assertGreaterEqual(len(settings_response.json()["providers"]), 1)

        provider_update = self.client.patch(
            "/api/v1/settings/providers/llm-story",
            json={"priority": 220, "budget_threshold": 92, "routing_mode": "manual", "is_enabled": True},
            headers=self._auth_headers("admin-test-token"),
        )
        self.assertEqual(provider_update.status_code, 200)
        self.assertEqual(provider_update.json()["priority"], 220)
        self.assertEqual(provider_update.json()["routing_mode"], "manual")

        audit_logs = self.client.get(
            "/api/v1/audit-logs",
            headers=self._auth_headers("admin-test-token"),
        )
        self.assertEqual(audit_logs.status_code, 200)
        self.assertGreaterEqual(len(audit_logs.json()["items"]), 1)
        self.assertTrue(any(item["request_path"] == "/api/v1/settings/providers/llm-story" for item in audit_logs.json()["items"]))

    @staticmethod
    def _auth_headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}


if __name__ == "__main__":
    unittest.main()
