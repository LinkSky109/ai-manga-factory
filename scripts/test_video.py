#!/usr/bin/env python3
"""
Video-only Ark generation test.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
WORKHOME_ROOT = PROJECT_ROOT.parent.parent
VERIFICATION_ROOT = WORKHOME_ROOT / "management" / "ai-manga-factory" / "verification" / "provider-tests"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.providers.ark import ArkProvider


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Ark video generation.")
    parser.add_argument("--output", type=Path, default=VERIFICATION_ROOT / "provider_test_preview.mp4")
    parser.add_argument(
        "--prompt",
        default="Cinematic dark xianxia trailer, moonlit ritual courtyard, slow camera pan.",
    )
    parser.add_argument("--video-model", default=ArkProvider.DEFAULT_VIDEO_MODEL)
    args = parser.parse_args()

    provider = ArkProvider.from_local_secrets(
        root_dir=PROJECT_ROOT,
        image_model=ArkProvider.DEFAULT_IMAGE_MODEL,
        video_model=args.video_model,
    )
    if provider is None:
        print("Provider credentials not found.")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    provider.generate_video_to_file(
        prompt=args.prompt,
        output_path=args.output,
        duration_seconds=5,
        ratio="16:9",
        resolution="720p",
        max_wait_seconds=900,
        poll_interval_seconds=8,
    )
    print(f"Video API test success. Video saved to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
