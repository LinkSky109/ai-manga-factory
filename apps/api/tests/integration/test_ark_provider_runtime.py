import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


class ArkProviderRuntimeIntegrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "integration-ark.db"
        os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{self.database_path}"
        os.environ["ARTIFACT_ROOT"] = str(Path(self.temp_dir.name) / "artifacts")
        os.environ["ARCHIVE_ROOT"] = str(Path(self.temp_dir.name) / "archives")
        os.environ["PREVIEW_ROOT"] = str(Path(self.temp_dir.name) / "previews")
        os.environ["OBJECT_STORAGE_ROOT"] = str(Path(self.temp_dir.name) / "object-storage")
        os.environ["OBJECT_STORAGE_BUCKET"] = "ark-tests"
        os.environ["ARK_API_KEY"] = "ark-test-key"

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
            "ARK_API_KEY",
            "ARK_BASE_URL",
            "ARK_TEXT_MODEL",
            "ARK_VIDEO_MODEL",
            "ARK_IMAGE_MODEL",
        ]:
            os.environ.pop(env_key, None)
        self.temp_dir.cleanup()

    def test_job_uses_ark_story_and_ark_video_when_runtime_succeeds(self) -> None:
        project_id, chapter_id, workflow_id = self._bootstrap_project(name="Ark 成功项目")

        with patch(
            "src.infrastructure.storage.artifact_storage.build_ark_runtime_client",
            return_value=_FakeArkRuntimeClient(),
        ):
            job_response = self.client.post(
                "/api/v1/jobs",
                json={
                    "project_id": project_id,
                    "chapter_id": chapter_id,
                    "workflow_id": workflow_id,
                    "execution_mode": "sync",
                    "input": {"story_context": "主角走入古殿，镜头逐步推进。"},
                },
            )

        self.assertEqual(job_response.status_code, 201)
        self.assertEqual(job_response.json()["status"], "completed")
        self.assertEqual(job_response.json()["steps"][0]["provider_key"], "ark-story")
        self.assertEqual(job_response.json()["steps"][1]["provider_key"], "ark-video")
        self.assertEqual(
            [attempt["provider_key"] for attempt in job_response.json()["steps"][0]["output_snapshot"]["provider_attempts"]],
            ["ark-story"],
        )
        self.assertEqual(
            [attempt["provider_key"] for attempt in job_response.json()["steps"][1]["output_snapshot"]["provider_attempts"]],
            ["ark-video"],
        )

        previews_response = self.client.get(f"/api/v1/projects/{project_id}/previews")
        self.assertEqual(previews_response.status_code, 200)
        video_item = next(item for item in previews_response.json()["items"] if item["stage_key"] == "video")
        self.assertEqual(video_item["mime_type"], "video/mp4")

        preview_response = self.client.get(video_item["playback_url"])
        self.assertEqual(preview_response.status_code, 200)
        self.assertTrue(preview_response.headers["content-type"].startswith("video/mp4"))

    def test_job_falls_back_to_legacy_suppliers_when_ark_runtime_fails(self) -> None:
        project_id, chapter_id, workflow_id = self._bootstrap_project(name="Ark 回退项目")

        with patch(
            "src.infrastructure.storage.artifact_storage.build_ark_runtime_client",
            return_value=_FailingArkRuntimeClient(),
        ):
            job_response = self.client.post(
                "/api/v1/jobs",
                json={
                    "project_id": project_id,
                    "chapter_id": chapter_id,
                    "workflow_id": workflow_id,
                    "execution_mode": "sync",
                    "input": {"story_context": "主角走入古殿，镜头逐步推进。"},
                },
            )

        self.assertEqual(job_response.status_code, 201)
        self.assertEqual(job_response.json()["status"], "completed")
        self.assertEqual(job_response.json()["steps"][0]["provider_key"], "llm-story")
        self.assertEqual(job_response.json()["steps"][1]["provider_key"], "vidu-primary")
        self.assertEqual(
            [attempt["provider_key"] for attempt in job_response.json()["steps"][0]["output_snapshot"]["provider_attempts"]],
            ["ark-story", "llm-story"],
        )
        self.assertEqual(
            [attempt["status"] for attempt in job_response.json()["steps"][0]["output_snapshot"]["provider_attempts"]],
            ["failed", "completed"],
        )
        self.assertEqual(
            [attempt["provider_key"] for attempt in job_response.json()["steps"][1]["output_snapshot"]["provider_attempts"]],
            ["ark-video", "vidu-primary"],
        )

        previews_response = self.client.get(f"/api/v1/projects/{project_id}/previews")
        self.assertEqual(previews_response.status_code, 200)
        video_item = next(item for item in previews_response.json()["items"] if item["stage_key"] == "video")
        self.assertEqual(video_item["mime_type"], "text/html; charset=utf-8")

    def test_image_step_uses_ark_image_and_generates_png_preview(self) -> None:
        project_id, chapter_id, workflow_id = self._bootstrap_image_project(name="Ark 图片项目")

        with patch(
            "src.infrastructure.storage.artifact_storage.build_ark_runtime_client",
            return_value=_FakeArkRuntimeClient(),
        ):
            job_response = self.client.post(
                "/api/v1/jobs",
                json={
                    "project_id": project_id,
                    "chapter_id": chapter_id,
                    "workflow_id": workflow_id,
                    "execution_mode": "sync",
                    "input": {"prompt": "古风少年站在大殿中央，金色火光映照。"},
                },
            )

        self.assertEqual(job_response.status_code, 201)
        self.assertEqual(job_response.json()["status"], "completed")
        self.assertEqual(job_response.json()["steps"][0]["provider_key"], "ark-image")
        self.assertEqual(
            [attempt["provider_key"] for attempt in job_response.json()["steps"][0]["output_snapshot"]["provider_attempts"]],
            ["ark-image"],
        )

        previews_response = self.client.get(f"/api/v1/projects/{project_id}/previews")
        self.assertEqual(previews_response.status_code, 200)
        image_item = next(item for item in previews_response.json()["items"] if item["stage_key"] == "cover-image")
        self.assertEqual(image_item["mime_type"], "image/png")

        preview_response = self.client.get(image_item["playback_url"])
        self.assertEqual(preview_response.status_code, 200)
        self.assertTrue(preview_response.headers["content-type"].startswith("image/png"))

    def test_project_initialization_uses_ark_story_and_returns_model_payload(self) -> None:
        project_id = self._bootstrap_initialization_project(name="Ark 初始化项目")
        source_text = """
第1章 乌坦城风起
萧炎站在乌坦城议事堂中央，望向远处的药老。

第2章 夜谈药老
夜色降临，萧炎来到后山石台，与药老对谈。
        """.strip()

        with patch(
            "src.application.orchestrators.project_initializer.build_ark_runtime_client",
            return_value=_ProjectInitializationArkRuntimeClient(),
        ):
            initialize_response = self.client.post(
                f"/api/v1/projects/{project_id}/initialize",
                json={
                    "source_title": "斗气试制线",
                    "source_type": "novel_text",
                    "source_text": source_text,
                    "overwrite_assets": True,
                },
            )

        self.assertEqual(initialize_response.status_code, 201)
        payload = initialize_response.json()
        self.assertEqual(payload["summary"]["summary_body"], "项目主线聚焦萧炎在乌坦城失势后的第一次反击，并由药老介入建立成长引擎。")
        self.assertEqual(payload["script"]["title"], "斗气试制线 模型剧本初稿")
        self.assertEqual(payload["chapters"][0]["summary"], "乌坦城议事堂内建立压迫关系与主角处境。")
        self.assertEqual(payload["character_drafts"][0]["name"], "萧炎")
        self.assertEqual(payload["scene_drafts"][0]["name"], "乌坦城议事堂")
        self.assertEqual(payload["generation_trace"]["resolved_provider_key"], "ark-story")
        self.assertEqual(
            [attempt["provider_key"] for attempt in payload["generation_trace"]["provider_attempts"]],
            ["ark-story"],
        )

    def test_project_initialization_falls_back_to_llm_story_when_ark_story_fails(self) -> None:
        project_id = self._bootstrap_initialization_project(name="Ark 初始化回退项目")
        source_text = """
第1章 乌坦城风起
萧炎站在乌坦城议事堂中央，望向远处的药老。

第2章 夜谈药老
夜色降临，萧炎来到后山石台，与药老对谈。
        """.strip()

        with patch(
            "src.application.orchestrators.project_initializer.build_ark_runtime_client",
            return_value=_FailingArkRuntimeClient(),
        ):
            initialize_response = self.client.post(
                f"/api/v1/projects/{project_id}/initialize",
                json={
                    "source_title": "斗气试制线",
                    "source_type": "novel_text",
                    "source_text": source_text,
                    "overwrite_assets": True,
                },
            )

        self.assertEqual(initialize_response.status_code, 201)
        payload = initialize_response.json()
        self.assertEqual(payload["generation_trace"]["resolved_provider_key"], "llm-story")
        self.assertEqual(
            [attempt["provider_key"] for attempt in payload["generation_trace"]["provider_attempts"]],
            ["ark-story", "llm-story"],
        )
        self.assertEqual(
            [attempt["status"] for attempt in payload["generation_trace"]["provider_attempts"]],
            ["failed", "completed"],
        )
        self.assertIn("第1章 乌坦城风起", payload["summary"]["summary_body"])
        self.assertGreaterEqual(len(payload["character_drafts"]), 1)
        self.assertGreaterEqual(len(payload["scene_drafts"]), 1)

    def test_multi_agent_review_uses_ark_story_when_runtime_succeeds(self) -> None:
        project_id = self._bootstrap_initialization_project(name="Ark 审核项目")
        source_text = """
第1章 乌坦城风起
萧炎站在乌坦城议事堂中央，望向远处的药老。
        """.strip()

        with patch(
            "src.application.orchestrators.project_initializer.build_ark_runtime_client",
            return_value=_ProjectInitializationArkRuntimeClient(),
        ):
            initialize_response = self.client.post(
                f"/api/v1/projects/{project_id}/initialize",
                json={
                    "source_title": "斗气试制线",
                    "source_type": "novel_text",
                    "source_text": source_text,
                    "overwrite_assets": True,
                },
            )
        self.assertEqual(initialize_response.status_code, 201)
        chapter_id = initialize_response.json()["chapters"][0]["id"]

        with patch(
            "src.application.services.review_service.build_ark_runtime_client",
            return_value=_ReviewArkRuntimeClient(),
        ):
            review_response = self.client.post(
                "/api/v1/reviews",
                json={
                    "project_id": project_id,
                    "chapter_id": chapter_id,
                    "review_stage": "script",
                    "review_type": "multi-agent",
                    "assigned_agents": ["logic-auditor", "continuity-keeper", "character-editor"],
                    "checklist": ["剧情逻辑", "角色一致性", "世界观约束"],
                },
            )

        self.assertEqual(review_response.status_code, 201)
        payload = review_response.json()
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["result_payload"]["execution_trace"]["resolved_provider_key"], "ark-story")
        self.assertEqual(payload["result_payload"]["blocking_status"], "warning")
        self.assertEqual(payload["result_payload"]["findings"][0]["agent"], "logic-auditor")

    def _bootstrap_project(self, name: str) -> tuple[int, int, int]:
        project_response = self.client.post(
            "/api/v1/projects",
            json={"name": name, "description": "Ark integration"},
        )
        self.assertEqual(project_response.status_code, 201)
        project_id = project_response.json()["id"]

        chapter_response = self.client.post(
            f"/api/v1/projects/{project_id}/chapters",
            json={"chapter_number": 1, "title": "第一章", "summary": "Ark provider 验证"},
        )
        self.assertEqual(chapter_response.status_code, 201)
        chapter_id = chapter_response.json()["id"]

        workflow_response = self.client.post(
            "/api/v1/workflows",
            json={
                "project_id": project_id,
                "name": "Ark 流水线",
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

    def _bootstrap_image_project(self, name: str) -> tuple[int, int, int]:
        project_response = self.client.post(
            "/api/v1/projects",
            json={"name": name, "description": "Ark image integration"},
        )
        self.assertEqual(project_response.status_code, 201)
        project_id = project_response.json()["id"]

        chapter_response = self.client.post(
            f"/api/v1/projects/{project_id}/chapters",
            json={"chapter_number": 1, "title": "第一章", "summary": "Ark 图片验证"},
        )
        self.assertEqual(chapter_response.status_code, 201)
        chapter_id = chapter_response.json()["id"]

        workflow_response = self.client.post(
            "/api/v1/workflows",
            json={
                "project_id": project_id,
                "name": "Ark 图片流水线",
                "description": "封面图生成",
                "routing_mode": "smart",
                "nodes": [
                    {"key": "cover-image", "title": "封面图", "provider_type": "image"},
                ],
                "edges": [],
            },
        )
        self.assertEqual(workflow_response.status_code, 201)
        workflow_id = workflow_response.json()["id"]
        return project_id, chapter_id, workflow_id

    def _bootstrap_initialization_project(self, name: str) -> int:
        project_response = self.client.post(
            "/api/v1/projects",
            json={"name": name, "description": "Ark project initialization integration"},
        )
        self.assertEqual(project_response.status_code, 201)
        return project_response.json()["id"]


class _FakeArkRuntimeClient:
    def generate_text(self, *, prompt: str, system_prompt: str | None = None, model: str | None = None, temperature: float = 0.2, max_tokens: int = 2000) -> str:
        return "镜头一：主角走入古殿。镜头二：火光摇曳。"

    def generate_video_to_file(self, *, prompt: str, output_path: Path, model: str | None = None, options=None) -> Path:
        output_path.write_bytes(b"fake-mp4-payload")
        return output_path

    def generate_image_to_file(self, *, prompt: str, output_path: Path, model: str | None = None) -> Path:
        output_path.write_bytes(_png_bytes())
        return output_path


class _FailingArkRuntimeClient:
    def generate_text(self, *, prompt: str, system_prompt: str | None = None, model: str | None = None, temperature: float = 0.2, max_tokens: int = 2000) -> str:
        raise RuntimeError("Ark text quota exhausted")

    def generate_video_to_file(self, *, prompt: str, output_path: Path, model: str | None = None, options=None) -> Path:
        raise RuntimeError("Ark video quota exhausted")

    def generate_image_to_file(self, *, prompt: str, output_path: Path, model: str | None = None) -> Path:
        raise RuntimeError("Ark image quota exhausted")


class _ProjectInitializationArkRuntimeClient:
    def generate_text(self, *, prompt: str, system_prompt: str | None = None, model: str | None = None, temperature: float = 0.2, max_tokens: int = 2000) -> str:
        return """
{
  "summary_body": "项目主线聚焦萧炎在乌坦城失势后的第一次反击，并由药老介入建立成长引擎。",
  "highlights": [
    "第1章：乌坦城议事堂内建立压迫关系与主角处境。",
    "第2章：后山石台夜谈，药老正式推动成长线。"
  ],
  "chapters": [
    {
      "chapter_number": 1,
      "title": "第1章 乌坦城风起",
      "summary": "乌坦城议事堂内建立压迫关系与主角处境。"
    },
    {
      "chapter_number": 2,
      "title": "第2章 夜谈药老",
      "summary": "后山石台夜谈，药老正式推动成长线。"
    }
  ],
  "script_title": "斗气试制线 模型剧本初稿",
  "script_body": "# 斗气试制线 模型剧本初稿\\n\\n## 第1章 乌坦城风起\\n- 剧情目标：压缩家族羞辱与主角失势。\\n- 镜头策略：从议事堂全景推进到萧炎特写。\\n\\n## 第2章 夜谈药老\\n- 剧情目标：确立师徒关系与新规则。\\n- 镜头策略：月光逆光包裹石台对谈。",
  "characters": [
    {
      "name": "萧炎",
      "appearance": "黑发少年，衣着克制，眼神压着不服输的劲。",
      "personality": "倔强、克制、爆发前始终压着锋芒。 "
    },
    {
      "name": "药老",
      "appearance": "白发灵体长袍，轮廓半透明，气场沉稳。",
      "personality": "老练、带压场感、擅长用一句话改变局面。"
    }
  ],
  "scenes": [
    {
      "name": "乌坦城议事堂",
      "baseline_prompt": "乌坦城议事堂，石柱高耸，暖金火光压着家族会议气氛，镜头强调压迫与审视。",
      "continuity_guardrails": "保持主门朝向、议事桌中心轴线和人物站位一致。"
    },
    {
      "name": "后山石台",
      "baseline_prompt": "后山石台，夜色偏蓝，月光切出人物轮廓，空间安静克制。",
      "continuity_guardrails": "保持石台高度、树影方向和月光来源一致。"
    }
  ]
}
        """.strip()


class _ReviewArkRuntimeClient:
    def generate_text(self, *, prompt: str, system_prompt: str | None = None, model: str | None = None, temperature: float = 0.2, max_tokens: int = 2000) -> str:
        return """
{
  "blocking_status": "warning",
  "severity": "medium",
  "summary": "角色动机承接基本清楚，但转场提示还可以更具体。",
  "findings": [
    {
      "agent": "logic-auditor",
      "title": "转场动机可再压实",
      "severity": "medium",
      "summary": "夜谈切入前，主角的即时触发原因还可以更明确。",
      "recommendation": "在进入后山石台前补一条心理驱动或外部刺激。"
    }
  ],
  "memory_candidates": [
    {
      "scope_type": "chapter",
      "scope_key": "review:script:chapter:1:logic-auditor",
      "memory_type": "review_guideline",
      "content": {
        "rule": "涉及夜谈转场时，必须补足主角即时动机。",
        "owner": "logic-auditor"
      }
    }
  ],
  "prompt_feedback": {
    "template_body": "生成章节剧本时，要明确转场前的动机、连续性与角色目标。",
    "score": 4,
    "correction_summary": "补强转场动机提示。",
    "corrected_prompt": "生成章节剧本时，要明确转场前的动机、连续性与角色目标，并补足触发原因。"
  }
}
        """.strip()


def _png_bytes() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
        b"\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00"
        b"\xc9\xfe\x92\xef"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


if __name__ == "__main__":
    unittest.main()
