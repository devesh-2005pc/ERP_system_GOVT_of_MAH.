#!/usr/bin/env python3
"""
Offline license issuing tool.

Run this ONLY on a trusted machine that holds the private signing key
(generated once via generate_keys.py and kept OFF any office computer and
OFF the application repository/build). It produces a signed license_token.json
that you hand to the customer office, who places it wherever
LICENSE_TOKEN_PATH points to (see app/core/config.py) and restarts the server.

Usage:
    python scripts/issue_license.py \\
        --private-key ./keys/private_key.pem \\
        --office-name "Shasakiya Mudranalaya - Nashik Division" \\
        --device-fingerprint <fingerprint from the office's first-run screen> \\
        --max-devices 10 \\
        --valid-days 365 \\
        --out license_token.json
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.licensing.tokens import load_private_key, sign_license  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--key-password", default=None)
    parser.add_argument("--office-name", required=True)
    parser.add_argument("--device-fingerprint", required=True)
    parser.add_argument("--license-key", default=None, help="human-readable key printed on the invoice; auto-generated if omitted")
    parser.add_argument("--max-devices", type=int, default=1)
    parser.add_argument("--valid-days", type=int, default=365)
    parser.add_argument("--out", default="license_token.json")
    args = parser.parse_args()

    private_key = load_private_key(args.private_key, args.key_password.encode() if args.key_password else None)

    now = datetime.now(timezone.utc)
    license_key = args.license_key or f"MUDRA-{now.strftime('%Y%m')}-{args.device_fingerprint[:8].upper()}"
    payload = {
        "license_key": license_key,
        "office_name": args.office_name,
        "device_fingerprint": args.device_fingerprint,
        "max_devices": args.max_devices,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(days=args.valid_days)).isoformat(),
    }
    token = sign_license(private_key, payload)
    Path(args.out).write_text(json.dumps(token, indent=2))
    print(f"License issued -> {args.out}")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
