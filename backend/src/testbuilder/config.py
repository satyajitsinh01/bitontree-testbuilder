from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

IST = ZoneInfo("Asia/Kolkata")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TB_", extra="ignore")

    app_name: str = "TestBuilder"
    debug: bool = False
    # sqlite for zero-dependency dev; postgres+asyncpg in production (see infra/)
    database_url: str = "sqlite+aiosqlite:///./testbuilder.db"
    redis_url: str = ""  # empty -> in-memory fallbacks (dev/test only)
    inline_jobs: bool = True  # run background jobs inline; False requires redis+arq worker

    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    # External services; unset values switch the service to a local stub.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    judge0_url: str = ""
    judge0_auth_token: str = ""
    resend_api_key: str = ""
    email_from: str = "TestBuilder <no-reply@testbuilder.local>"
    # SMTP takes priority over Resend when smtp_host is set (e.g. Gmail app password)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True  # STARTTLS on port 587
    smtp_use_ssl: bool = False  # implicit TLS on port 465

    s3_endpoint: str = ""
    s3_bucket: str = "testbuilder"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    local_storage_dir: str = "./storage_local"

    frontend_base_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    # Exam engine defaults
    screenshot_interval_sec: int = 5
    percentile_min_cohort: int = 20
    run_rate_limit_per_min: int = 10
    submit_limit_per_question: int = 30
    evidence_retention_days: int = 90


@lru_cache
def get_settings() -> Settings:
    return Settings()
