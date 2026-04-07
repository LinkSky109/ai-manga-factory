import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


class ProjectApiIntegrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "integration.db"
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

    def test_project_workflow_job_monitoring_and_feedback_flow(self) -> None:
        project_response = self.client.post(
            "/api/v1/projects",
            json={"name": "斗气项目", "description": "Phase 2 integration"},
        )
        self.assertEqual(project_response.status_code, 201)
        project_id = project_response.json()["id"]

        chapter_response = self.client.post(
            f"/api/v1/projects/{project_id}/chapters",
            json={"chapter_number": 1, "title": "第一章", "summary": "乌坦城起始"},
        )
        self.assertEqual(chapter_response.status_code, 201)
        chapter_id = chapter_response.json()["id"]

        character_response = self.client.post(
            "/api/v1/assets/characters",
            json={
                "project_id": project_id,
                "name": "萧炎",
                "appearance": "黑发少年，神情坚毅",
                "personality": "倔强、克制、成长型",
                "lora_path": "loras/xiao-yan.safetensors",
                "reference_images": [
                    {
                        "view_type": "front",
                        "asset_path": "references/xiao-yan-front.png",
                        "notes": "正脸标准照"
                    }
                ],
            },
        )
        self.assertEqual(character_response.status_code, 201)

        voice_response = self.client.post(
            "/api/v1/assets/voices",
            json={
                "project_id": project_id,
                "character_name": "萧炎",
                "voice_key": "voice-xiao-yan-01",
                "provider_key": "voice-clone-main",
                "tone_description": "少年感、克制、偏冷",
            },
        )
        self.assertEqual(voice_response.status_code, 201)

        workflow_response = self.client.post(
            "/api/v1/workflows",
            json={
                "project_id": project_id,
                "name": "章节标准流水线",
                "description": "分镜到成片",
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

        failed_job_response = self.client.post(
            "/api/v1/jobs",
            json={
                "project_id": project_id,
                "chapter_id": chapter_id,
                "workflow_id": workflow_id,
                "execution_mode": "sync",
                "input": {"simulate_failure_at_step": "video"},
            },
        )
        self.assertEqual(failed_job_response.status_code, 201)
        failed_job_id = failed_job_response.json()["id"]
        self.assertEqual(failed_job_response.json()["status"], "failed")

        resumed_job_response = self.client.post(
            f"/api/v1/jobs/{failed_job_id}/resume",
            json={"override_input": {}},
        )
        self.assertEqual(resumed_job_response.status_code, 200)
        self.assertEqual(resumed_job_response.json()["status"], "completed")

        overview_response = self.client.get(f"/api/v1/projects/{project_id}/overview")
        self.assertEqual(overview_response.status_code, 200)
        self.assertEqual(overview_response.json()["project_name"], "斗气项目")

        chapters_response = self.client.get(f"/api/v1/projects/{project_id}/chapters")
        self.assertEqual(chapters_response.status_code, 200)
        self.assertEqual(len(chapters_response.json()), 1)
        self.assertEqual(chapters_response.json()[0]["pipeline_states"][0]["stage_key"], "storyboard")

        characters_response = self.client.get(f"/api/v1/assets/characters?project_id={project_id}")
        self.assertEqual(characters_response.status_code, 200)
        self.assertEqual(len(characters_response.json()), 1)

        voices_response = self.client.get(f"/api/v1/assets/voices?project_id={project_id}")
        self.assertEqual(voices_response.status_code, 200)
        self.assertEqual(len(voices_response.json()), 1)

        workflows_response = self.client.get(f"/api/v1/workflows?project_id={project_id}")
        self.assertEqual(workflows_response.status_code, 200)
        self.assertEqual(len(workflows_response.json()), 1)

        jobs_response = self.client.get(f"/api/v1/projects/{project_id}/jobs")
        self.assertEqual(jobs_response.status_code, 200)
        self.assertEqual(len(jobs_response.json()), 1)
        self.assertEqual(jobs_response.json()[0]["status"], "completed")

        previews_response = self.client.get(f"/api/v1/projects/{project_id}/previews")
        self.assertEqual(previews_response.status_code, 200)
        self.assertGreaterEqual(len(previews_response.json()["items"]), 1)

        monitoring_response = self.client.get("/api/v1/monitoring/providers")
        self.assertEqual(monitoring_response.status_code, 200)
        self.assertGreaterEqual(len(monitoring_response.json()["items"]), 1)

        feedback_response = self.client.post(
            "/api/v1/prompt-evolution/feedback",
            json={
                "project_id": project_id,
                "job_id": failed_job_id,
                "workflow_key": "chapter-standard",
                "template_version": "v1",
                "template_body": "生成高一致性的分镜与视频提示词",
                "score": 4,
                "correction_summary": "补充角色统一服装和镜头连续性约束",
                "corrected_prompt": "生成高一致性的分镜与视频提示词，并固定角色服装与镜头连续性。",
            },
        )
        self.assertEqual(feedback_response.status_code, 201)

        prompt_templates_response = self.client.get(f"/api/v1/prompt-evolution/templates?project_id={project_id}")
        self.assertEqual(prompt_templates_response.status_code, 200)
        self.assertEqual(len(prompt_templates_response.json()), 1)
        self.assertEqual(prompt_templates_response.json()[0]["feedback_count"], 1)

        prompt_feedback_response = self.client.get(f"/api/v1/prompt-evolution/feedback?project_id={project_id}")
        self.assertEqual(prompt_feedback_response.status_code, 200)
        self.assertEqual(len(prompt_feedback_response.json()), 1)

        memory_create_response = self.client.post(
            "/api/v1/memories",
            json={
                "project_id": project_id,
                "scope_type": "project",
                "scope_key": "global-story-bible",
                "memory_type": "continuity_rule",
                "content": {
                    "rule": "萧炎在第一幕保持黑色主服装和银色纹样。",
                    "priority": "high",
                },
            },
        )
        self.assertEqual(memory_create_response.status_code, 201)

        memories_response = self.client.get(f"/api/v1/memories?project_id={project_id}")
        self.assertEqual(memories_response.status_code, 200)
        self.assertEqual(len(memories_response.json()), 1)

        review_create_response = self.client.post(
            "/api/v1/reviews",
            json={
                "project_id": project_id,
                "chapter_id": chapter_id,
                "review_stage": "script",
                "review_type": "multi-agent",
                "assigned_agents": ["logic-auditor", "continuity-keeper", "character-editor"],
                "checklist": ["剧情逻辑", "角色一致性", "世界观约束"],
                "findings_summary": "第二幕转场需要补足动机说明。",
                "result_payload": {
                    "severity": "medium",
                    "recommendation": "补充角色转场前的心理动机。"
                },
            },
        )
        self.assertEqual(review_create_response.status_code, 201)

        reviews_response = self.client.get(f"/api/v1/reviews?project_id={project_id}")
        self.assertEqual(reviews_response.status_code, 200)
        self.assertEqual(len(reviews_response.json()), 1)
        self.assertEqual(reviews_response.json()[0]["assigned_agents"][0], "logic-auditor")

        workflow_update_response = self.client.put(
            f"/api/v1/workflows/{workflow_id}",
            json={
                "name": "章节增强流水线",
                "description": "加入成品包装阶段",
                "routing_mode": "manual",
                "nodes": [
                    {"key": "storyboard", "title": "分镜", "provider_type": "llm"},
                    {"key": "video", "title": "视频", "provider_type": "video"},
                    {"key": "voice", "title": "配音", "provider_type": "voice"},
                    {"key": "finalize", "title": "成品包装", "provider_type": "finalize"},
                ],
                "edges": [
                    {"source": "storyboard", "target": "video"},
                    {"source": "video", "target": "voice"},
                    {"source": "voice", "target": "finalize"},
                ],
            },
        )
        self.assertEqual(workflow_update_response.status_code, 200)
        self.assertEqual(workflow_update_response.json()["routing_mode"], "manual")

    def test_project_initialization_generates_story_assets_and_chapter_drafts(self) -> None:
        project_response = self.client.post(
            "/api/v1/projects",
            json={"name": "原文初始化项目", "description": "Step 7 integration"},
        )
        self.assertEqual(project_response.status_code, 201)
        project_id = project_response.json()["id"]

        source_text = """
第1章 乌坦城风起
萧炎站在乌坦城议事堂中央，望向远处的药老。族人们在大堂里低声议论。

第2章 夜谈药老
夜色降临，萧炎来到后山石台，与药老对谈。月光落在山道和古树之间。
        """.strip()

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
        self.assertEqual(payload["project_id"], project_id)
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["source"]["source_title"], "斗气试制线")
        self.assertEqual(payload["summary"]["status"], "completed")
        self.assertEqual(payload["script"]["status"], "completed")
        self.assertEqual(payload["generation_trace"]["resolved_provider_key"], "llm-story")
        self.assertEqual(len(payload["chapters"]), 2)
        self.assertGreaterEqual(len(payload["character_drafts"]), 1)
        self.assertGreaterEqual(len(payload["scene_drafts"]), 1)

        initialization_response = self.client.get(f"/api/v1/projects/{project_id}/initialization")
        self.assertEqual(initialization_response.status_code, 200)
        self.assertEqual(initialization_response.json()["source"]["source_title"], "斗气试制线")
        self.assertEqual(len(initialization_response.json()["chapters"]), 2)

        chapters_response = self.client.get(f"/api/v1/projects/{project_id}/chapters")
        self.assertEqual(chapters_response.status_code, 200)
        self.assertEqual(len(chapters_response.json()), 2)

        characters_response = self.client.get(f"/api/v1/assets/characters?project_id={project_id}")
        self.assertEqual(characters_response.status_code, 200)
        self.assertGreaterEqual(len(characters_response.json()), 1)

        scenes_response = self.client.get(f"/api/v1/assets/scenes?project_id={project_id}")
        self.assertEqual(scenes_response.status_code, 200)
        self.assertGreaterEqual(len(scenes_response.json()), 1)

        overview_response = self.client.get(f"/api/v1/projects/{project_id}/overview")
        self.assertEqual(overview_response.status_code, 200)
        self.assertGreaterEqual(len(overview_response.json()["initialization_progress"]), 4)
        self.assertEqual(overview_response.json()["asset_health"][1]["label"], "场景资产")

    def test_multi_agent_review_auto_executes_and_syncs_memories_and_prompt_feedback(self) -> None:
        project_response = self.client.post(
            "/api/v1/projects",
            json={"name": "审核自动执行项目", "description": "Step 8 integration"},
        )
        self.assertEqual(project_response.status_code, 201)
        project_id = project_response.json()["id"]

        source_text = """
第1章 乌坦城风起
萧炎站在乌坦城议事堂中央，望向远处的药老。族人们在大堂里低声议论。

第2章 夜谈药老
夜色降临，萧炎来到后山石台，与药老对谈。月光落在山道和古树之间。
        """.strip()

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
        review_payload = review_response.json()
        self.assertEqual(review_payload["status"], "completed")
        self.assertEqual(review_payload["result_payload"]["execution_trace"]["resolved_provider_key"], "llm-story")
        self.assertIn(review_payload["result_payload"]["blocking_status"], {"pass", "warning", "blocked"})
        self.assertGreaterEqual(len(review_payload["result_payload"]["findings"]), 1)

        memories_response = self.client.get(f"/api/v1/memories?project_id={project_id}")
        self.assertEqual(memories_response.status_code, 200)
        self.assertGreaterEqual(len(memories_response.json()), 1)
        self.assertTrue(any("review:script" in item["scope_key"] for item in memories_response.json()))

        prompt_templates_response = self.client.get(f"/api/v1/prompt-evolution/templates?project_id={project_id}")
        self.assertEqual(prompt_templates_response.status_code, 200)
        self.assertGreaterEqual(len(prompt_templates_response.json()), 1)
        self.assertTrue(any(item["workflow_key"] == "script-review" for item in prompt_templates_response.json()))

        prompt_feedback_response = self.client.get(f"/api/v1/prompt-evolution/feedback?project_id={project_id}")
        self.assertEqual(prompt_feedback_response.status_code, 200)
        self.assertGreaterEqual(len(prompt_feedback_response.json()), 1)


if __name__ == "__main__":
    unittest.main()
