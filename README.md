# ERP_system_GOVT_of_MAH

# Mudranalaya ERP-MIS (Government Printing Press)

> **Mudranalaya ERP-MIS** is a LAN-based Enterprise Resource Planning and Management Information System designed for a Government Printing Press. The system digitizes and coordinates the complete printing-workflow lifecycle, including work-order management, production planning, machine and paper allocation, pre-press/plate preparation, digital and traditional printing, binding and finishing, quality/standard checking, dispatch, billing preparation, inventory-related operations, maintenance, audit trails, and management reporting.

---

## 🏛️ System Overview

Mudranalaya ERP-MIS provides an end-to-end digital operational backbone engineered for the specific requirements, governance hierarchy, and operational workflows of a Government Printing Press.

### Key Capabilities & Workflow Lifecycle
- **Work Order Management:** Centralized registration, departmental docketing, priority scheduling, and lifecycle tracking of government print jobs.
- **Production Planning:** Comprehensive job scheduling, route card generation, and resource requirement calculations.
- **Machine & Material Allocation:** Real-time machine scheduling, paper stock reservations (sheets, reels, GSM, quality), and ink/chemical allocation.
- **Pre-Press & Plate Preparation:** Digital prepress verification, CTP (Computer-to-Plate) tracking, plate lifecycle tracking, and approval sign-offs.
- **Digital & Traditional Printing Operations:** Support for both high-speed digital presses and traditional offset sheet-fed/web printing presses.
- **Batched, Partial & Multi-Year Production:** Production tracking supporting partial deliveries, multi-phase print runs, pause/resume mechanisms, and spanning financial years.
- **Binding & Finishing:** Cutting, folding, stitching, perfect binding, laminating, and packaging workflow management.
- **Quality & Standard Checking:** Pre-dispatch inspection against government printing standards, spoilage calculation, and QC sign-offs.
- **Dispatch & Delivery:** Gate pass creation, delivery challan generation, dispatch logging, and department acknowledgments.
- **Dedicated Billing & Costing Preparation:** Official costing computation based on standard schedule of rates (SoR), paper consumption, machine-hour rates, and billing preparation.
- **Inventory & Store Operations:** Real-time material stock management, minimum-level alerts, requisition processing, and supplier purchasing workflows.
- **Audit Trails & Security:** Comprehensive immutable audit logs, session management, and granular Role-Based Access Control (RBAC).

---

## 🏗️ Architecture & Local LAN Deployment

The system is architected for **LOCAL / LAN DEPLOYMENT** within the Government Press office intranet for high reliability, zero cloud dependency for core operations, and departmental data sovereignty.

```
                    SERVER PC
                       │
              FastAPI Backend
                       │
             PostgreSQL Database
                       │
                   Local LAN
          ┌────────────┼────────────┐
          ▼            ▼            ▼
       Store        Planning     Accounts
         PC            PC           PC
                       │
                       ▼
                    Manager
                       PC
```

---

## 💻 Technology Stack

### Backend
- **Python 3.12**
- **FastAPI** — High-performance asynchronous REST API framework
- **SQLAlchemy 2.x** — ORM and database abstraction
- **Pydantic & Pydantic-Settings** — Strict data validation and environment configuration
- **Uvicorn** — ASGI production server
- **Argon2id & Python-Jose** — Cryptographic password hashing and JWT authentication

### Database
- **PostgreSQL** — Primary production database with `psycopg2-binary`
- **SQLite** — Embedded fallback for lightweight / standalone zero-setup testing

### Real-Time & Communications
- **WebSockets** — Instant bi-directional notifications across press departments

### Frontend
- **HTML5, CSS3, Modern JavaScript (Vanilla)** — Zero-build, fast loading, responsive interface designed for press desktop workstations

### Desktop Deployment & Utilities
- **PyInstaller** — Executable bundling (`Mudranalaya.exe`) for local workstation distribution
- **ReportLab & OpenPyXL** — Formatted PDF and Excel report generation

---

## 📁 Project Structure

```
mudranalaya/
├── API.md                           # Complete REST API specification
├── ARCHITECTURE.md                  # System design, models, and workflow architecture
├── DATABASE.md                      # Schema definitions and database relationships
├── DEPLOYMENT.md                    # Production LAN deployment and packaging guide
├── README.md                        # Project documentation and operational guide
├── SECURITY.md                      # Security policies, RBAC, and encryption details
├── USER_GUIDE.md                    # Department-by-department user manual
├── desktop_entry.py                 # PyInstaller desktop launcher with embedded server
├── mudranalaya.spec                 # PyInstaller build specification
├── .env.example                     # Environment configuration template
├── .gitignore                       # Git ignore rules for secrets, builds, and caches
│
├── backend/
│   ├── app/
│   │   ├── api/                     # API routers (planning, billing, binding, etc.)
│   │   ├── auth/                    # JWT handling, password hashing, dependencies
│   │   ├── core/                    # App config, database connections, security
│   │   ├── licensing/               # Device and installation license validation
│   │   ├── models/                  # SQLAlchemy ORM models
│   │   ├── schemas/                 # Pydantic validation schemas
│   │   ├── services/                # Business logic, audit trails, and inventory
│   │   ├── ws/                      # WebSocket manager for live press updates
│   │   ├── main.py                  # FastAPI application entry point
│   │   └── seed.py                  # Database seeder for demo & initialization
│   ├── scripts/                     # Backend test scripts and e2e workflow tests
│   ├── tests/                       # Automated test suite (RBAC, costing, auth, etc.)
│   └── requirements.txt             # Python dependencies
│
├── frontend/
│   ├── index.html                   # Single-page interface container
│   ├── styles.css                   # Enterprise UI stylesheet
│   ├── app.js                       # Frontend state management and DOM rendering
│   └── api-client.js                # Asynchronous API communications client
│
└── scripts/
    ├── backup.py                    # Database automated backup script
    ├── restore.py                   # Disaster recovery and restore script
    ├── create_first_manager.py      # Secure administrative user initialization
    ├── generate_license_keys.py     # Ed25519 license key generator
    └── issue_license.py             # License token generator for authorized installations
```

---

## 🚀 Quick Start (Local Setup)

### 1. Prerequisites
- Python 3.10+ (Python 3.12 recommended)
- PostgreSQL (for production LAN) or SQLite (for immediate testing)

### 2. Setup Backend Environment
```bash
cd backend
python -m venv ../venv
# Activate on Windows:
..\venv\Scripts\activate
# Activate on Linux/macOS:
source ../venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure Environment Variables
```bash
cp .env.example .env
```
Update `.env` with your local database URL and secure JWT secret key. *Never commit `.env` containing real credentials to Git.*

### 4. Initialize Database
```bash
python -m app.seed
```

### 5. Launch the Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Access the application on the server or any LAN workstation at `http://<SERVER_IP>:8000`.

---

## 🔒 Security & Data Isolation
- **Departmental Isolation:** Access to sensitive records (Stores, Planning, Accounts, Dispatch) is strictly enforced at the API layer via Role-Based Access Control (RBAC).
- **Audit Logging:** Every state transition (work order creation, paper issue, machine allocation, approval, billing) is immutably recorded in the audit log with user and timestamp.
