"""
Device fingerprint generation.

Combines several machine-identifying values into a stable hash. No single
value is perfectly unforgeable (this is stated plainly in the project's
security docs — client-side protection is never absolute) but combining
several raises the bar for casual copying of an install to another machine.
"""
import hashlib
import platform
import subprocess
import uuid


def _safe(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=3).decode().strip()
    except Exception:
        return ""


def get_machine_guid_windows() -> str:
    """On Windows, read the stable per-install MachineGuid from the registry."""
    if platform.system() != "Windows":
        return ""
    try:
        import winreg  # type: ignore
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
        value, _ = winreg.QueryValueEx(key, "MachineGuid")
        return value
    except Exception:
        return ""


def compute_fingerprint() -> str:
    parts = [
        platform.node(),                     # computer name
        platform.system(),
        platform.machine(),
        str(uuid.getnode()),                 # MAC-derived node id
        get_machine_guid_windows(),
    ]
    raw = "|".join(p for p in parts if p)
    return hashlib.sha256(raw.encode()).hexdigest()


def get_computer_name() -> str:
    return platform.node()
