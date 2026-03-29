from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from shared.runtime_consistency import (
    check_runtime_consistency,
    print_runtime_consistency,
    wait_for_runtime_consistency,
)


ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = ROOT.parents[3]
WEB_ROOT = ROOT / "web"
SMOKE_SCRIPT = ROOT / "scripts" / "run_frontend_real_media_smoke.mjs"


def resolve_python() -> str:
    candidates = []
    env_python = os.environ.get("AI_MANGA_FACTORY_PYTHON")
    if env_python:
        candidates.append(Path(env_python))
    current_python = Path(sys.executable).resolve()
    if current_python.exists():
        candidates.append(current_python)
    candidates.extend(
        [
            WORKSPACE_ROOT / ".venvs" / "ai-manga-factory" / "Scripts" / "python.exe",
            ROOT / ".venv" / "Scripts" / "python.exe",
            ROOT / ".venv" / "bin" / "python",
        ]
    )
    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        if candidate.exists():
            return normalized
    for command in ("python3", "python"):
        resolved = shutil.which(command)
        if resolved:
            return resolved
    raise RuntimeError("Python executable not found. Set AI_MANGA_FACTORY_PYTHON or create a local venv.")


def resolve_npm() -> str:
    for command in ("npm", "npm.cmd"):
        resolved = shutil.which(command)
        if resolved:
            return resolved
    raise RuntimeError("npm executable not found. Install Node.js or add npm to PATH.")


def resolve_node() -> str:
    for command in ("node", "node.exe"):
        resolved = shutil.which(command)
        if resolved:
            return resolved
    raise RuntimeError("node executable not found. Install Node.js or add node to PATH.")


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> int:
    process = subprocess.run(command, cwd=str(cwd), env=env, check=False)
    return int(process.returncode)


