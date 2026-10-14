"""
Entry point for the PyInstaller-built Windows executable.

This is what actually runs when an office double-clicks Mudranalaya.exe.
It launches the FastAPI backend (Uvicorn, embedded, no separate install)
and opens the default browser pointed at it. The frontend (HTML/CSS/JS)
is bundled as static files inside the exe and served by the same process,
so there is nothing else to install on the machine.

First-run behaviour:
  - If no database file exists yet, it is created automatically (SQLite by
    default for a single-office/single-server deployment; point DATABASE_URL
    at PostgreSQL for a proper multi-workstation office deployment - see
    docs/DEPLOYMENT.md).
  - If no Manager user exists yet, the console prints instructions to run
    scripts/create_first_manager.py once (kept as a separate deliberate step
    rather than a hardcoded default account, per the project's security
    requirements).
"""
import os
import sys
import threading
import time
import webbrowser

import uvicorn


def resource_path(relative_path: str) -> str:
    """Resolve a path that works both when run from source and when frozen
    into a PyInstaller onefile executable (which unpacks to sys._MEIPASS)."""
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def _launch_browser(url: str, delay_seconds: float = 1.5):
    time.sleep(delay_seconds)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main():
    # Ensure a writable data directory next to the executable (not inside
    # the read-only PyInstaller bundle) for the database, uploads, backups,
    # and license files.
    app_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    data_dir = os.path.join(app_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(data_dir, 'mudranalaya.db')}")
    os.environ.setdefault("BACKUP_DIR", os.path.join(data_dir, "backups"))
    os.environ.setdefault("UPLOAD_DIR", os.path.join(data_dir, "uploads"))
    os.environ.setdefault("LICENSE_PUBLIC_KEY_PATH", os.path.join(data_dir, "license", "public_key.pem"))
    os.environ.setdefault("LICENSE_TOKEN_PATH", os.path.join(data_dir, "license", "license_token.json"))

    host = os.environ.get("MUDRANALAYA_HOST", "0.0.0.0")  # listen on the office LAN, not just localhost
    port = int(os.environ.get("MUDRANALAYA_PORT", "8000"))

    print(f"Mudranalaya ERP-MIS starting on http://{host}:{port}")
    print("Other office computers should browse to this machine's IP address, e.g. http://192.168.1.10:8000")
    print("Press Ctrl+C in this window to stop the server.")

    threading.Thread(target=_launch_browser, args=(f"http://127.0.0.1:{port}",), daemon=True).start()

    sys.path.insert(0, resource_path("backend"))
    from app.main import app  # imported here so env vars above take effect first

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
