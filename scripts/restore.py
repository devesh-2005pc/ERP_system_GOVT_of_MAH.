#!/usr/bin/env python3
"""
Database restore script. Deliberately a manual, offline, command-line-only
operation (not exposed over the API to any role, including Manager) so that
restoring the database always requires physical/administrative access to the
server machine - never something that can be triggered remotely by a
compromised web session.

Usage:
    python scripts/restore.py --backup-file ./data/backups/mudranalaya_20260101_020000.db
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.core.config import get_settings  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-file", required=True)
    parser.add_argument("--yes", action="store_true", help="skip the interactive confirmation prompt")
    args = parser.parse_args()

    settings = get_settings()
    print(f"About to restore into: {settings.DATABASE_URL}")
    print(f"From backup file:      {args.backup_file}")
    print("THIS WILL OVERWRITE ALL CURRENT DATA.")
    if not args.yes:
        confirm = input("Type RESTORE to proceed: ")
        if confirm != "RESTORE":
            print("Aborted.")
            return

    if settings.DATABASE_URL.startswith("sqlite"):
        db_path = settings.DATABASE_URL.replace("sqlite:///", "")
        shutil.copy2(args.backup_file, db_path)
        print("SQLite database restored.")
        return

    if settings.DATABASE_URL.startswith("postgresql"):
        parsed = urlparse(settings.DATABASE_URL.replace("+psycopg2", ""))
        cmd = [
            "psql", "-h", parsed.hostname or "localhost", "-p", str(parsed.port or 5432),
            "-U", parsed.username or "postgres", "-d", parsed.path.lstrip("/"),
            "-f", args.backup_file,
        ]
        subprocess.run(cmd, check=True)
        print("PostgreSQL database restored.")
        return

    raise RuntimeError(f"Unsupported DATABASE_URL scheme for restore: {settings.DATABASE_URL}")


if __name__ == "__main__":
    main()
