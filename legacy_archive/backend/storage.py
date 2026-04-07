import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from backend.config import DATA_DIR, DB_PATH
from backend.schemas import ArtifactPreview, JobResponse, ProjectResponse, UiPreferencesResponse, WorkflowStep


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class PlatformStore:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    capability_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    workflow_json TEXT NOT NULL,
                    artifacts_json TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id)
                );

                CREATE TABLE IF NOT EXISTS ui_preferences (
                    preference_key TEXT PRIMARY KEY,
                    preference_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(connection, "jobs", "error", "TEXT")

    def _ensure_column(
        self, connection: sqlite3.Connection, table: str, column: str, column_type: str
    ) -> None:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")

    def create_project(self, name: str, description: str | None = None) -> ProjectResponse:
        created_at = _utcnow()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO projects (name, description, created_at)
                VALUES (?, ?, ?)
                """,
                (name, description, created_at),
            )
            project_id = cursor.lastrowid

        return self.get_project(project_id)

    def get_project(self, project_id: int) -> ProjectResponse:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, name, description, created_at FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()

        if row is None:
            raise KeyError(f"Project {project_id} not found")

        return ProjectResponse(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def get_or_create_project(self, name: str) -> ProjectResponse:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, name, description, created_at FROM projects WHERE name = ?",
                (name,),
            ).fetchone()

        if row is not None:
            return ProjectResponse(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )

        return self.create_project(name=name)

    def list_projects(self) -> list[ProjectResponse]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, name, description, created_at FROM projects ORDER BY id DESC"
            ).fetchall()

        return [
            ProjectResponse(
                id=row["id"],
                name=row["name"],
                description=row["description"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def create_job(
        self,
        project_id: int,
        capability_id: str,
        status: str,
        input_payload: dict,
        workflow: list[WorkflowStep],
        artifacts: list[ArtifactPreview],
        summary: str,
    ) -> JobResponse:
        timestamp = _utcnow()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO jobs (
                    project_id, capability_id, status, input_json, workflow_json,
                    artifacts_json, summary, error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    capability_id,
                    status,
                    json.dumps(input_payload, ensure_ascii=False),
                    json.dumps([step.model_dump() for step in workflow], ensure_ascii=False),
                    json.dumps([artifact.model_dump() for artifact in artifacts], ensure_ascii=False),
                    summary,
                    None,
                    timestamp,
                    timestamp,
                ),
            )
            job_id = cursor.lastrowid

        return self.get_job(job_id)

    def list_jobs(self) -> list[JobResponse]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT jobs.*, projects.name AS project_name
                FROM jobs
                JOIN projects ON projects.id = jobs.project_id
                ORDER BY jobs.id DESC
                """
            ).fetchall()

        return [self._row_to_job(row) for row in rows]

    def get_job(self, job_id: int) -> JobResponse:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT jobs.*, projects.name AS project_name
                FROM jobs
                JOIN projects ON projects.id = jobs.project_id
                WHERE jobs.id = ?
                """,
                (job_id,),
            ).fetchone()

        if row is None:
            raise KeyError(f"Job {job_id} not found")

        return self._row_to_job(row)

    def update_job(
        self,
        job_id: int,
        status: str,
        workflow: list[WorkflowStep],
        artifacts: list[ArtifactPreview],
        summary: str,
        error: str | None,
    ) -> JobResponse:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, workflow_json = ?, artifacts_json = ?, summary = ?, error = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    json.dumps([step.model_dump() for step in workflow], ensure_ascii=False),
                    json.dumps([artifact.model_dump() for artifact in artifacts], ensure_ascii=False),
                    summary,
                    error,
                    _utcnow(),
                    job_id,
                ),
            )
        return self.get_job(job_id)

    def get_ui_preferences(self) -> UiPreferencesResponse:
        default = UiPreferencesResponse()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT preference_json, updated_at FROM ui_preferences WHERE preference_key = ?",
                ("dashboard_ui",),
            ).fetchone()
        if row is None:
            return default

        payload = json.loads(row["preference_json"])
        payload["updated_at"] = row["updated_at"]
        return UiPreferencesResponse(**payload)

    def update_ui_preferences(self, *, density_mode: str) -> UiPreferencesResponse:
        updated_at = _utcnow()
        payload = {"density_mode": density_mode}
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ui_preferences (preference_key, preference_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(preference_key) DO UPDATE SET
                    preference_json = excluded.preference_json,
                    updated_at = excluded.updated_at
                """,
                ("dashboard_ui", json.dumps(payload, ensure_ascii=False), updated_at),
            )
        return UiPreferencesResponse(density_mode=density_mode, updated_at=updated_at)

    def _row_to_job(self, row: sqlite3.Row) -> JobResponse:
        return JobResponse(
            id=row["id"],
            project_id=row["project_id"],
            project_name=row["project_name"] if "project_name" in row.keys() else None,
            capability_id=row["capability_id"],
            status=row["status"],
            input=json.loads(row["input_json"]),
            workflow=[WorkflowStep(**item) for item in json.loads(row["workflow_json"])],
            artifacts=[ArtifactPreview(**item) for item in json.loads(row["artifacts_json"])],
            summary=row["summary"],
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
