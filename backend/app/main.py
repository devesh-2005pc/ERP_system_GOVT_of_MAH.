import logging
import time
import uuid

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.database import Base, engine
from app.models import *  # noqa: F401,F403  (ensures every model is registered on Base.metadata)

from app.api.routers import (
    auth as auth_router,
    materials as materials_router,
    requests as requests_router,
    purchasing as purchasing_router,
    production as production_router,
    accounts as accounts_router,
    costing as costing_router,
    users as users_router,
    audit as audit_router,
    notifications as notifications_router,
    reports as reports_router,
    forecasting as forecasting_router,
    dashboard as dashboard_router,
    licensing as licensing_router,
    ws_routes,
    # Press workflow enhancement routers
    machines as machines_router,
    planning as planning_router,
    plate_making as plate_making_router,
    binding as binding_router,
    standard as standard_router,
    billing as billing_router,
)

settings = get_settings()

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger("mudranalaya")

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url=None,
)


# ---------------- Startup safety checks ----------------
@app.on_event("startup")
def on_startup():
    if settings.ENVIRONMENT == "production" and settings.JWT_SECRET_KEY == "dev-only-insecure-secret-change-me":
        raise RuntimeError(
            "Refusing to start in production with the default JWT_SECRET_KEY. "
            "Set a strong JWT_SECRET_KEY environment variable before deploying."
        )
    if settings.ENVIRONMENT == "production" and settings.DATABASE_URL.startswith("sqlite"):
        logger.warning(
            "Running in production with SQLite. PostgreSQL is required for real "
            "multi-workstation office deployment (see DEPLOYMENT.md)."
        )
    # Dev convenience only: for production, use Alembic migrations instead of create_all.
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema ready (mode=%s)", "create_all-dev" if settings.DEBUG else "startup-check")


# ---------------- Security headers ----------------
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.time()
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Request-ID"] = request_id
    duration_ms = (time.time() - start) * 1000
    logger.info("%s %s -> %s (%.1fms) [%s]", request.method, request.url.path, response.status_code, duration_ms, request_id)
    return response


# ---------------- CORS ----------------
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,  # never "*" — explicit office LAN origins only
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ---------------- Error handling: never leak stack traces to users ----------------
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": "Invalid request data", "details": exc.errors()})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": "An unexpected error occurred. Please try again or contact IT support."})


# ---------------- Routers ----------------
app.include_router(auth_router.router)
app.include_router(materials_router.router)
app.include_router(materials_router.inv_router)
app.include_router(requests_router.router)
app.include_router(purchasing_router.router)
app.include_router(production_router.router)
app.include_router(production_router.dispatch_router)
app.include_router(accounts_router.router)
app.include_router(costing_router.router)
app.include_router(users_router.router)
app.include_router(audit_router.router)
app.include_router(notifications_router.router)
app.include_router(reports_router.router)
app.include_router(forecasting_router.router)
app.include_router(dashboard_router.router)
app.include_router(licensing_router.router)
app.include_router(ws_routes.router)
# Press workflow enhancement routers
app.include_router(machines_router.router)
app.include_router(planning_router.router)
app.include_router(plate_making_router.router)
app.include_router(binding_router.router)
app.include_router(standard_router.router)
app.include_router(billing_router.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.APP_NAME}


# ---------------- Serve the frontend (single-page static app) ----------------
from pathlib import Path  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
