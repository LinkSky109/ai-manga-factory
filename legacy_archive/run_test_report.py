from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from shared.runtime_consistency import check_runtime_consistency

ROOT = Path(__file__).resolve().parent
SMOKE_SCRIPT = ROOT / "scripts" / "run_frontend_real_media_smoke.mjs"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate an AI Manga Factory verification report")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--output", default=str(ROOT / "test_report.json"), help="Report output path")
    return parser


def build_report(base_url: str) -> dict[str, object]:
    runtime = check_runtime_consistency(base_url)
    smoke_entry = {
        "command": f"python start_project.py smoke-browser --app-url {base_url}",
        "script_exists": SMOKE_SCRIPT.exists(),
        "script_path": str(SMOKE_SCRIPT),
    }
    recommendations: list[str] = []

    openapi = runtime.get("openapi", {})
    if isinstance(openapi, dict) and openapi.get("missing_paths"):
        missing = ", ".join(str(path) for path in openapi.get("missing_paths", []))
        recommendations.append(f"Fix missing OpenAPI routes: {missing}")

    if not bool(runtime.get("ok")):
        recommendations.append("Run `python start_project.py verify-deploy --base-url ...` after restart or deploy.")

    if not smoke_entry["script_exists"]:
        recommendations.append("Restore the browser smoke script before enabling the smoke entry.")

    return {
        "project": "ai-manga-factory",
        "runtime_consistency": runtime,
        "smoke_entry": smoke_entry,
        "recommendations": recommendations,
    }


def main() -> int:
    args = build_parser().parse_args()
    report = build_report(args.base_url)
    output_path = Path(args.output)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report["runtime_consistency"].get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
