from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from backend import adaptation_packs


class AdaptationPackAssetLockTests(unittest.TestCase):
    def test_build_job_payload_includes_pack_asset_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            adaptations_dir = Path(tmp_dir)
            pack_dir = adaptations_dir / "demo_pack"
            pack_dir.mkdir(parents=True)
            (pack_dir / "pack.json").write_text(
                json.dumps(
                    {
                        "pack_name": "demo_pack",
                        "source_title": "测试原作",
                        "chapter_range": "1-2",
                        "default_project_name": "demo-pack",
                        "default_scene_count": 12,
                        "default_target_duration_seconds": 66,
                        "recommended_visual_style": "电影级东方奇幻",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (pack_dir / "chapter_briefs.json").write_text(
                json.dumps(
                    [
                        {"chapter": 1, "title": "第1章", "summary": "摘要1", "key_scene": "场景1", "emotion": "紧张", "target_duration_seconds": 72},
                        {"chapter": 2, "title": "第2章", "summary": "摘要2", "key_scene": "场景2", "emotion": "爆发", "target_duration_seconds": 54},
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (pack_dir / "asset_lock.json").write_text(
                json.dumps(
                    {
                        "scene": {"baseline_prompt": "冷色古殿，压低饱和度。"},
                        "characters": [
                            {
                                "name": "主角",
                                "aliases": ["阿炎"],
                                "fixed_prompt": "黑金劲装，左手古戒。",
                                "voice_id": "voice.lead",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            with mock.patch.object(adaptation_packs, "ADAPTATIONS_DIR", adaptations_dir):
                pack = adaptation_packs.get_adaptation_pack("demo_pack")
                payload = adaptation_packs.build_adaptation_job_payload(
                    pack=pack,
                    project_name=None,
                    scene_count=8,
                    use_real_images=False,
                    image_model=None,
                    video_model=None,
                )

        self.assertIn("asset_lock", payload.input)
        self.assertEqual(payload.input["asset_lock"]["scene"]["baseline_prompt"], "冷色古殿，压低饱和度。")
        self.assertEqual(payload.input["asset_lock"]["characters"][0]["name"], "主角")
        self.assertEqual(payload.input["target_duration_seconds"], 66.0)
        self.assertEqual(payload.input["chapter_duration_plan"], {"1": 72.0, "2": 54.0})

    def test_build_job_payload_omits_asset_lock_when_pack_has_no_lock_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            adaptations_dir = Path(tmp_dir)
            pack_dir = adaptations_dir / "demo_pack"
            pack_dir.mkdir(parents=True)
            (pack_dir / "chapter_briefs.json").write_text(
                json.dumps(
                    [{"chapter": 1, "title": "第1章", "summary": "摘要1", "key_scene": "场景1", "emotion": "紧张"}],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            with mock.patch.object(adaptation_packs, "ADAPTATIONS_DIR", adaptations_dir):
                pack = adaptation_packs.get_adaptation_pack("demo_pack")
                payload = adaptation_packs.build_adaptation_job_payload(
                    pack=pack,
                    project_name="demo",
                    scene_count=6,
                    use_real_images=False,
                    image_model=None,
                    video_model=None,
                )

        self.assertNotIn("asset_lock", payload.input)


if __name__ == "__main__":
    unittest.main()
