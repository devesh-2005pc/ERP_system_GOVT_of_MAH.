"""
Central application configuration.

All secrets/config come from environment variables (or a `.env` file loaded by
pydantic-settings). NOTHING sensitive is hardcoded here. See `.env.example`
at the project root for the full list of variables an office deployment must set.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    APP_NAME: str = "Mudranalaya ERP-MIS"
    ENVIRONMENT: str = "development"  # development | production
    DEBUG: bool = True

    # --- Database ---
    # Development default: local SQLite file so the app runs with zero setup.
    # Production (office server): set DATABASE_URL to a PostgreSQL DSN, e.g.
    #   postgresql+psycopg2://erp_user:STRONG_PASSWORD@127.0.0.1:5432/mudranalaya_erp
    DATABASE_URL: str = "sqlite:///./data/mudranalaya.db"

    # --- Auth / JWT ---
    # MUST be overridden in production via environment variable. There is
    # intentionally no safe hardcoded default used in production mode (see
    # startup check in main.py).
    JWT_SECRET_KEY: str = "dev-only-insecure-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    SESSION_IDLE_TIMEOUT_MINUTES: int = 30

    # --- CORS ---
    # Comma-separated list of allowed origins for browser clients (office LAN
    # URLs). Never "*" in production.
    CORS_ALLOWED_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"

    # --- Files ---
    UPLOAD_DIR: str = "./data/uploads"
    MAX_UPLOAD_MB: int = 15
    ALLOWED_UPLOAD_EXTENSIONS: str = ".pdf,.jpg,.jpeg,.png"

    # --- Backups ---
    BACKUP_DIR: str = "./data/backups"

    # --- Licensing ---
    LICENSE_PUBLIC_KEY_PATH: str = "./data/license/public_key.pem"
    LICENSE_TOKEN_PATH: str = "./data/license/license_token.json"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_upload_ext_list(self) -> list[str]:
        return [e.strip().lower() for e in self.ALLOWED_UPLOAD_EXTENSIONS.split(",") if e.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
