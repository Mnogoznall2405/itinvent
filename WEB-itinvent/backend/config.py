"""
Configuration management for IT-invent Web application.
Loads settings from environment variables with sensible defaults.
"""
import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

# Single source of truth: project root .env
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROOT_ENV_PATH = PROJECT_ROOT / ".env"
LEGACY_BACKEND_ENV_PATH = Path(__file__).resolve().parent / ".env"
LEGACY_API_ENV_PATH = Path(__file__).resolve().parent / "api" / ".env"

if ROOT_ENV_PATH.exists():
    load_dotenv(str(ROOT_ENV_PATH))
    if LEGACY_BACKEND_ENV_PATH.exists():
        warnings.warn(
            f"Legacy env file is ignored: {LEGACY_BACKEND_ENV_PATH}. Use {ROOT_ENV_PATH} instead.",
            RuntimeWarning,
            stacklevel=2,
        )
    if LEGACY_API_ENV_PATH.exists():
        warnings.warn(
            f"Legacy env file is ignored: {LEGACY_API_ENV_PATH}. Use {ROOT_ENV_PATH} instead.",
            RuntimeWarning,
            stacklevel=2,
        )
else:
    # Backward-compatible fallback.
    if LEGACY_BACKEND_ENV_PATH.exists():
        load_dotenv(str(LEGACY_BACKEND_ENV_PATH))
        warnings.warn(
            f"Root .env not found at {ROOT_ENV_PATH}; loaded fallback {LEGACY_BACKEND_ENV_PATH}.",
            RuntimeWarning,
            stacklevel=2,
        )


@dataclass
class DatabaseConfig:
    """Database connection configuration."""
    host: str
    database: str
    username: str
    password: str
    driver: str = "SQL Server"

    @property
    def connection_string(self) -> str:
        """Build ODBC connection string."""
        return (
            f"DRIVER={self.driver};"
            f"SERVER={self.host};"
            f"DATABASE={self.database};"
            f"UID={self.username};"
            f"PWD={self.password};"
            "TrustServerCertificate=yes;"
            "autocommit=True;"
        )


@dataclass
class JWTConfig:
    """JWT token configuration."""
    secret_key: str
    previous_secret_keys: List[str]
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 hours


@dataclass
class AppConfig:
    """Application configuration."""
    app_name: str = "IT-invent Web API"
    version: str = "1.0.0"
    debug: bool = False
    cors_origins: List[str] = None
    auth_cookie_name: str = "itinvent_access_token"
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"
    auth_cookie_domain: Optional[str] = None
    ldap_server: Optional[str] = None
    ldap_domain: Optional[str] = None

    def __post_init__(self):
        if self.cors_origins is None:
            self.cors_origins = ["http://localhost:5173", "http://localhost:3000"]


@dataclass
class Config:
    """Main configuration container."""
    database: DatabaseConfig
    jwt: JWTConfig
    app: AppConfig

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        jwt_secret_keys_raw = str(os.getenv("JWT_SECRET_KEYS", "") or "").strip()
        jwt_previous_keys_raw = str(os.getenv("JWT_PREVIOUS_SECRET_KEYS", "") or "").strip()

        if jwt_secret_keys_raw:
            secret_keys = [item.strip() for item in jwt_secret_keys_raw.split(",") if item.strip()]
            jwt_secret_key = secret_keys[0] if secret_keys else ""
            jwt_previous_secret_keys = secret_keys[1:]
        else:
            jwt_secret_key = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
            jwt_previous_secret_keys = [
                item.strip() for item in jwt_previous_keys_raw.split(",") if item.strip()
            ]

        cookie_samesite = str(os.getenv("AUTH_COOKIE_SAMESITE", "lax")).strip().lower() or "lax"
        if cookie_samesite not in {"lax", "strict", "none"}:
            cookie_samesite = "lax"

        return cls(
            database=DatabaseConfig(
                host=os.getenv("SQL_SERVER_HOST", "10.103.0.213"),
                database=os.getenv("SQL_SERVER_DATABASE", "ITINVENT"),
                username=os.getenv("SQL_SERVER_USERNAME", "ROUser"),
                password=os.getenv("SQL_SERVER_PASSWORD", ""),
                driver=os.getenv("SQL_SERVER_DRIVER", "SQL Server"),
            ),
            jwt=JWTConfig(
                secret_key=jwt_secret_key,
                previous_secret_keys=jwt_previous_secret_keys,
                access_token_expire_minutes=int(os.getenv("JWT_EXPIRE_MINUTES", "480")),
            ),
            app=AppConfig(
                app_name="IT-invent Web API",
                version="1.0.0",
                debug=os.getenv("DEBUG", "false").lower() == "true",
                cors_origins=os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else None,
                auth_cookie_name=str(os.getenv("AUTH_COOKIE_NAME", "itinvent_access_token")).strip() or "itinvent_access_token",
                auth_cookie_secure=os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true",
                auth_cookie_samesite=cookie_samesite,
                auth_cookie_domain=(str(os.getenv("AUTH_COOKIE_DOMAIN", "") or "").strip() or None),
                ldap_server=str(os.getenv("LDAP_SERVER", "10.103.0.150")).strip() or None,
                ldap_domain=str(os.getenv("LDAP_DOMAIN", "zsgp.corp")).strip() or None,
            ),
        )


# Global config instance
config = Config.from_env()
