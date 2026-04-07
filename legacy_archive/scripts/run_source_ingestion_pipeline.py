#!/usr/bin/env python3
"""一键串联原文 URL 清单生成、Playwright 抓取、原文导入和摘要生成。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.adaptation_packs import get_adaptation_pack


@dataclass(frozen=True)
class StepResult:
    name: str
    status: str
    command: list[str]
    started_at: str
    finished_at: str
    return_code: int
    stdout: str
    stderr: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行原文抓取与导入流水线")
    parser.add_argument("--pack-name", required=True, help="适配包名称，例如 dpcq_ch1_20")
    parser.add_argument("--config-file", default=None, help="Playwright 配置文件")
    parser.add_argument("--toc-file", default=None, help="可选，目录页 HTML")
    parser.add_argument("--base-url", default=None, help="目录页相对链接的基地址")
    parser.add_argument("--url-manifest", default=None, help="source_urls.json 路径")
    parser.add_argument("--source-dir", default=None, help="导入原文时使用的 HTML 目录")
    parser.add_argument("--chapter-start", type=int, default=None)
    parser.add_argument("--chapter-end", type=int, default=None)
    parser.add_argument("--page-limit", type=int, default=None, help="抓取页数限制，便于试跑")
    parser.add_argument("--wait-selector", default=None)
    parser.add_argument("--title-selector", default=None)
    parser.add_argument("--content-selector", default=None)
    parser.add_argument("--browser", default=None)
    parser.add_argument("--channel", default=None)
    parser.add_argument("--headed", dest="headless", action="store_false", default=None)
    parser.add_argument("--headless", dest="headless", action="store_true", default=None)
    parser.add_argument("--skip-manifest", action="store_true", help="跳过 URL 清单生成")
    parser.add_argument("--skip-capture", action="store_true", help="跳过 Playwright 抓取")
    parser.add_argument("--skip-collect", action="store_true", help="跳过原文导入")
    parser.add_argument("--skip-briefs", action="store_true", help="跳过章节摘要生成")
    parser.add_argument("--force-manifest", action="store_true", help="强制重写 source_urls.json")
    parser.add_argument(
        "--no-overwrite-source",
        dest="overwrite_source",
        action="store_false",
        default=True,
        help="保留已有 source/chapters，不覆盖",
    )
    parser.add_argument(
        "--keep-existing-briefs",
        dest="force_briefs",
        action="store_false",
        default=True,
        help="保留已有非占位章节摘要，不强制覆盖",
    )
    parser.add_argument("--source-max-chars", type=int, default=None, help="传给摘要生成脚本的原文截断长度")
    parser.add_argument("--text-model", default=None, help="可选，覆盖摘要生成使用的文本模型")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pack = get_adaptation_pack(args.pack_name)
    snapshot_path = pack.root_dir / "source" / "incoming" / "source_pipeline_snapshot.json"
    report_path = pack.root_dir / "reports" / "source_pipeline_report.md"
    default_config_path = pack.root_dir / "source" / "playwright_capture.template.json"
    default_manifest_path = pack.root_dir / "source" / "incoming" / "source_urls.json"
    default_capture_dir = pack.root_dir / "source" / "incoming" / "playwright_html"

    config_path = resolve_optional_path(args.config_file) or (default_config_path if default_config_path.exists() else None)
    url_manifest_path = resolve_optional_path(args.url_manifest) or default_manifest_path
    source_dir = resolve_optional_path(args.source_dir) or default_capture_dir

    step_results: list[StepResult] = []
    overall_status = "completed"
    failure_message = ""

    try:
        if not args.skip_manifest:
            step_results.append(
                run_step(
                    name="build_source_url_manifest",
                    command=build_manifest_command(args=args, url_manifest_path=url_manifest_path),
                )
            )
        if not args.skip_capture:
            step_results.append(
                run_step(
                    name="playwright_capture",
                    command=build_capture_command(
                        args=args,
                        config_path=config_path,
                        url_manifest_path=url_manifest_path,
                    ),
                )
            )
        if not args.skip_collect:
            step_results.append(
                run_step(
                    name="collect_source_text",
                    command=build_collect_command(args=args, source_dir=source_dir),
                )
            )
        if not args.skip_briefs:
            step_results.append(
                run_step(
                    name="generate_chapter_briefs",
                    command=build_brief_command(args=args),
                )
            )
    except subprocess.CalledProcessError as exc:
        overall_status = "failed"
        failure_message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        step_results.append(
            StepResult(
                name=infer_failed_step_name(exc.cmd),
                status="failed",
                command=list(exc.cmd) if isinstance(exc.cmd, list) else [str(exc.cmd)],
                started_at=datetime.now().isoformat(),
                finished_at=datetime.now().isoformat(),
                return_code=int(exc.returncode),
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
            )
        )

    snapshot = build_snapshot(
        pack_name=args.pack_name,
        status=overall_status,
        failure_message=failure_message,
        config_path=config_path,
        url_manifest_path=url_manifest_path,
        source_dir=source_dir,
        step_results=step_results,
    )
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(render_report(snapshot), encoding="utf-8")

    print(f"流水线状态：{overall_status}")
    print(f"快照：{snapshot_path}")
    print(f"报告：{report_path}")
    if overall_status != "completed":
        print(f"失败原因：{safe_console_text(failure_message)}")
        return 1
    return 0


def build_manifest_command(*, args: argparse.Namespace, url_manifest_path: Path) -> list[str]:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "build_source_url_manifest.py"),
        "--pack-name",
        args.pack_name,
        "--output",
        str(url_manifest_path),
        "--merge-existing",
    ]
    if args.force_manifest:
        command.append("--force")
    if args.chapter_start is not None:
        command.extend(["--chapter-start", str(args.chapter_start)])
    if args.chapter_end is not None:
        command.extend(["--chapter-end", str(args.chapter_end)])
    if args.wait_selector:
        command.extend(["--wait-selector", args.wait_selector])
    if args.content_selector:
        command.extend(["--content-selector", args.content_selector])
    if args.title_selector:
        command.extend(["--title-selector", args.title_selector])
    if args.toc_file:
        command.extend(["--toc-file", str(resolve_optional_path(args.toc_file) or args.toc_file)])
    if args.base_url:
        command.extend(["--base-url", args.base_url])
    return command


def build_capture_command(
    *,
    args: argparse.Namespace,
    config_path: Path | None,
    url_manifest_path: Path,
) -> list[str]:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "playwright_source_capture.py"),
        "capture",
        "--pack-name",
        args.pack_name,
        "--url-manifest",
        str(url_manifest_path),
    ]
    if config_path is not None:
        command.extend(["--config-file", str(config_path)])
    if args.page_limit is not None:
        command.extend(["--page-limit", str(args.page_limit)])
    if args.wait_selector:
        command.extend(["--wait-selector", args.wait_selector])
    if args.title_selector:
        command.extend(["--title-selector", args.title_selector])
    if args.browser:
        command.extend(["--browser", args.browser])
    if args.channel:
        command.extend(["--channel", args.channel])
    if args.headless is True:
        command.append("--headless")
    elif args.headless is False:
        command.append("--headed")
    return command


def build_collect_command(*, args: argparse.Namespace, source_dir: Path) -> list[str]:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "collect_source_text.py"),
        "--pack-name",
        args.pack_name,
        "--source-dir",
        str(source_dir),
    ]
    if args.chapter_start is not None:
        command.extend(["--chapter-start", str(args.chapter_start)])
    if args.chapter_end is not None:
        command.extend(["--chapter-end", str(args.chapter_end)])
    if args.overwrite_source:
        command.append("--overwrite")
    return command


def build_brief_command(*, args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "generate_chapter_briefs.py"),
        "--pack-name",
        args.pack_name,
    ]
    if args.chapter_start is not None:
        command.extend(["--chapter-start", str(args.chapter_start)])
    if args.chapter_end is not None:
        command.extend(["--chapter-end", str(args.chapter_end)])
    if args.source_max_chars is not None:
        command.extend(["--source-max-chars", str(args.source_max_chars)])
    if args.text_model:
        command.extend(["--text-model", args.text_model])
    if args.force_briefs:
        command.append("--force")
    return command


def run_step(*, name: str, command: list[str]) -> StepResult:
    started_at = datetime.now().isoformat()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return StepResult(
        name=name,
        status="completed",
        command=command,
        started_at=started_at,
        finished_at=datetime.now().isoformat(),
        return_code=int(completed.returncode),
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def build_snapshot(
    *,
    pack_name: str,
    status: str,
    failure_message: str,
    config_path: Path | None,
    url_manifest_path: Path,
    source_dir: Path,
    step_results: list[StepResult],
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(),
        "pack_name": pack_name,
        "status": status,
        "failure_message": failure_message,
        "config_path": str(config_path) if config_path else "",
        "url_manifest_path": str(url_manifest_path),
        "source_dir": str(source_dir),
        "steps": [
            {
                "name": item.name,
                "status": item.status,
                "command": item.command,
                "started_at": item.started_at,
                "finished_at": item.finished_at,
                "return_code": item.return_code,
                "stdout": item.stdout,
                "stderr": item.stderr,
            }
            for item in step_results
        ],
    }


def render_report(snapshot: dict[str, Any]) -> str:
    lines = [
        "# 原文抓取流水线报告",
        "",
        f"- 时间：{snapshot['generated_at']}",
        f"- 适配包：{snapshot['pack_name']}",
        f"- 状态：{snapshot['status']}",
        f"- 配置文件：{snapshot['config_path'] or '未指定'}",
        f"- URL 清单：{snapshot['url_manifest_path']}",
        f"- 原文目录：{snapshot['source_dir']}",
    ]
    if snapshot.get("failure_message"):
        lines.append(f"- 失败原因：{snapshot['failure_message']}")
    lines.extend(["", "## 步骤结果"])
    for step in snapshot.get("steps", []):
        lines.extend(
            [
                f"- {step['name']} | {step['status']} | return_code={step['return_code']}",
                f"  命令：{' '.join(step['command'])}",
            ]
        )
        if step.get("stdout", "").strip():
            lines.append(f"  stdout：{collapse_whitespace(step['stdout'])}")
        if step.get("stderr", "").strip():
            lines.append(f"  stderr：{collapse_whitespace(step['stderr'])}")
    lines.append("")
    return "\n".join(lines)


def collapse_whitespace(text: str) -> str:
    return " ".join(text.strip().split())


def safe_console_text(text: str) -> str:
    encoding = sys.stdout.encoding or "utf-8"
    return str(text).encode(encoding, errors="backslashreplace").decode(encoding, errors="ignore")


def resolve_optional_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / raw
    return path


def infer_failed_step_name(command: Any) -> str:
    if isinstance(command, list):
        text = " ".join(str(item) for item in command)
    else:
        text = str(command)
    if "build_source_url_manifest.py" in text:
        return "build_source_url_manifest"
    if "playwright_source_capture.py" in text:
        return "playwright_capture"
    if "collect_source_text.py" in text:
        return "collect_source_text"
    if "generate_chapter_briefs.py" in text:
        return "generate_chapter_briefs"
    return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
