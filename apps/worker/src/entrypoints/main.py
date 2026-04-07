import argparse
from pathlib import Path
import sys
from time import sleep
from uuid import uuid4


def _bootstrap_api_package() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    api_root = repo_root / "apps" / "api"
    if str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI Manga Factory async worker")
    parser.add_argument("--once", action="store_true", help="Consume a single queued job and exit.")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Seconds to wait between queue polls when no work is available.",
    )
    parser.add_argument(
        "--worker-id",
        default=f"worker-{uuid4().hex[:8]}",
        help="Stable worker identifier used for queue claims.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    _bootstrap_api_package()

    from src.application.services.archive_sync_runner import ArchiveSyncRunner
    from src.application.services.async_job_runner import AsyncJobRunner
    from src.infrastructure.db.base import get_session_factory, init_database
    from src.infrastructure.db.repositories.monitoring_repository import MonitoringRepository
    from src.infrastructure.db.repositories.provider_repository import ProviderRepository

    def seed_defaults(session) -> None:
        ProviderRepository(session).seed_defaults()

    def write_heartbeat(*, status: str, last_job_id: int | None = None, detail: dict | None = None) -> None:
        session = get_session_factory()()
        try:
            seed_defaults(session)
            MonitoringRepository(session).record_worker_heartbeat(
                worker_id=args.worker_id,
                worker_type="hybrid",
                status=status,
                last_job_id=last_job_id,
                detail=detail,
            )
            session.commit()
        finally:
            session.close()

    init_database()
    runner = AsyncJobRunner(
        session_factory=get_session_factory(),
        worker_id=args.worker_id,
        session_initializer=seed_defaults,
    )
    archive_runner = ArchiveSyncRunner(
        session_factory=get_session_factory(),
        worker_id=f"{args.worker_id}-archive",
        session_initializer=seed_defaults,
    )

    print(f"[worker] AI Manga Factory worker started as {args.worker_id}")
    write_heartbeat(status="idle")

    while True:
        consumed_job_id = runner.consume_next()
        if consumed_job_id is not None:
            write_heartbeat(status="busy", last_job_id=consumed_job_id, detail={"last_task_type": "job"})
            print(f"[worker] consumed async job #{consumed_job_id}")
        else:
            consumed_sync_run_id = archive_runner.consume_next()
            if consumed_sync_run_id is not None:
                write_heartbeat(
                    status="busy",
                    detail={"last_task_type": "archive_sync", "last_archive_sync_run_id": consumed_sync_run_id},
                )
                print(f"[worker] consumed archive sync run #{consumed_sync_run_id}")
                continue
            write_heartbeat(status="idle")
            if args.once:
                write_heartbeat(status="stopped")
                print("[worker] no queued async jobs or archive sync runs found")
                return
            sleep(args.poll_interval)


if __name__ == "__main__":
    main()
