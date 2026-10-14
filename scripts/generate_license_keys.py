#!/usr/bin/env python3
"""
Run ONCE, on a trusted machine, to create the license signing keypair.

- private_key.pem: keep this OFF every office computer and OFF the
  application build entirely. Store it somewhere secure (encrypted vault,
  offline USB drive). This is what lets you issue new licenses.
- public_key.pem: this ships INSIDE the application (backend/data/license/
  public_key.pem) so the app can verify licenses but never mint new ones.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.licensing.tokens import generate_keypair, save_private_key, save_public_key  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="./keys")
    parser.add_argument("--password", default=None, help="optional password to encrypt the private key file")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    private_key, public_key = generate_keypair()
    save_private_key(private_key, str(out_dir / "private_key.pem"), args.password.encode() if args.password else None)
    save_public_key(public_key, str(out_dir / "public_key.pem"))

    print(f"Keys written to {out_dir}/")
    print("  private_key.pem  -> KEEP SECRET, off any office machine")
    print("  public_key.pem   -> copy into backend/data/license/public_key.pem before packaging the app")


if __name__ == "__main__":
    main()
