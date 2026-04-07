from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_ROOT = PROJECT_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.core.config import get_settings, reset_settings_cache
from src.infrastructure.storage.remote_storage_clients import (
    build_aliyundrive_remote_uploader,
    build_quark_pan_remote_uploader,
)


def _auth_quark(*, prepare_qr: bool) -> int:
    settings = get_settings()

    if prepare_qr:
        from quark_client.auth.api_login import APILogin  # type: ignore

        out_dir = PROJECT_ROOT / "data" / "verification" / "auth"
        out_dir.mkdir(parents=True, exist_ok=True)
        login = APILogin(timeout=300)
        qr_token, qr_url = login.get_qr_code()
        payload = {
            "provider": "quark-pan",
            "qr_token": qr_token,
            "qr_url": qr_url,
        }
        try:
            import qrcode  # type: ignore

            qr_path = out_dir / "quark-login-qr.png"
            qrcode.make(qr_url).save(qr_path)
            payload["qr_path"] = str(qr_path)
        except ImportError:
            payload["qr_path"] = None

        (out_dir / "quark-login-qr.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    build_quark_pan_remote_uploader(settings, interactive_login=True)
    cookie_file = settings.quark_pan_cookie_file
    print(
        json.dumps(
            {
                "provider": "quark-pan",
                "status": "ok",
                "cookie_file": str(cookie_file),
                "config_dir": str(settings.quark_pan_config_dir),
            },
            ensure_ascii=False,
        )
    )
    return 0


def _auth_aliyundrive() -> int:
    settings = get_settings()
    build_aliyundrive_remote_uploader(settings, interactive_login=True)
    print(
        json.dumps(
            {
                "provider": "aliyundrive",
                "status": "ok",
                "config_dir": str(settings.aliyundrive_config_dir),
                "name": settings.aliyundrive_name,
            },
            ensure_ascii=False,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Authenticate remote storage providers")
    parser.add_argument("--provider", required=True, choices=["quark-pan", "aliyundrive"])
    parser.add_argument(
        "--prepare-qr",
        action="store_true",
        help="Only prepare Quark QR metadata without completing login.",
    )
    return parser


def main() -> int:
    reset_settings_cache()
    args = build_parser().parse_args()
    if args.provider == "quark-pan":
        return _auth_quark(prepare_qr=bool(args.prepare_qr))
    if args.provider == "aliyundrive":
        return _auth_aliyundrive()
    raise RuntimeError(f"Unsupported provider: {args.provider}")


if __name__ == "__main__":
    raise SystemExit(main())
