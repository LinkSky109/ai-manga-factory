#!/usr/bin/env python3
"""把外部 Excel 分镜参考导入为项目内可复用的结构化模板。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.storyboard_reference import PROFILE_JSON, REFERENCE_JSON, save_storyboard_reference_from_workbook


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导入 Excel 分镜参考模板")
    parser.add_argument("--workbook", required=True, help="Excel 分镜表路径")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = save_storyboard_reference_from_workbook(Path(args.workbook))
    print(f"已导入分镜参考：{args.workbook}")
    print(f"参考 JSON：{REFERENCE_JSON}")
    print(f"模板 Profile：{PROFILE_JSON}")
    print(f"Sheet 数量：{len(payload['sheets'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