def spawn(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.Popen[str]:
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    return subprocess.Popen(command, cwd=str(cwd), env=env, creationflags=creationflags)


def wait_for_health(base_url: str, timeout_seconds: int) -> bool:
    return wait_for_runtime_consistency(base_url, timeout_seconds)


def cmd_backend(args: argparse.Namespace) -> int:
    python = resolve_python()
    host = args.host or os.environ.get("AI_MANGA_FACTORY_HOST", "127.0.0.1")
    port = str(args.port or os.environ.get("AI_MANGA_FACTORY_PORT", "8000"))
    command = [python, "-m", "uvicorn", "backend.main:app", "--host", host, "--port", port]
    command.extend(args.extra)
    return run(command, cwd=ROOT)


def cmd_web(args: argparse.Namespace) -> int:
    npm = resolve_npm()
    env = os.environ.copy()
    if args.api_base:
        env["VITE_API_BASE_URL"] = args.api_base
    command = [npm, "run", "dev"]
    if args.host:
        command.extend(["--", "--host", args.host, "--port", str(args.port)])
    return run(command, cwd=WEB_ROOT, env=env)


def cmd_build_web(_: argparse.Namespace) -> int:
    npm = resolve_npm()
    return run([npm, "run", "build"], cwd=WEB_ROOT)


def cmd_health(args: argparse.Namespace) -> int:
    report = check_runtime_consistency(args.base_url)
    print_runtime_consistency(report)
    return 0 if bool(report.get("ok")) else 1


def cmd_verify_deploy(args: argparse.Namespace) -> int:
    return cmd_health(args)


def cmd_sync_storage(args: argparse.Namespace) -> int:
    python = resolve_python()
    command = [python, str(ROOT / "scripts" / "sync_runtime_storage.py")]
    if args.provider:
        command.extend(["--provider", args.provider])
    if args.dry_run:
        command.append("--dry-run")
    for job_id in args.job_id:
        command.extend(["--job-id", str(job_id)])
    return run(command, cwd=ROOT)


def cmd_auth_storage(args: argparse.Namespace) -> int:
    python = resolve_python()
    command = [python, str(ROOT / "scripts" / "auth_remote_storage.py"), "--provider", args.provider]
    if args.prepare_qr:
        command.append("--prepare-qr")
    return run(command, cwd=ROOT)


def cmd_smoke_browser(args: argparse.Namespace) -> int:
    report = check_runtime_consistency(args.app_url)
    print_runtime_consistency(report)
    if not bool(report.get("ok")):
        return 1

    node = resolve_node()
    env = os.environ.copy()
    env["AMF_APP_URL"] = args.app_url
    if args.pack_name:
        env["AMF_PACK_NAME"] = args.pack_name
    if args.project_name:
        env["AMF_PROJECT_NAME"] = args.project_name
    if args.scene_count is not None:
        env["AMF_SCENE_COUNT"] = str(args.scene_count)
    if args.chapter_start is not None:
        env["AMF_CHAPTER_START"] = str(args.chapter_start)
    if args.chapter_end is not None:
        env["AMF_CHAPTER_END"] = str(args.chapter_end)
    if args.target_duration_seconds is not None:
        env["AMF_TARGET_DURATION_SECONDS"] = str(args.target_duration_seconds)
    if args.output_dir:
        env["AMF_OUTPUT_DIR"] = args.output_dir
    if args.timeout_ms is not None:
        env["AMF_TIMEOUT_MS"] = str(args.timeout_ms)

    return run([node, str(SMOKE_SCRIPT)], cwd=ROOT, env=env)


def cmd_all(args: argparse.Namespace) -> int:
    python = resolve_python()
    npm = resolve_npm()
    backend_host = args.backend_host or os.environ.get("AI_MANGA_FACTORY_HOST", "127.0.0.1")
    backend_port = str(args.backend_port or os.environ.get("AI_MANGA_FACTORY_PORT", "8000"))
    web_host = args.web_host or os.environ.get("AI_MANGA_FACTORY_WEB_HOST", "127.0.0.1")
    web_port = str(args.web_port or os.environ.get("AI_MANGA_FACTORY_WEB_PORT", "5173"))
    api_base = args.api_base or f"http://{backend_host}:{backend_port}"

    backend = spawn([python, "-m", "uvicorn", "backend.main:app", "--host", backend_host, "--port", backend_port], cwd=ROOT)
    try:
        if not wait_for_runtime_consistency(api_base, timeout_seconds=args.health_timeout):
            backend.terminate()
            return 1
        env = os.environ.copy()
        env["VITE_API_BASE_URL"] = api_base
        web = spawn([npm, "run", "dev", "--", "--host", web_host, "--port", web_port], cwd=WEB_ROOT, env=env)
        try:
            print(f"[backend] {api_base}")
            print(f"[web] http://{web_host}:{web_port}")
            while True:
                if backend.poll() is not None:
                    return int(backend.returncode or 0)
                if web.poll() is not None:
                    return int(web.returncode or 0)
                time.sleep(1)
        finally:
            if web.poll() is None:
                web.terminate()
                web.wait(timeout=10)
    finally:
        if backend.poll() is None:
            backend.terminate()
            backend.wait(timeout=10)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI Manga Factory cross-platform launcher")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backend = subparsers.add_parser("backend", help="start FastAPI backend")
    backend.add_argument("--host", default=None)
    backend.add_argument("--port", type=int, default=None)
    backend.add_argument("extra", nargs=argparse.REMAINDER)
    backend.set_defaults(func=cmd_backend)

    web = subparsers.add_parser("web", help="start Vite frontend")
    web.add_argument("--host", default=None)
    web.add_argument("--port", type=int, default=5173)
    web.add_argument("--api-base", default=None)
    web.set_defaults(func=cmd_web)

    build_web = subparsers.add_parser("build-web", help="build Vite frontend")
    build_web.set_defaults(func=cmd_build_web)

    health = subparsers.add_parser("health", help="check key HTTP endpoints and OpenAPI consistency")
    health.add_argument("--base-url", default="http://127.0.0.1:8000")
    health.set_defaults(func=cmd_health)

    verify_deploy = subparsers.add_parser("verify-deploy", help="alias for health")
    verify_deploy.add_argument("--base-url", default="http://127.0.0.1:8000")
    verify_deploy.set_defaults(func=cmd_verify_deploy)

    sync_storage = subparsers.add_parser("sync-storage", help="sync business outputs to configured remote storage")
    sync_storage.add_argument("--provider", default=None)
    sync_storage.add_argument("--dry-run", action="store_true")
    sync_storage.add_argument("--job-id", action="append", default=[])
    sync_storage.set_defaults(func=cmd_sync_storage)

    auth_storage = subparsers.add_parser("auth-storage", help="authenticate remote storage provider")
    auth_storage.add_argument("--provider", required=True)
    auth_storage.add_argument("--prepare-qr", action="store_true")
    auth_storage.set_defaults(func=cmd_auth_storage)

    smoke_browser = subparsers.add_parser("smoke-browser", help="run the low-dependency browser smoke entry")
    smoke_browser.add_argument("--app-url", default="http://127.0.0.1:8000")
    smoke_browser.add_argument("--pack-name", default=None)
    smoke_browser.add_argument("--project-name", default=None)
    smoke_browser.add_argument("--scene-count", type=int, default=None)
    smoke_browser.add_argument("--chapter-start", type=int, default=None)
    smoke_browser.add_argument("--chapter-end", type=int, default=None)
    smoke_browser.add_argument("--target-duration-seconds", type=int, default=None)
    smoke_browser.add_argument("--output-dir", default=None)
    smoke_browser.add_argument("--timeout-ms", type=int, default=None)
    smoke_browser.set_defaults(func=cmd_smoke_browser)

    smoke = subparsers.add_parser("smoke", help="alias for smoke-browser")
    smoke.add_argument("--app-url", default="http://127.0.0.1:8000")
    smoke.add_argument("--pack-name", default=None)
    smoke.add_argument("--project-name", default=None)
    smoke.add_argument("--scene-count", type=int, default=None)
    smoke.add_argument("--chapter-start", type=int, default=None)
    smoke.add_argument("--chapter-end", type=int, default=None)
    smoke.add_argument("--target-duration-seconds", type=int, default=None)
    smoke.add_argument("--output-dir", default=None)
    smoke.add_argument("--timeout-ms", type=int, default=None)
    smoke.set_defaults(func=cmd_smoke_browser)

    all_in_one = subparsers.add_parser("all", help="start backend and frontend together")
    all_in_one.add_argument("--backend-host", default=None)
    all_in_one.add_argument("--backend-port", type=int, default=8000)
    all_in_one.add_argument("--web-host", default=None)
    all_in_one.add_argument("--web-port", type=int, default=5173)
    all_in_one.add_argument("--api-base", default=None)
    all_in_one.add_argument("--health-timeout", type=int, default=30)
    all_in_one.set_defaults(func=cmd_all)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
