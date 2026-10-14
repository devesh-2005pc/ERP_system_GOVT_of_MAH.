# Deployment

## Overview

One office computer (or a small server) runs the Mudranalaya backend and
PostgreSQL database - this is the "central office server." Every other
department's computer is just a **web browser** pointed at that machine's
IP address on the office LAN. There is nothing to install on the client
computers.

```
CENTRAL SERVER (e.g. Manager's PC or a small server)
  - PostgreSQL running locally
  - Mudranalaya.exe running (listens on 0.0.0.0:8000)

CLIENT PCs (Store, Planning, Dispatch, Accounts, other Manager PCs)
  - Just a browser, e.g. http://192.168.1.10:8000
```

## 1. Building the Windows `.exe`

**This must be done on a Windows machine** (or a Windows CI runner) -
PyInstaller builds a native executable for whatever OS it runs on, so
building on Linux (as this project's automated build/test pass did, to
verify the packaging mechanics) produces a Linux binary, not a `.exe`. The
spec file and entry point are OS-agnostic and were tested end-to-end in
this environment; the actual Windows binary must be produced on Windows.

```powershell
cd mudranalaya
python -m venv venv
venv\Scripts\activate
pip install -r backend\requirements.txt
pip install psycopg2-binary   # only if deploying against PostgreSQL
pip install pyinstaller
pyinstaller mudranalaya.spec
```

Output: `dist\Mudranalaya\Mudranalaya.exe` plus its `_internal` folder -
**copy the whole `dist\Mudranalaya` folder** to the target machine, not just
the `.exe` file alone.

## 2. Installing the central server

1. Install PostgreSQL on the server machine (or use SQLite for a very small
   single-PC pilot - not recommended for real multi-workstation use, see
   `DATABASE.md`).
2. Create a database and a dedicated low-privilege user:
   ```sql
   CREATE DATABASE mudranalaya_erp;
   CREATE USER erp_user WITH PASSWORD 'CHANGE_ME_STRONG_PASSWORD';
   GRANT ALL PRIVILEGES ON DATABASE mudranalaya_erp TO erp_user;
   ```
3. Copy the `dist\Mudranalaya` folder to the server, e.g.
   `C:\Mudranalaya\`.
4. Create `C:\Mudranalaya\.env` (next to the exe) with, at minimum:
   ```
   ENVIRONMENT=production
   DATABASE_URL=postgresql+psycopg2://erp_user:CHANGE_ME_STRONG_PASSWORD@127.0.0.1:5432/mudranalaya_erp
   JWT_SECRET_KEY=<output of: python -c "import secrets; print(secrets.token_urlsafe(64))">
   CORS_ALLOWED_ORIGINS=http://192.168.1.10:8000,http://localhost:8000
   ```
   Replace `192.168.1.10` with the server's actual LAN IP, and add every
   other origin client browsers will use.
5. Run `Mudranalaya.exe` once. It will create the database schema
   automatically on first start (see the Alembic caveat in `DATABASE.md`
   for future schema *changes*).
6. Create the first Manager account (do **not** use the demo seed script in
   production):
   ```powershell
   python scripts\create_first_manager.py
   ```
7. (Optional, but recommended) Register `Mudranalaya.exe` as a Windows
   service (via NSSM or Task Scheduler "run at startup") so it survives
   reboots without someone double-clicking it.

## 3. License activation

1. On a separate, trusted machine (never on the office server), run once:
   ```
   python scripts/generate_license_keys.py --out-dir ./keys
   ```
   Keep `keys/private_key.pem` secret and off any office machine.
2. Copy `keys/public_key.pem` to
   `C:\Mudranalaya\data\license\public_key.pem` on the server *before*
   packaging/deploying (or drop it in after - the app reads it at request
   time).
3. Start the server and log in as Manager → **License & Devices** → note
   the device fingerprint shown.
4. On the trusted machine, issue a license:
   ```
   python scripts/issue_license.py --private-key ./keys/private_key.pem \
     --office-name "Your Press Name" --device-fingerprint <fingerprint> \
     --max-devices 10 --valid-days 365 --out license_token.json
   ```
5. Copy `license_token.json` to
   `C:\Mudranalaya\data\license\license_token.json` on the server.
6. In the app, Manager → License & Devices → **Activate This Device**.

## 4. Connecting client computers

No installation needed. On each department's PC, open a browser to
`http://<server-LAN-IP>:8000` and log in with the credentials the Manager
created for that department (Manager → Users → + New User).

## 5. Backups

```powershell
python scripts\backup.py
```

Writes a timestamped backup to `BACKUP_DIR` (defaults to
`data\backups\`). Schedule this via **Windows Task Scheduler** (e.g. daily
at 2 AM) - see `SECURITY.md`/`ARCHITECTURE.md` for why this isn't yet
automatic inside the app itself.

To restore (only from a machine with physical/administrative access to the
server - this is intentionally not exposed over the web UI):
```powershell
python scripts\restore.py --backup-file data\backups\mudranalaya_20260101_020000.db
```

## 6. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Other PCs can't reach the server | Windows Firewall blocking port 8000 - add an inbound rule for TCP 8000 |
| "Refusing to start in production with the default JWT_SECRET_KEY" | Set a real `JWT_SECRET_KEY` in `.env` |
| Login works but every action gives 403 | Check the user's department assignment (Manager → Users) |
| Stock numbers look wrong after a power cut | Check `data\backups\` for the most recent backup and consider restoring; the ledger design means the transaction history in `inventory_transactions` is the source of truth for reconciliation |
