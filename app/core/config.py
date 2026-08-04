"""Application settings loaded from environment."""
from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "SIAPKOPO"
    app_env: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/db_kopo"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    password_reset_ttl_seconds: int = 600
    password_reset_code_length: int = 6

    # Fonnte WhatsApp gateway (https://fonnte.com) -- used to deliver the
    # password-reset OTP over WhatsApp. Empty by default so a missing key
    # fails soft (log-only, see WhatsAppProvider) instead of crashing.
    fonnte_api_key: str = ""
    fonnte_api_url: str = "https://api.fonnte.com/send"

    # NoDecode stops pydantic-settings from JSON-decoding the raw env value,
    # so the validator below can split a plain comma-separated string.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    max_upload_size_bytes: int = 5 * 1024 * 1024  # 5 MB, matches FormSurat.jsx's stated limit
    upload_storage_dir: str = "storage"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
