from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from shared.asset_lock import (
    asset_lock_from_payload,
    ensure_asset_lock_scaffold,
    load_asset_lock,
    load_asset_cards,
)


class AssetLockTests(unittest.TestCase):
    def test_missing_file_returns_empty_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_dir = Path(tmp_dir)

            first = load_asset_lock(pack_dir)
            second = load_asset_lock(pack_dir)

        self.assertFalse(first.exists)
        self.assertEqual(first.characters, ())
        self.assertEqual(first.validation_errors, ())
        self.assertIsNone(first.resolve_character("主角"))
        self.assertIsNot(first, second)

    def test_load_asset_lock_normalizes_aliases_and_resolves_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_dir = Path(tmp_dir)
            (pack_dir / "assets" / "characters").mkdir(parents=True)
            (pack_dir / "assets" / "scenes").mkdir(parents=True)
            (pack_dir / "assets" / "loras").mkdir(parents=True)
            (pack_dir / "assets" / "characters" / "lead.png").write_bytes(b"lead")
            (pack_dir / "assets" / "scenes" / "baseline.png").write_bytes(b"scene")
            (pack_dir / "assets" / "loras" / "lead.safetensors").write_bytes(b"lora")
            (pack_dir / "asset_lock.json").write_text(
                json.dumps(
                    {
                        "scene": {
                            "baseline_prompt": "冷色地下宫殿宿舍，潮湿石墙与青焰火盆保持统一。",
                            "reference_image_path": "assets/scenes/baseline.png",
                        },
                        "characters": [
                            {
                                "name": "萧炎",
                                "aliases": ["小炎子"],
                                "fixed_prompt": "黑色短发，深色练功短衫，左手古朴戒指。",
                                "voice_id": "voice.lead",
                                "reference_image_path": "assets/characters/lead.png",
                                "lora_path": "assets/loras/lead.safetensors",
                            },
                            {
                                "name": "旁白",
                                "aliases": ["解说"],
                                "fixed_prompt": "冷静克制的叙事旁白。",
                                "voice_id": "voice.narrator",
                            },
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            asset_lock = load_asset_lock(pack_dir)
            roundtrip = asset_lock_from_payload(asset_lock.to_payload())

        self.assertTrue(asset_lock.exists)
        self.assertEqual(asset_lock.scene_baseline_prompt, "冷色地下宫殿宿舍，潮湿石墙与青焰火盆保持统一。")
        self.assertEqual(asset_lock.scene_reference_image_path, pack_dir / "assets" / "scenes" / "baseline.png")
        self.assertEqual(asset_lock.resolve_character(" 小炎子 ").name, "萧炎")
        self.assertEqual(asset_lock.resolve_character("解说").name, "旁白")
        self.assertEqual(asset_lock.characters[0].reference_image_path, pack_dir / "assets" / "characters" / "lead.png")
        self.assertEqual(asset_lock.characters[0].lora_path, pack_dir / "assets" / "loras" / "lead.safetensors")
        self.assertEqual(roundtrip.resolve_character("小炎子").name, "萧炎")
        self.assertEqual(roundtrip.validation_errors, ())

    def test_load_asset_lock_rejects_duplicate_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_dir = Path(tmp_dir)
            (pack_dir / "asset_lock.json").write_text(
                json.dumps(
                    {
                        "scene": {"baseline_prompt": "测试场景"},
                        "characters": [
                            {
                                "name": "萧炎",
                                "aliases": ["阿炎"],
                                "fixed_prompt": "主角固定提示词",
                                "voice_id": "voice.lead",
                            },
                            {
                                "name": "药老",
                                "aliases": ["阿炎"],
                                "fixed_prompt": "老师固定提示词",
                                "voice_id": "voice.support",
                            },
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "alias"):
                load_asset_lock(pack_dir)

    def test_load_asset_lock_reports_missing_reference_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_dir = Path(tmp_dir)
            (pack_dir / "asset_lock.json").write_text(
                json.dumps(
                    {
                        "scene": {
                            "baseline_prompt": "测试场景",
                            "reference_image_path": "assets/scenes/missing.png",
                        },
                        "characters": [
                            {
                                "name": "萧炎",
                                "aliases": ["萧炎"],
                                "fixed_prompt": "主角固定提示词",
                                "voice_id": "voice.lead",
                                "reference_image_path": "assets/characters/missing.png",
                                "lora_path": "assets/loras/missing.safetensors",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            asset_lock = load_asset_lock(pack_dir)

        joined = "\n".join(asset_lock.validation_errors)
        self.assertIn("missing.png", joined)
        self.assertIn("missing.safetensors", joined)

    def test_ensure_asset_lock_scaffold_creates_standardized_asset_cards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_dir = Path(tmp_dir)
            ensure_asset_lock_scaffold(pack_dir, source_title="斗破苍穹")
            asset_cards = load_asset_cards(pack_dir)
            self.assertTrue((pack_dir / "asset_lock.json").exists())
            self.assertTrue((pack_dir / "assets" / "characters" / "character_cards.json").exists())
            self.assertTrue((pack_dir / "assets" / "scenes" / "scene_cards.json").exists())
            self.assertGreaterEqual(len(asset_cards["character_cards"]), 4)
            self.assertEqual(asset_cards["scene_cards"][0]["scene_id"], "primary_world")
            self.assertTrue(all(card["name"] not in {"主角", "同伴", "对手"} for card in asset_cards["character_cards"]))
            self.assertIn("asset_status", asset_cards["character_cards"][0])
            self.assertIn("reference_assets", asset_cards["character_cards"][0])
            self.assertIn("visual_traits", asset_cards["character_cards"][0])
            self.assertIn("review_status", asset_cards["character_cards"][0])
            self.assertIn("review_notes", asset_cards["character_cards"][0])
            self.assertIn("continuity_guardrails", asset_cards["character_cards"][0])
            self.assertIn("asset_status", asset_cards["scene_cards"][0])
            self.assertIn("reference_assets", asset_cards["scene_cards"][0])
            self.assertIn("review_status", asset_cards["scene_cards"][0])
            self.assertIn("review_notes", asset_cards["scene_cards"][0])
            self.assertIn("continuity_guardrails", asset_cards["scene_cards"][0])


if __name__ == "__main__":
    unittest.main()
