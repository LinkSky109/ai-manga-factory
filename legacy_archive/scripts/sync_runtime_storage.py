from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import DATA_DIR, RUNTIME_STORAGE_PLAN
from shared.aliyun_pan_sync import REPORT_FILE as ALIYUN_REPORT_FILE
from shared.aliyun_pan_sync import sync_business_outputs_to_aliyundrive
from shared.quark_pan_sync import REPORT_FILE, sync_business_outputs_to_quark
from shared.runtime_storage import load_runtime_storage_config


def _iter_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file():
            yield path


def _sync_to_aliyun_oss(config: dict) -> int:
    try:
        import oss2  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("缺少 oss2，请先安装 requirements-storage.txt") from exc

    endpoint = str(config.get("endpoint", "")).strip()
    bucket_name = str(config.get("bucket", "")).strip()
    prefix = str(config.get("prefix", "ai-manga-factory/runtime")).strip().strip("/")
    key_id = os.getenv(str(config.get("access_key_id_env", "AI_MANGA_FACTORY_OSS_ACCESS_KEY_ID")).strip(), "")
    key_secret = os.getenv(str(config.get("access_key_secret_env", "AI_MANGA_FACTORY_OSS_ACCESS_KEY_SECRET")).strip(), "")

    if not endpoint or not bucket_name or not key_id or not key_secret:
        raise RuntimeError("OSS 配置不完整：需要 endpoint、bucket 和 access key 环境变量")

    auth = oss2.Auth(key_id, key_secret)
    bucket = oss2.Bucket(auth, endpoint, bucket_name)

    uploaded = 0
    for file_path in _iter_files(DATA_DIR):
        relative = file_path.relative_to(DATA_DIR).as_posix()
        object_name = f"{prefix}/{relative}" if prefix else relative
        bucket.put_object_from_file(object_name, str(file_path))
        uploaded += 1
        print(f"[upload] {relative} -> oss://{bucket_name}/{object_name}")
    print(f"[done] uploaded={uploaded} runtime_root={DATA_DIR}")
    return 0


def _parse_job_ids(raw_values: list[str]) -> set[int]:
    results: set[int] = set()
    for raw in raw_values:
        for item in raw.split(","):
            value = item.strip()
            if not value:
                continue
            results.add(int(value))
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync AI Manga Factory runtime or business outputs to remote storage")
    parser.add_argument("--provider", default=None, help="override remote sync provider, e.g. aliyun_oss or quark_pan")
    parser.add_argument("--dry-run", action="store_true", help="only print/upload plan without real upload")
    parser.add_argument("--job-id", action="append", default=[], help="only sync specified job ids, supports repeated use or comma-separated values")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    config = load_runtime_storage_config(RUNTIME_STORAGE_PLAN.config_path)
    remote_sync = config.get("remote_sync", {})
    provider = str(args.provider or remote_sync.get("provider", "")).strip()

    if not provider:
        raise RuntimeError("未指定远程同步 provider，请在配置中设置 remote_sync.provider 或使用 --provider")

    if provider == "aliyun_oss":
        if not bool(remote_sync.get("enabled", False)) and not args.provider:
            print("[skip] remote_sync 未启用")
            return 0
        return _sync_to_aliyun_oss(remote_sync.get("aliyun_oss", {}))

    if provider == "quark_pan":
        job_ids = _parse_job_ids(args.job_id)
        report = sync_business_outputs_to_quark(
            config=remote_sync.get("quark_pan", {}),
            dry_run=bool(args.dry_run),
            job_ids=job_ids or None,
        )
        print(
            {
                "provider": report.get("provider"),
                "dry_run": report.get("dry_run"),
                "planned": report.get("planned"),
                "pending": report.get("pending"),
                "uploaded": len(report.get("uploaded", [])),
                "skipped": len(report.get("skipped", [])),
                "report_path": str(REPORT_FILE),
            }
        )
        return 0

    if provider == "aliyundrive":
        job_ids = _parse_job_ids(args.job_id)
        report = sync_business_outputs_to_aliyundrive(
            config=remote_sync.get("aliyundrive", {}),
            dry_run=bool(args.dry_run),
            job_ids=job_ids or None,
        )
        print(
            {
                "provider": report.get("provider"),
                "dry_run": report.get("dry_run"),
                "planned": report.get("planned"),
                "pending": report.get("pending"),
                "uploaded": len(report.get("uploaded", [])),
                "skipped": len(report.get("skipped", [])),
                "report_path": str(ALIYUN_REPORT_FILE),
            }
        )
        return 0

    raise RuntimeError(f"当前远程存储后端 {provider!r} 尚未接入")


if __name__ == "__main__":
    raise SystemExit(main())
