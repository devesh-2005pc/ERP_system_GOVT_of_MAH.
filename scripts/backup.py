#!/usr/bin/env python3
"""
Database backup script. Supports both backends:
  - SQLite (dev / small single-server deployments): file copy with a
    timestamped name, safe to run while the app is running because SQLite
    keeps a consistent on-disk file between transactions.
  - PostgreSQL (recommended production backend): shells out to pg_dump.

Run manually, or schedule via Windows Task Scheduler / cron:
    python scripts/backup.py
"""
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.core.config import get_settings  # noqa: E402


def backup():
    settings = get_settings()
    backup_dir = Path(settings.BACKUP_DIR)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if settings.DATABASE_URL.startswith("sqlite"):
        db_path = settings.DATABASE_URL.replace("sqlite:///", "")
        dest = backup_dir / f"mudranalaya_{timestamp}.db"
        shutil.copy2(db_path, dest)
        print(f"SQLite backup written to {dest}")
        return str(dest)

    if settings.DATABASE_URL.startswith("postgresql"):
        parsed = urlparse(settings.DATABASE_URL.replace("+psycopg2", ""))
        dest = backup_dir / f"mudranalaya_{timestamp}.sql"
        env = os.environ.copy()
        if parsed.password:
            env["PGPASSWORD"] = parsed.password
        cmd = [
            "pg_dump", "-h", parsed.hostname or "localhost", "-p", str(parsed.port or 5432),
            "-U", parsed.username or "postgres", "-d", parsed.path.lstrip("/"),
            "-f", str(dest),
        ]
        subprocess.run(cmd, env=env, check=True)
        print(f"PostgreSQL backup written to {dest}")
        return str(dest)

    raise RuntimeError(f"Unsupported DATABASE_URL scheme for backup: {settings.DATABASE_URL}")


if __name__ == "__main__":
    backup()
