from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.aliyun_pan_sync import build_aliyun_sync_config
from shared.quark_pan_sync import build_quark_sync_config


def _auth_quark(*, prepare_qr: bool) -> int:
    from quark_client.auth.api_login import APILogin

    config = build_quark_sync_config()
    if prepare_qr:
        import qrcode

        out_dir = PROJECT_ROOT.parent.parent / "management" / "ai-manga-factory" / "verification" / "auth"
        out_dir.mkdir(parents=True, exist_ok=True)
        login = APILogin(timeout=300)
        qr_token, qr_url = login.get_qr_code()
        qr_path = out_dir / "quark-login-qr.png"
        qrcode.make(qr_url).save(qr_path)
        payload = {
            "provider": "quark_pan",
            "qr_token": qr_token,
            "qr_url": qr_url,
            "qr_path": str(qr_path),
        }
        (out_dir / "quark-login-qr.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    from shared.quark_pan_sync import _create_client  # noqa: PLC2701

    client = _create_client(config)
    storage = client.get_storage_info()
    print(json.dumps({"provider": "quark_pan", "status": "ok", "storage": storage}, ensure_ascii=False))
    return 0


def _auth_aliyun() -> int:
    from aligo import Aligo
    from aligo.core import set_config_folder

    config = build_aliyun_sync_config()
    config_dir = Path(config["config_dir"])
    config_dir.mkdir(parents=True, exist_ok=True)
    set_config_folder(str(config_dir))
    ali = Aligo(name=str(config["name"]), re_login=True)
    drive = ali.get_drive()
    personal = ali.get_personal_info()
    print(
        json.dumps(
            {
                "provider": "aliyundrive",
                "status": "ok",
                "default_drive_id": getattr(drive, "default_drive_id", None),
                "user_name": getattr(personal, "nick_name", None),
            },
            ensure_ascii=False,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Authenticate remote storage providers")
    parser.add_argument("--provider", required=True, choices=["quark_pan", "aliyundrive"])
    parser.add_argument("--prepare-qr", action="store_true", help="only prepare Quark QR image without waiting for login")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.provider == "quark_pan":
        return _auth_quark(prepare_qr=bool(args.prepare_qr))
    if args.provider == "aliyundrive":
        return _auth_aliyun()
    raise RuntimeError(f"unsupported provider: {args.provider}")


if __name__ == "__main__":
    raise SystemExit(main())
