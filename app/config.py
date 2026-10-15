"""Application settings, read from environment variables (see .env.example)."""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

log = logging.getLogger("railmate.config")


def load_dotenv(path: Path = BASE_DIR / ".env") -> None:
    """Minimal .env loader (KEY=VALUE lines). Real environment variables always win."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(f"RAILMATE_{name}", default)


@dataclass(frozen=True)
class Settings:
    env: str = field(default_factory=lambda: _env("ENV", "development"))
    db_path: Path = field(
        default_factory=lambda: Path(_env("DB_PATH", str(BASE_DIR / "data" / "railmate.db")))
    )
    user_db_path: Path = field(
        default_factory=lambda: Path(_env("USER_DB_PATH", str(BASE_DIR / "var" / "users.db")))
    )
    model_path: Path = field(
        default_factory=lambda: Path(_env("MODEL_PATH", str(BASE_DIR / "ml" / "artifacts" / "delay_model.joblib")))
    )
    faq_path: Path = field(default_factory=lambda: BASE_DIR / "data" / "faq.json")
    frontend_dir: Path = field(default_factory=lambda: BASE_DIR / "frontend")
    secret_key: str = field(default_factory=lambda: _env("SECRET_KEY", "") or "")
    token_minutes: int = field(default_factory=lambda: int(_env("TOKEN_MINUTES", "120")))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(o.strip() for o in (_env("CORS_ORIGINS", "") or "").split(",") if o.strip())
    )
    rate_limit_per_minute: int = field(default_factory=lambda: int(_env("RATE_LIMIT", "120")))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    def resolved_secret(self) -> str:
        """Return the JWT secret. Production must set one explicitly."""
        if self.secret_key:
            if self.is_production and len(self.secret_key) < 32:
                raise RuntimeError("RAILMATE_SECRET_KEY must be at least 32 characters in production")
            return self.secret_key
        if self.is_production:
            raise RuntimeError("RAILMATE_SECRET_KEY must be set in production")
        log.warning("RAILMATE_SECRET_KEY not set - using a random dev key (tokens reset on restart)")
        return _DEV_SECRET


_DEV_SECRET = secrets.token_urlsafe(32)


def get_settings() -> Settings:
    return Settings()
