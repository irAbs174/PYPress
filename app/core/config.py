from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "PYpress"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-me-in-production"
    database_url: str = "sqlite:///./pypress.db"
    session_cookie_name: str = "pypress_session"
    admin_email: str = "admin@example.com"
    admin_password: str = "admin12345"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
