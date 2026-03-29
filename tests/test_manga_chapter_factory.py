from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.schemas import WorkflowStep
from modules.base import ExecutionContext, PlannedJob
from modules.manga import chapter_factory


class ChapterFactoryFailureAggregationTests(unittest.TestCase):
    def test_failed_qa_still_writes_job_level_artifacts_before_raising(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifacts_dir = Path(tmp_dir)
            job_dir = artifacts_dir / "job_999"
            context = ExecutionContext(job_id=999, project_id=24, job_dir=job_dir)
            plan = PlannedJob(
                workflow=[
                    WorkflowStep(key="research", title="research", description=""),
                    WorkflowStep(key="story_breakdown", title="story_breakdown", description=""),
                    WorkflowStep(key="storyboard_design", title="storyboard_design", description=""),
                    WorkflowStep(key="chapter_packaging", title="chapter_packaging", description=""),
                    WorkflowStep(key="qa_loop", title="qa_loop", description=""),
                ],
                artifacts=[],
                summary="test plan",
            )
            payload = {
                "source_title": "测试漫画",
                "chapter_range": "1-1",
                "episode_count": 1,
                "visual_style": "test style",
                "chapter_briefs": [
                    {
                        "chapter": 1,
                        "title": "第一章",
                        "summary": "summary",
                        "key_scene": "scene",
                        "emotion": "紧张",
                    }
                ],
                "adaptation_pack": "",
            }

            with mock.patch.object(chapter_factory, "ARTIFACTS_DIR", artifacts_dir):
                with mock.patch.object(chapter_factory, "ROOT_DIR", artifacts_dir):
                    with mock.patch.object(chapter_factory.ArkProvider, "from_local_secrets", return_value=None):
                        with mock.patch.object(chapter_factory, "load_storyboard_profile", return_value={"required_fields": []}):
                            runner = chapter_factory.ChapterFactoryRunner(
                                payload=payload,
                                context=context,
                                plan=plan,
                                normalize_chapter_briefs=lambda **kwargs: payload["chapter_briefs"],
                                build_prompts=lambda **kwargs: {"lead_character": "lead", "storyboard_prompts": []},
                                format_research_brief=lambda item: f"- {item['title']}",
                                write_placeholder_image=lambda path, *_args, **_kwargs: path.write_bytes(b"img"),
                                load_font=lambda *_args, **_kwargs: None,
                            )

                            def write_lead_character(_prompt: str, path: Path) -> None:
                                path.parent.mkdir(parents=True, exist_ok=True)
                                path.write_bytes(b"lead")

                            def write_top_level_docs(research_path: Path, screenplay_path: Path, art_path: Path) -> None:
                                research_path.write_text("research", encoding="utf-8")
                                screenplay_path.write_text("screenplay", encoding="utf-8")
                                art_path.write_text("art", encoding="utf-8")

                            def build_chapter_package(*, chapters_dir: Path, brief: dict[str, object]) -> dict[str, object]:
                                chapter_dir = chapters_dir / "chapter_01"
                                storyboard_dir = chapter_dir / "storyboard"
                                preview_dir = chapter_dir / "preview"
                                delivery_dir = chapter_dir / "delivery"
                                images_dir = chapter_dir / "images"
                                qa_dir = chapter_dir / "qa"
                                audio_dir = chapter_dir / "audio"
                                video_dir = chapter_dir / "video"
                                for path in (storyboard_dir, preview_dir, delivery_dir, images_dir, qa_dir, audio_dir, video_dir):
                                    path.mkdir(parents=True, exist_ok=True)
                                (storyboard_dir / "storyboard.json").write_text('{"rows":[]}', encoding="utf-8")
                                (preview_dir / "index.html").write_text("<html></html>", encoding="utf-8")
                                (preview_dir / "chapter_preview.mp4").write_bytes(b"preview")
                                (delivery_dir / "chapter_final_cut.mp4").write_bytes(b"delivery")
                                (images_dir / "keyframe_01.png").write_bytes(b"frame")
                                (qa_dir / "qa_report.md").write_text("qa", encoding="utf-8")
                                (qa_dir / "qa_snapshot.json").write_text("{}", encoding="utf-8")
                                (audio_dir / "audio_plan.json").write_text("{}", encoding="utf-8")
                                (audio_dir / "narration_script.txt").write_text("", encoding="utf-8")
                                (audio_dir / "voice_script.txt").write_text("", encoding="utf-8")
                                (audio_dir / "voiceover.mp3").write_bytes(b"voice")
                                (audio_dir / "ambience.wav").write_bytes(b"ambience")
                                (video_dir / "video_plan.json").write_text("{}", encoding="utf-8")
                                return {
                                    "chapter": 1,
                                    "title": str(brief["title"]),
                                    "storyboard": {"chapter": 1, "title": str(brief["title"])},
                                    "audio_plan": {},
                                    "artifact_paths": [
                                        "chapters/chapter_01/storyboard/storyboard.json",
                                        "chapters/chapter_01/preview/chapter_preview.mp4",
                                        "chapters/chapter_01/delivery/chapter_final_cut.mp4",
                                    ],
                                    "preview_video": str(preview_dir / "chapter_preview.mp4"),
                                    "delivery_video": str(delivery_dir / "chapter_final_cut.mp4"),
                                    "video_plan": {},
                                    "image_prompts": ["shot prompt"],
                                    "qa": {"passed": False, "summary": "未通过，需要返工"},
                                }

                            def concat_videos(_video_paths: list[Path], output_path: Path) -> None:
                                output_path.parent.mkdir(parents=True, exist_ok=True)
                                output_path.write_bytes(b"video")

                            runner._write_lead_character = write_lead_character
                            runner._write_top_level_docs = write_top_level_docs
                            runner._build_chapter_package = build_chapter_package
                            runner._concat_videos = concat_videos
                            runner._build_preview_html = lambda: "<html>preview</html>"
                            runner._collect_aggregate_scene_images = lambda limit: [job_dir / "chapters" / "chapter_01" / "images" / "keyframe_01.png"]

                            with self.assertRaisesRegex(RuntimeError, "QA 未通过"):
                                runner.run()

            self.assertTrue((job_dir / "prompts.json").exists())
            self.assertTrue((job_dir / "manifest.json").exists())
            self.assertTrue((job_dir / "chapters_index.json").exists())
            self.assertTrue((job_dir / "qa_overview.md").exists())
            self.assertTrue((job_dir / "storyboard" / "storyboard.json").exists())
            self.assertTrue((job_dir / "preview" / "index.html").exists())
            self.assertTrue((job_dir / "preview" / "preview.mp4").exists())
            self.assertTrue((job_dir / "delivery" / "final_cut.mp4").exists())

    def test_review_plan_does_not_false_positive_voice_script_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            artifacts_dir = Path(tmp_dir)
            job_dir = artifacts_dir / "job_1000"
            context = ExecutionContext(job_id=1000, project_id=24, job_dir=job_dir)
            plan = PlannedJob(
                workflow=[WorkflowStep(key="qa_loop", title="qa_loop", description="")],
                artifacts=[],
                summary="test plan",
            )
            payload = {
                "source_title": "测试漫画",
                "chapter_range": "1-1",
                "episode_count": 1,
                "target_duration_seconds": 60,
                "visual_style": "test style",
                "chapter_briefs": [{"chapter": 1, "title": "第一章", "summary": "summary", "key_scene": "scene", "emotion": "紧张"}],
                "adaptation_pack": "",
            }

            with mock.patch.object(chapter_factory, "ARTIFACTS_DIR", artifacts_dir):
                with mock.patch.object(chapter_factory, "ROOT_DIR", artifacts_dir):
                    with mock.patch.object(chapter_factory.ArkProvider, "from_local_secrets", return_value=None):
                        with mock.patch.object(chapter_factory, "load_storyboard_profile", return_value={"required_fields": [], "target_duration_seconds": 60}):
                            runner = chapter_factory.ChapterFactoryRunner(
                                payload=payload,
                                context=context,
                                plan=plan,
                                normalize_chapter_briefs=lambda **kwargs: payload["chapter_briefs"],
                                build_prompts=lambda **kwargs: {"lead_character": "lead", "storyboard_prompts": []},
                                format_research_brief=lambda item: f"- {item['title']}",
                                write_placeholder_image=lambda path, *_args, **_kwargs: path.write_bytes(b"img"),
                                load_font=lambda *_args, **_kwargs: None,
                            )

            rows = [
                {
                    "镜头号": index,
                    "时长(s)": 6.0,
                    "场景/时间": f"病房场景{index}",
                    "画面内容": f"独特画面内容{index}",
                    "人物动作/神态": f"动作{index}",
                    "旁白": f"旁白内容{index}",
                    "对白角色": "主角",
                    "对白": f"对白内容{index}",
                    "节奏目的": "推进",
                    "音频设计": f"音频设计{index}",
                    "音乐": "紧张",
                }
                for index in range(1, 11)
            ]
            audio_plan = {
                "voice_style": "zh-CN-YunxiNeural",
                "cue_sheet": [{"shot": index, "cue": f"cue-{index}"} for index in range(1, 11)],
                "narration_tracks": [{"shot": index, "text": f"旁白内容{index}"} for index in range(1, 11)],
                "dialogue_tracks": [{"shot": index, "speaker": "主角", "text": f"对白内容{index}"} for index in range(1, 11)],
                "voice_script": "旁白：测试旁白\n主角：测试对白",
            }

            review = runner._review_plan(payload["chapter_briefs"][0], rows, audio_plan)

            self.assertNotIn("voice_script 缺少旁白台本", review["blockers"])
            self.assertNotIn("voice_script 缺少角色对白台本", review["blockers"])

    def test_diversify_storyboard_rows_rewrites_canonical_fields_for_duplicates(self) -> None:
        runner = chapter_factory.ChapterFactoryRunner.__new__(chapter_factory.ChapterFactoryRunner)
        brief = {
            "chapter": 1,
            "title": "病房异兆",
            "summary": "主角在病房与诡异幻象之间反复切换，初次感知两个世界的裂缝。",
            "key_scene": "病房灯光闪烁时，墙面短暂显出古旧符纹。",
            "emotion": "迷惘",
            "world_rule": "",
            "memorable_line": "这件事，还没结束。",
        }
        rows = [
            {
                "镜头号": 1,
                "时长(s)": 6.1,
                "场景/时间": "高潮 / 病房",
                "镜头景别": "近景",
                "镜头运动": "插入",
                "画面内容": "病房灯光闪烁时",
                "人物动作/神态": "迷惘；情绪兑现，动作和表情顶到峰值",
                "旁白": "病房灯光闪烁时，危险先于答案降临。",
                "对白角色": "主角",
                "对白": "—",
                "台词对白": "—",
                "节奏目的": "高潮",
            },
            {
                "镜头号": 2,
                "时长(s)": 6.1,
                "场景/时间": "高潮 / 病房",
                "镜头景别": "近景",
                "镜头运动": "插入",
                "画面内容": "病房灯光闪烁时",
                "人物动作/神态": "迷惘；情绪兑现，动作和表情顶到峰值",
                "旁白": "病房灯光闪烁时，危险先于答案降临。",
                "对白角色": "对手",
                "对白": "—",
                "台词对白": "—",
                "节奏目的": "高潮",
            },
        ]

        runner._diversify_storyboard_rows(brief, rows)

        self.assertNotEqual(
            runner._normalize_storyboard_text_key(rows[0]["画面内容"]),
            runner._normalize_storyboard_text_key(rows[1]["画面内容"]),
        )
        self.assertNotEqual(rows[0]["人物动作/神态"], rows[1]["人物动作/神态"])
        self.assertNotEqual(rows[0]["镜头运动"], rows[1]["镜头运动"])
        self.assertNotEqual(rows[0]["镜头景别"], rows[1]["镜头景别"])
        self.assertEqual("这件事，还没结束。", rows[1]["对白"])
        self.assertEqual("这件事，还没结束。", rows[1]["台词对白"])
        self.assertNotIn("鐢婚潰鍐呭", rows[1])
        self.assertNotIn("闀滃ご杩愬姩", rows[1])
        self.assertNotIn("闀滃ご鏅埆", rows[1])

    def test_duplicate_variation_dialogue_stays_in_story_world_and_meta_lines_blocked(self) -> None:
        runner = chapter_factory.ChapterFactoryRunner.__new__(chapter_factory.ChapterFactoryRunner)
        runner.qa_threshold = {"fidelity": 7.0, "pacing": 7.0, "production": 7.0, "adaptation": 7.0, "overall": 7.5}
        runner.storyboard_profile = {"target_duration_seconds": 60}
        runner.target_duration_seconds = 60
        brief = {
            "chapter": 1,
            "title": "病房异兆",
            "summary": "主角在病房与诡异幻象之间反复切换，初次感知两个世界的裂缝。",
            "key_scene": "病房灯光闪烁时，墙面短暂显出古旧符纹。",
            "emotion": "迷惘",
            "world_rule": "",
            "memorable_line": "这件事，还没结束。",
        }
        rows = [
            {
                "镜头号": 1,
                "时长(s)": 6.0,
                "场景/时间": "开场钩子 / 病房",
                "镜头景别": "中近景",
                "镜头运动": "缓推",
                "画面内容": "病房灯光闪烁时，墙面短暂显出古旧符纹，环境建场",
                "人物动作/神态": "迷惘；先压后提，留出人物登场前的期待",
                "旁白": "病房灯光闪烁时，危险先于答案降临。",
                "对白角色": "主角",
                "对白": "有人在看着我们。",
                "台词对白": "有人在看着我们。",
                "节奏目的": "开场钩子",
            },
            {
                "镜头号": 2,
                "时长(s)": 6.0,
                "场景/时间": "开场钩子 / 病房",
                "镜头景别": "中近景",
                "镜头运动": "缓推",
                "画面内容": "病房灯光闪烁时，墙面短暂显出古旧符纹，环境建场",
                "人物动作/神态": "迷惘；先压后提，留出人物登场前的期待",
                "旁白": "病房灯光闪烁时，危险先于答案降临。",
                "对白角色": "旁白",
                "对白": "—",
                "台词对白": "—",
                "节奏目的": "开场钩子",
            },
        ]

        runner._diversify_storyboard_rows(brief, rows)

        self.assertNotIn("别停在同一个反应上", rows[1]["对白"])
        self.assertNotIn("往前推", rows[1]["对白"])
        self.assertNotIn("复述", rows[1]["对白"])

        audio_plan = {
            "voice_style": "zh-CN-YunxiNeural",
            "cue_sheet": [{"shot": 1, "cue": "cue-1"}, {"shot": 2, "cue": "cue-2"}],
            "narration_tracks": [{"shot": 1, "text": rows[0]["旁白"]}, {"shot": 2, "text": rows[1]["旁白"]}],
            "dialogue_tracks": [
                {"shot": 1, "speaker": rows[0]["对白角色"], "text": rows[0]["对白"]},
                {"shot": 2, "speaker": rows[1]["对白角色"], "text": "别停在同一个反应上，继续往前推。"},
            ],
            "voice_script": "旁白：病房灯光闪烁时，危险先于答案降临。\n主角：有人在看着我们。\n旁白：别停在同一个反应上，继续往前推。",
        }

        review = runner._review_plan(brief, rows, audio_plan)

        self.assertIn("对白或旁白混入制作指令，破坏成片沉浸感", review["blockers"])


if __name__ == "__main__":
    unittest.main()
