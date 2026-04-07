from __future__ import annotations

import argparse
import json
import sys

from shared.runtime_consistency import check_runtime_consistency, print_runtime_consistency


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check AI Manga Factory deploy/runtime consistency")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--json", action="store_true", help="Print raw JSON only")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = check_runtime_consistency(args.base_url)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_runtime_consistency(report)
    return 0 if bool(report.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
