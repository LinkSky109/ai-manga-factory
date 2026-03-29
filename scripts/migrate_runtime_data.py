from __future__ import annotations

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import DATA_DIR, ROOT_DIR


LEGACY_DATA_DIR = ROOT_DIR / "data"
RUNTIME_ITEMS = [
    "artifacts",
    "provider_usage",
    "requirements",
    "source_sessions",
    "platform.db",
    "backend.log",
    "backend-error.log",
    "provider_test_i2v.mp4",
]


def _copy_path(source: Path, target: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def main() -> int:
    if LEGACY_DATA_DIR.resolve() == DATA_DIR.resolve():
        print(f"[skip] 运行时目录仍在项目内：{DATA_DIR}")
        return 0

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    migrated = 0
    skipped = 0

    for name in RUNTIME_ITEMS:
        source = LEGACY_DATA_DIR / name
        if not source.exists():
            skipped += 1
            continue
        target = DATA_DIR / name
        _copy_path(source, target)
        migrated += 1
        print(f"[copy] {source} -> {target}")

    print(f"[done] migrated={migrated} skipped={skipped} runtime_root={DATA_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
