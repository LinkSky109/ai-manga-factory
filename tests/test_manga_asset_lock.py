from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend.schemas import WorkflowStep
from modules.base import ExecutionContext, PlannedJob
from modules.manga import chapter_factory
from modules.manga.service import MangaCapability


def build_asset_lock_payload(*, include_invalid_reference: bool = False) -> dict:
    return {
        "exists": True,
        "pack_root": "E:/work/project-manager/workhome/projects/ai-manga-factory/adaptations/demo_pack",
        "source_path": "E:/work/project-manager/workhome/projects/ai-manga-factory/adaptations/demo_pack/asset_lock.json",
        "scene": {
            "baseline_prompt": "冷色地下宫殿宿舍，青焰火盆与潮湿石墙保持统一。",
            "reference_image_path": None,
        },
        "characters": [
            {
                "name": "萧炎",
                "aliases": ["小炎子", "萧炎哥哥"],
                "fixed_prompt": "黑色短发，深色练功短衫，左手古朴戒指，少年感明显。",
                "voice_id": "voice.lead",
                "reference_image_path": None,
                "lora_path": None,
                "notes": "",
            },
            {
                "name": "药老",
                "aliases": ["老师", "药尘"],
                "fixed_prompt": "半透明苍老灵魂体，白发长须，灰白长袍，悬浮感。",
                "voice_id": "voice.support",
                "reference_image_path": None,
                "lora_path": None,
                "notes": "",
            },
            {
                "name": "萧薰儿",
                "aliases": ["薰儿", "萧炎哥哥"],
                "fixed_prompt": "黑色长发少女，紫色衣裙，神态安静克制。",
                "voice_id": "voice.support.female",
                "reference_image_path": None,
                "lora_path": None,
                "notes": "",
            },
            {
                "name": "萧战",
                "aliases": ["族长", "父亲"],
                "fixed_prompt": "中年族长，深色长袍，压迫感克制。",
                "voice_id": "voice.support.male",
                "reference_image_path": None,
                "lora_path": None,
                "notes": "",
            },
            {
                "name": "旁白",
                "aliases": ["解说"],
                "fixed_prompt": "冷静克制的叙事旁白。",
                "voice_id": "voice.narrator",
                "reference_image_path": None,
                "lora_path": None,
                "notes": "",
            },
        ],
        "validation_errors": ["资产锁引用路径无效：assets/characters/missing.png"] if include_invalid_reference else [],
    }


def make_brief() -> dict[str, object]:
    return {
        "chapter": 1,
        "title": "第1章",
        "summary": "萧炎在旧殿里第一次察觉异火的异常波动。",
        "key_scene": "旧殿深处的青焰火盆突然暴涨。",
        "emotion": "压抑",
        "fidelity_notes": "",
        "memorable_line": "这火不对劲。",
        "world_rule": "异火会主动排斥陌生斗气。",
    }


def make_runner(
    tmp_dir: str,
    *,
    asset_lock: dict | None = None,
    payload_overrides: dict[str, object] | None = None,
) -> chapter_factory.ChapterFactoryRunner:
    job_dir = Path(tmp_dir) / "job_1"
    context = ExecutionContext(job_id=1, project_id=1, job_dir=job_dir)
    plan = PlannedJob(
        workflow=[
            WorkflowStep(key="asset_lock", title="asset_lock", description=""),
            WorkflowStep(key="storyboard_design", title="storyboard_design", description=""),
            WorkflowStep(key="chapter_packaging", title="chapter_packaging", description=""),
            WorkflowStep(key="qa_loop", title="qa_loop", description=""),
        ],
        artifacts=[],
        summary="plan",
    )
    payload = {
        "source_title": "测试原作",
        "chapter_range": "1-1",
        "episode_count": 1,
        "visual_style": "电影级东方奇幻",
        "chapter_briefs": [make_brief()],
        "adaptation_pack": "",
        "target_duration_seconds": 60,
    }
    if asset_lock is not None:
        payload["asset_lock"] = asset_lock
    if payload_overrides:
        payload.update(payload_overrides)

    with mock.patch.object(chapter_factory.ArkProvider, "from_local_secrets", return_value=None):
        with mock.patch.object(
            chapter_factory,
            "load_storyboard_profile",
            return_value={
                "required_fields": [],
                "target_duration_seconds": 60,
                "group_durations": [10, 10, 10, 10, 10, 10],
                "group_style_blocks": [],
            },
        ):
            return chapter_factory.ChapterFactoryRunner(
                payload=payload,
                context=context,
                plan=plan,
                normalize_chapter_briefs=lambda **kwargs: payload["chapter_briefs"],
                build_prompts=lambda **kwargs: {"lead_character": "lead", "storyboard": []},
                format_research_brief=lambda item: f"- {item['title']}",
                write_placeholder_image=lambda output_path, **_kwargs: output_path.parent.mkdir(parents=True, exist_ok=True) or output_path.write_bytes(b"img"),
                load_font=lambda *_args, **_kwargs: None,
            )


