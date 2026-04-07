#!/usr/bin/env python3
"""
Minimal connectivity test for Ark image/video generation.
No hardcoded credentials are allowed in this script.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.providers.ark import ArkProvider


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Ark image/video API with environment credentials.")
    parser.add_argument("--image-output", type=Path, default=Path("data/provider_test_scene_square.png"))
    parser.add_argument("--video-output", type=Path, default=Path("data/provider_test_preview.mp4"))
    parser.add_argument(
        "--prompt",
        default="Dark xianxia manga scene, moonlit ruin, eerie atmosphere, cinematic lighting.",
    )
    parser.add_argument(
        "--video-prompt",
        default="Cinematic dark xianxia trailer shot, eerie moonlit ruin, slow camera move, high contrast.",
    )
    parser.add_argument("--video", action="store_true", help="Also run a short video generation test.")
    parser.add_argument("--image-model", default=ArkProvider.DEFAULT_IMAGE_MODEL)
    parser.add_argument("--video-model", default=ArkProvider.DEFAULT_VIDEO_MODEL)
    args = parser.parse_args()

    provider = ArkProvider.from_local_secrets(
        root_dir=PROJECT_ROOT,
        image_model=args.image_model,
        video_model=args.video_model,
    )
    if provider is None:
        print("Provider credentials not found.")
        return 1

    args.image_output.parent.mkdir(parents=True, exist_ok=True)
    provider.generate_image_to_file(prompt=args.prompt, output_path=args.image_output)
    print(f"Image API test success. Image saved to: {args.image_output}")

    if args.video:
        args.video_output.parent.mkdir(parents=True, exist_ok=True)
        provider.generate_video_to_file(
            prompt=args.video_prompt,
            output_path=args.video_output,
            duration_seconds=5,
            ratio="16:9",
            resolution="720p",
            max_wait_seconds=900,
            poll_interval_seconds=8,
        )
        print(f"Video API test success. Video saved to: {args.video_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
