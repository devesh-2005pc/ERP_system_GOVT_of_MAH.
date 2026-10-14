# Mudranalaya ERP-MIS: Windows Local Deployment Guide

This guide provides instructions for deploying the Mudranalaya ERP-MIS application on a local Windows server. The application is designed to be accessible across the local area network (LAN) by various departments in the printing press.

## Prerequisites

1.  **Windows Server (or Windows 10/11 Pro)**: The machine that will host the application.
2.  **PostgreSQL (version 13 or later)**: Relational database for the backend.
3.  **Python 3.10+**: Runtime for the FastAPI backend and simple frontend HTTP server.

---

## 1. PostgreSQL Database Setup

1.  Download the PostgreSQL Windows installer from the [official website](https://www.postgresql.org/download/windows/).
2.  Run the installer. Remember the **postgres** user password you set during installation.
3.  Open the **pgAdmin 4** tool (installed alongside PostgreSQL) or use the `psql` command line tool.
4.  Create a new database named `mudranalaya_db`:
    ```sql
    CREATE DATABASE mudranalaya_db;
    ```
5.  *(Optional but recommended)* Create a dedicated user for the application:
    ```sql
    CREATE USER mudranalaya_user WITH ENCRYPTED PASSWORD 'your_secure_password';
    GRANT ALL PRIVILEGES ON DATABASE mudranalaya_db TO mudranalaya_user;
    ```

---

## 2. Python Setup & Environment Configuration

1.  Download the latest Python installer from [python.org](https://www.python.org/downloads/windows/).
2.  Run the installer. **CRITICAL:** Check the box that says **"Add Python to PATH"** before clicking Install.
3.  Open a PowerShell terminal and verify the installation:
    ```powershell
    python --version
    ```
4.  Navigate to the `mudranalaya/backend` directory:
    ```powershell
    cd path\to\mudranalaya\backend
    ```
5.  Create a virtual environment and activate it:
    ```powershell
    python -m venv venv
    .\venv\Scripts\Activate.ps1
    ```
6.  Install backend dependencies:
    ```powershell
    pip install -r requirements.txt
    ```
7.  Copy the `.env.example` file to `.env` and update the `DATABASE_URL` with your PostgreSQL credentials:
    ```ini
    DATABASE_URL=postgresql://postgres:your_password@localhost/mudranalaya_db
    # Or if using the dedicated user:
    # DATABASE_URL=postgresql://mudranalaya_user:your_secure_password@localhost/mudranalaya_db
    ```

---

## 3. Running the Application (LAN Access)

The application consists of a backend API and a static frontend. For a production-like local deployment on Windows without IIS/Nginx, we use `waitress` (a production WSGI/ASGI server for Windows) for the backend and Python's built-in `http.server` for the static frontend.

### A. Starting the Backend (FastAPI)

1.  Install the `uvicorn` and `waitress` servers (Waitress is excellent for Windows):
    ```powershell
    pip install uvicorn waitress
    ```
2.  Start the backend bound to `0.0.0.0` (all network interfaces) so other computers on the LAN can connect:
    ```powershell
    uvicorn app.main:app --host 0.0.0.0 --port 8000
    # OR using waitress for production:
    # waitress-serve --host=0.0.0.0 --port=8000 app.main:app
    ```
    *Note: For a more robust background service, consider using [NSSM (Non-Sucking Service Manager)](https://nssm.cc/) to run this command as a Windows Service.*

### B. Starting the Frontend

The frontend is pure HTML/JS/CSS. You simply need to serve the `mudranalaya/frontend` directory.

1.  Open a **new** PowerShell terminal.
2.  Navigate to the `mudranalaya/frontend` directory:
    ```powershell
    cd path\to\mudranalaya\frontend
    ```
3.  Start a simple HTTP server on port 80:
    ```powershell
    python -m http.server 80
    ```
    *(Note: Port 80 might require administrator privileges. If it fails, run PowerShell as Administrator).*

---

## 4. Windows Firewall Configuration

For other computers in the Press LAN to access the server, you must open ports 80 (Frontend) and 8000 (Backend API).

1.  Open **Windows Defender Firewall with Advanced Security**.
2.  Click on **Inbound Rules** in the left pane, then click **New Rule...** in the right pane.
3.  Select **Port** and click Next.
4.  Select **TCP** and specify **Specific local ports**: `80, 8000`. Click Next.
5.  Select **Allow the connection**. Click Next.
6.  Apply the rule to **Domain** and **Private** profiles (uncheck Public if this is a secure LAN). Click Next.
7.  Name the rule `Mudranalaya ERP Access` and click Finish.

**Client Access:**
Employees can now access the ERP by typing the server's IP address into their browser:
`http://<SERVER_IP_ADDRESS>` (e.g., `http://192.168.1.100`)

*Ensure the `API_BASE_URL` in `frontend/api-client.js` is set correctly to point to `http://<SERVER_IP_ADDRESS>:8000/api` if necessary, or use relative paths if hosted together.*

---

## 5. Automated Backups (pg_dump)

Database backups are critical. You can schedule a daily backup using Windows Task Scheduler.

1.  Create a batch script named `backup_mudranalaya.bat` in a safe location (e.g., `C:\Backups\`):

    ```bat
    @echo off
    set PGPASSWORD=your_postgres_password
    set BACKUP_DIR=C:\Backups\Mudranalaya
    set DATESTAMP=%DATE:~-4%-%DATE:~4,2%-%DATE:~7,2%
    
    mkdir %BACKUP_DIR% 2>nul
    
    "C:\Program Files\PostgreSQL\13\bin\pg_dump.exe" -U postgres -h localhost -F c mudranalaya_db > "%BACKUP_DIR%\mudranalaya_db_%DATESTAMP%.backup"
    
    echo Backup completed for %DATESTAMP%
    ```

2.  Open **Task Scheduler** in Windows.
3.  Click **Create Basic Task...**
4.  Name it `Mudranalaya Daily Backup`.
5.  Set Trigger to **Daily** at a time when the press is closed (e.g., 2:00 AM).
6.  Action: **Start a program**.
7.  Browse and select your `backup_mudranalaya.bat` file.
8.  Finish the wizard.

---

## 6. Restarting and Maintenance

If the server reboots, the services need to be started again.

**Recommended approach (NSSM):**
To ensure the backend and frontend start automatically on boot:
1.  Download [NSSM](https://nssm.cc/).
2.  Install the Backend as a service:
    ```powershell
    nssm install MudranalayaBackend "path\to\venv\Scripts\uvicorn.exe" "app.main:app --host 0.0.0.0 --port 8000"
    nssm set MudranalayaBackend AppDirectory "path\to\mudranalaya\backend"
    nssm start MudranalayaBackend
    ```
3.  Install the Frontend as a service:
    ```powershell
    nssm install MudranalayaFrontend "python.exe" "-m http.server 80"
    nssm set MudranalayaFrontend AppDirectory "path\to\mudranalaya\frontend"
    nssm start MudranalayaFrontend
    ```

You can now use standard Windows Services (`services.msc`) to Start, Stop, or Restart the ERP components.