class MangaCapabilityAssetLockTests(unittest.TestCase):
    def test_plan_job_starts_with_asset_lock_step(self) -> None:
        capability = MangaCapability()

        plan = capability.plan_job(
            {
                "source_title": "测试原作",
                "chapter_range": "1-1",
                "episode_count": 1,
                "visual_style": "电影级东方奇幻",
                "chapter_briefs": [make_brief()],
            }
        )

        self.assertEqual(plan.workflow[0].key, "asset_lock")

    def test_build_prompts_uses_asset_lock_primary_character_and_scene_baseline(self) -> None:
        capability = MangaCapability()

        prompts = capability._build_prompts(
            source_title="测试原作",
            visual_style="电影级东方奇幻",
            chapter_briefs=[make_brief()],
            scene_count=1,
            asset_lock=build_asset_lock_payload(),
        )

        self.assertIn("黑色短发，深色练功短衫，左手古朴戒指，少年感明显。", prompts["lead_character"])
        self.assertIn("冷色地下宫殿宿舍", prompts["storyboard"][0])


class ChapterFactoryAssetLockTests(unittest.TestCase):
    def test_story_grounding_extracts_scene_conflict_relationship_and_dialogue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = make_runner(tmp_dir, asset_lock=build_asset_lock_payload())
            source_text = (
                "乌坦城测试广场上，测验魔石碑泛着冷光。999\n"
                "“萧炎，斗之力，三段！级别：低级！”执事冷声宣布。352\n"
                "周围族人哄笑，萧炎攥紧拳头，指节发白。186\n"
                "萧薰儿穿过人群站到他身前，低声说：“萧炎哥哥，别理他们。”50\n"
                "萧战皱眉望向长老席，强行压住场面。12\n"
            )

            grounding = runner._build_story_grounding(make_brief(), source_text)

        self.assertIn("乌坦城测试广场", json.dumps(grounding["scene_anchors"], ensure_ascii=False))
        self.assertIn("周围族人哄笑", json.dumps(grounding["conflict_points"], ensure_ascii=False))
        self.assertIn("萧炎哥哥，别理他们。", grounding["dialogue_candidates"])
        self.assertTrue(any(item.get("source") == "quoted_dialogue" for item in grounding["dialogue_candidates_detailed"]))
        self.assertTrue(any("萧炎" in item and "萧薰儿" in item for item in grounding["character_relationships"]))
        self.assertTrue(all("999" not in item for item in grounding["cleaned_source_lines"]))

    def test_story_grounding_and_blueprint_use_real_characters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = make_runner(tmp_dir, asset_lock=build_asset_lock_payload())
            source_text = "萧炎在旧殿里察觉异火躁动，老师提醒他不要贸然碰火。"

            grounding = runner._build_story_grounding(make_brief(), source_text)
            blueprint = runner._build_storyboard_blueprint(make_brief(), grounding)

        self.assertGreaterEqual(len(grounding["characters"]), 2)
        self.assertEqual(grounding["characters"][0]["name"], "萧炎")
        self.assertNotIn("主角", json.dumps(blueprint, ensure_ascii=False))
        self.assertTrue(all(shot.get("speaker") != "主角" for shot in blueprint["shots"] if shot.get("speaker")))

    def test_blueprint_prefers_grounded_actions_and_filters_low_value_narration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = make_runner(tmp_dir, asset_lock=build_asset_lock_payload())
            source_text = (
                "乌坦城测试广场上，测验魔石碑泛着冷光。\n"
                "“萧炎，斗之力，三段！级别：低级！”执事冷声宣布。\n"
                "周围族人哄笑，萧炎攥紧拳头，指节发白。\n"
                "萧薰儿穿过人群站到他身前，低声说：“萧炎哥哥，别理他们。”\n"
                "萧战皱眉望向长老席，强行压住场面。\n"
            )
            grounding = runner._build_story_grounding(make_brief(), source_text)
            blueprint = runner._build_storyboard_blueprint(make_brief(), grounding)

        shot_dump = json.dumps(blueprint["shots"], ensure_ascii=False)
        self.assertIn("攥紧拳头", shot_dump)
        self.assertIn("站到他身前", shot_dump)
        self.assertIn("萧炎哥哥，别理他们。", shot_dump)
        self.assertNotIn("级别", shot_dump)
        self.assertNotIn("萧炎斗之力测试仅三段遭众人嘲讽", shot_dump)

    def test_blueprint_uses_chapter_duration_plan_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = make_runner(
                tmp_dir,
                asset_lock=build_asset_lock_payload(),
                payload_overrides={"chapter_duration_plan": {"1": 72}},
            )
            grounding = runner._build_story_grounding(make_brief(), "萧炎与萧薰儿在广场对话。")
            blueprint = runner._build_storyboard_blueprint(make_brief(), grounding)

        self.assertEqual(blueprint["target_duration_seconds"], 72.0)

    def test_normalize_storyboard_rows_adds_real_present_characters_and_speaker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = make_runner(tmp_dir, asset_lock=build_asset_lock_payload())
            rows = [
                {
                    "镜头号": 1,
                    "时长(s)": 6,
                    "场景/时间": "旧殿 夜",
                    "镜头景别": "中景",
                    "镜头运动": "缓推",
                    "画面内容": "小炎子和老师踏入旧殿",
                    "人物动作/神态": "戒备",
                    "旁白": "",
                    "对白角色": "小炎子",
                    "对白": "跟紧我。",
                    "角色": "小炎子、老师",
                    "节奏目的": "冲突升级",
                }
            ]

            normalized = runner._normalize_storyboard_rows(rows, make_brief())

        self.assertEqual(normalized[0]["对白角色"], "萧炎")
        self.assertEqual(normalized[0]["出镜角色"], "萧炎、药老")
        self.assertEqual(normalized[0]["旁白"], "")

    def test_build_audio_plan_emits_canonical_character_voice_and_mix_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = make_runner(tmp_dir, asset_lock=build_asset_lock_payload())
            rows = runner._normalize_storyboard_rows(
                [
                    {
                        "镜头号": 1,
                        "时长(s)": 6,
                        "场景/时间": "旧殿 夜",
                        "镜头景别": "近景",
                        "镜头运动": "缓推",
                        "画面内容": "小炎子盯着异火",
                        "人物动作/神态": "压住呼吸",
                        "旁白": "旧殿深处的火焰开始反咬空气。",
                        "对白角色": "小炎子",
                        "对白": "这火不对劲。",
                        "角色": "小炎子",
                        "节奏目的": "高潮",
                    }
                ],
                make_brief(),
            )

            audio_plan = runner._build_audio_plan(make_brief(), rows)

        self.assertEqual(audio_plan["dialogue_tracks"][0]["canonical_character"], "萧炎")
        self.assertEqual(audio_plan["dialogue_tracks"][0]["voice_id"], "voice.lead")
        self.assertEqual(audio_plan["dialogue_tracks"][0]["bus"], "dialogue_bus")
        self.assertEqual(audio_plan["narration_tracks"][0]["canonical_character"], "旁白")
        self.assertEqual(audio_plan["narration_tracks"][0]["voice_id"], "voice.narrator")
        self.assertEqual(audio_plan["narration_tracks"][0]["bus"], "narration_bus")
        self.assertIn("mix_profile", audio_plan)

    def test_build_audio_plan_reduces_redundant_narration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = make_runner(tmp_dir, asset_lock=build_asset_lock_payload())
            rows = runner._normalize_storyboard_rows(
                [
                    {
                        "镜头号": 1,
                        "时长(s)": 5,
                        "场景/时间": "旧殿 夜",
                        "镜头景别": "近景",
                        "镜头运动": "缓推",
                        "画面内容": "萧炎停在火盆前",
                        "人物动作/神态": "紧张",
                        "旁白": "旧殿深处的火焰开始反咬空气。",
                        "对白角色": "萧炎",
                        "对白": "这火不对劲。",
                        "角色": "萧炎",
                        "节奏目的": "开场钩子",
                    },
                    {
                        "镜头号": 2,
                        "时长(s)": 5,
                        "场景/时间": "旧殿 夜",
                        "镜头景别": "中景",
                        "镜头运动": "定镜",
                        "画面内容": "药老悬停在萧炎身后",
                        "人物动作/神态": "克制",
                        "旁白": "药老看出异火在排斥陌生斗气。",
                        "对白角色": "药老",
                        "对白": "先别碰它。",
                        "角色": "药老、萧炎",
                        "节奏目的": "关系建立",
                    },
                ],
                make_brief(),
            )

            audio_plan = runner._build_audio_plan(make_brief(), rows)

        self.assertLess(len(audio_plan["narration_tracks"]), len(rows))
        self.assertEqual(audio_plan["mix_profile"]["dialogue_priority"], 100)
        self.assertEqual(audio_plan["mix_profile"]["ducking"]["narration_when_dialogue"], 0.4)
        self.assertEqual(audio_plan["mix_profile"]["ducking"]["ambience_when_dialogue"], 0.6)

    def test_synthesize_voiceover_renders_timeline_tracks_and_mixes_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = make_runner(tmp_dir, asset_lock=build_asset_lock_payload())
            output_path = Path(tmp_dir) / "voiceover.mp3"
            audio_plan = {
                "render_mode": "timeline_multitrack",
                "voice_style": "voice.narrator",
                "narration_tracks": [
                    {
                        "shot": 1,
                        "text": "旧殿深处的火焰开始反咬空气。",
                        "canonical_character": "旁白",
                        "voice_id": "voice.narrator",
                        "start_seconds": 0.0,
                        "target_duration_seconds": 2.6,
                        "bus": "narration_bus",
                    }
                ],
                "dialogue_tracks": [
                    {
                        "shot": 1,
                        "speaker": "萧炎",
                        "text": "这火不对劲。",
                        "canonical_character": "萧炎",
                        "voice_id": "voice.lead",
                        "start_seconds": 2.8,
                        "target_duration_seconds": 2.2,
                        "bus": "dialogue_bus",
                    }
                ],
            }
            rendered_calls: list[tuple[str, str, float, float, str]] = []
            mixed_tracks: list[dict[str, object]] = []

            def fake_render_track_audio(*, track: dict[str, object], output_path: Path) -> None:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"track")
                rendered_calls.append(
                    (
                        str(track["canonical_character"]),
                        str(track["voice_id"]),
                        float(track["start_seconds"]),
                        float(track["target_duration_seconds"]),
                        output_path.name,
                    )
                )

            def fake_mix_timeline_voice_tracks(*, rendered_tracks: list[dict[str, object]], output_path: Path) -> None:
                mixed_tracks.extend(rendered_tracks)
                output_path.write_bytes(b"mix")

            runner._render_track_audio = fake_render_track_audio
            runner._mix_timeline_voice_tracks = fake_mix_timeline_voice_tracks

            runner._synthesize_voiceover(audio_plan, output_path)
            self.assertTrue(output_path.exists())
            self.assertEqual(len(rendered_calls), 2)
            self.assertEqual(rendered_calls[0][0], "旁白")
            self.assertEqual(rendered_calls[1][0], "萧炎")
            self.assertEqual(len(mixed_tracks), 2)
            self.assertEqual(mixed_tracks[1]["canonical_character"], "萧炎")

    def test_mux_audio_uses_split_bus_before_ducking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = make_runner(tmp_dir, asset_lock=build_asset_lock_payload())
            silent_video = Path(tmp_dir) / "chapter_preview_silent.mp4"
            voiceover = Path(tmp_dir) / "voiceover.mp3"
            ambience = Path(tmp_dir) / "ambience.wav"
            output_path = Path(tmp_dir) / "chapter_preview.mp4"
            for path in (silent_video, voiceover, ambience):
                path.write_bytes(b"stub")

            with mock.patch.object(chapter_factory.subprocess, "run") as run_mock:
                runner._mux_audio(silent_video, voiceover, ambience, output_path)

        command = run_mock.call_args.args[0]
        filter_index = command.index("-filter_complex") + 1
        filter_graph = command[filter_index]
        self.assertIn("asplit=2[voice_duck][voice_mix]", filter_graph)
        self.assertIn("[ambience_bus][voice_duck]sidechaincompress", filter_graph)
        self.assertIn("[voice_mix][ambience_ducked]amix", filter_graph)

    def test_generate_keyframe_prompts_injects_scene_and_character_locks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = make_runner(tmp_dir, asset_lock=build_asset_lock_payload())
            row = runner._normalize_storyboard_rows(
                [
                    {
                        "镜头号": 1,
                        "时长(s)": 6,
                        "场景/时间": "旧殿 夜",
                        "镜头景别": "近景",
                        "镜头运动": "缓推",
                        "画面内容": "小炎子盯着异火",
                        "人物动作/神态": "压住呼吸",
                        "旁白": "",
                        "对白角色": "小炎子",
                        "对白": "这火不对劲。",
                        "角色": "小炎子",
                        "节奏目的": "高潮",
                    }
                ],
                make_brief(),
            )[0]
            prompts, image_paths = runner._generate_keyframes(Path(tmp_dir) / "images", make_brief(), [row])

        self.assertEqual(len(image_paths), 1)
        self.assertIn("冷色地下宫殿宿舍", prompts[0])
        self.assertIn("黑色短发，深色练功短衫，左手古朴戒指，少年感明显。", prompts[0])

    def test_review_plan_blocks_unmapped_speakers_invalid_assets_and_generic_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = make_runner(tmp_dir, asset_lock=build_asset_lock_payload(include_invalid_reference=True))
            rows = runner._normalize_storyboard_rows(
                [
                    {
                        "镜头号": 1,
                        "时长(s)": 6,
                        "场景/时间": "旧殿 夜",
                        "镜头景别": "近景",
                        "镜头运动": "缓推",
                        "画面内容": "陌生人闯入旧殿",
                        "人物动作/神态": "冷硬",
                        "旁白": "门口突然多了一道陌生的气息。",
                        "对白角色": "路人甲",
                        "对白": "把火交出来。",
                        "出镜角色": "",
                        "角色": "路人甲",
                        "节奏目的": "冲突升级",
                    }
                ],
                make_brief(),
            )
            audio_plan = runner._build_audio_plan(make_brief(), rows)
            review = runner._review_plan(make_brief(), rows, audio_plan)

        self.assertIn("出镜角色缺失或无法归一", review["blockers"])
        self.assertIn("对白角色无法映射到音色", review["blockers"])
        self.assertIn("资产锁引用路径无效", review["blockers"])

    def test_write_job_level_outputs_persists_asset_lock_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = make_runner(tmp_dir, asset_lock=build_asset_lock_payload())
            root = Path(tmp_dir)
            storyboard_dir = root / "storyboard"
            preview_dir = root / "preview"
            delivery_dir = root / "delivery"
            for path in (storyboard_dir, preview_dir, delivery_dir):
                path.mkdir(parents=True, exist_ok=True)

            (root / "chapters" / "chapter_01" / "images").mkdir(parents=True, exist_ok=True)
            keyframe_path = root / "chapters" / "chapter_01" / "images" / "keyframe_01.png"
            keyframe_path.write_bytes(b"img")
            preview_video = preview_dir / "preview.mp4"
            delivery_video = delivery_dir / "final_cut.mp4"
            preview_video.write_bytes(b"preview")
            delivery_video.write_bytes(b"delivery")
            chapter_preview = root / "chapters" / "chapter_01" / "preview.mp4"
            chapter_delivery = root / "chapters" / "chapter_01" / "final.mp4"
            chapter_preview.write_bytes(b"preview")
            chapter_delivery.write_bytes(b"delivery")

            runner.chapter_packages = [
                {
                    "chapter": 1,
                    "title": "第1章",
                    "storyboard": {"chapter": 1, "title": "第1章", "rows": []},
                    "audio_plan": {},
                    "artifact_paths": ["chapters/chapter_01/storyboard/storyboard.json"],
                    "preview_video": str(chapter_preview),
                    "delivery_video": str(chapter_delivery),
                    "video_plan": {},
                    "image_prompts": ["prompt"],
                    "qa": {"passed": True, "summary": "通过 QA"},
                }
            ]
            runner.chapter_artifacts = []
            runner.provider_notes = []
            runner._concat_videos = lambda _paths, output_path: output_path.write_bytes(b"video")
            runner._build_preview_html = lambda: "<html></html>"

            prompts_path = root / "prompts.json"
            storyboard_path = storyboard_dir / "storyboard.json"
            chapters_index_path = root / "chapters_index.json"
            qa_overview_path = root / "qa_overview.md"
            manifest_path = root / "manifest.json"
            snapshot_path = root / "asset_lock_snapshot.json"

            with mock.patch.object(chapter_factory, "ARTIFACTS_DIR", root):
                runner._write_job_level_outputs(
                    prompt_bundle={"lead_character": "lead", "storyboard": ["prompt"]},
                    storyboard_dir=storyboard_dir,
                    prompts_path=prompts_path,
                    storyboard_path=storyboard_path,
                    chapters_index_path=chapters_index_path,
                    qa_overview_path=qa_overview_path,
                    preview_path=preview_dir / "index.html",
                    preview_video_path=preview_video,
                    delivery_video_path=delivery_video,
                    manifest_path=manifest_path,
                    asset_lock_snapshot_path=snapshot_path,
                )

            prompts_payload = json.loads(prompts_path.read_text(encoding="utf-8"))
            storyboard_payload = json.loads(storyboard_path.read_text(encoding="utf-8"))
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            snapshot_payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

        self.assertIn("asset_lock", prompts_payload)
        self.assertIn("asset_lock", storyboard_payload)
        self.assertIn("asset_lock", manifest_payload)
        self.assertEqual(snapshot_payload["characters"][0]["name"], "萧炎")


if __name__ == "__main__":
    unittest.main()
