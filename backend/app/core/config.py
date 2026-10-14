"""Application configuration.

Every external dependency has a working local fallback so the platform runs with
zero infrastructure (SQLite + local filesystem + in-process bus + local vector
index). Production deployments override via environment variables.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Application ----
    app_name: str = "Pharma Intelligence Platform"
    environment: str = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"

    # ---- Database ----
    # Postgres in production (pgvector enabled), SQLite for local dev.
    database_url: str = f"sqlite:///{DATA_DIR / 'pharma.db'}"
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # ---- Cache / broker ----
    redis_url: str | None = None  # falls back to in-process cache when unset
    kafka_bootstrap_servers: str | None = None  # falls back to in-process bus
    kafka_topic_prefix: str = "pharma"
    rabbitmq_url: str | None = None

    # ---- Object storage ----
    storage_backend: str = "local"  # local | azure_blob
    storage_local_dir: Path = DATA_DIR / "artifacts"
    azure_storage_connection_string: str | None = None
    azure_storage_container: str = "pharma-artifacts"

    # ---- Vector search ----
    vector_backend: str = "auto"  # auto | pgvector | numpy
    embedding_dim: int = 384
    embedding_model: str = "local-hashing"  # or an Azure OpenAI deployment name

    # ---- LLM ----
    llm_provider: str = "auto"  # auto | azure_openai | openai | offline
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_chat_deployment: str = "gpt-4o"
    azure_openai_embedding_deployment: str = "text-embedding-3-small"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: int = 60

    # ---- Security ----
    jwt_secret: str = "dev-only-change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60
    refresh_token_ttl_days: int = 14
    rate_limit_per_minute: int = 240
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )

    # ---- Collection ----
    http_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    http_timeout_seconds: int = 60
    http_max_retries: int = 4
    http_backoff_seconds: float = 1.5
    collector_min_interval_seconds: int = 2  # politeness delay between requests
    use_playwright: bool = False  # opt-in; static HTTP + parser is the default path

    # ---- Alerting ----
    alert_min_priority_to_notify: int = 40  # only meaningful alerts reach users
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "pharma-intel@example.com"
    # 587 (submission) upgrades with STARTTLS; 465 uses implicit TLS from the
    # first byte. Both are common, so the transport is chosen by port and
    # ``smtp_use_tls`` can force STARTTLS on/off for anything unusual.
    smtp_use_ssl: bool | None = None  # None = infer from port
    smtp_use_tls: bool = True
    # The address that receives every detected change and alert. Deployments
    # override it with a comma-separated ALERT_EMAIL_RECIPIENTS list; the
    # platform default is the single monitored mailbox.
    alert_email_recipients: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["pharsightspatent@gmail.com"]
    )
    teams_webhook_url: str | None = None

    @field_validator("alert_email_recipients", mode="before")
    @classmethod
    def _csv_recipients(cls, value: object) -> object:
        # Deployments commonly export this as an empty string when unset, and as
        # a comma-separated list otherwise — accept both.
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                return json.loads(text)
            return [part.strip() for part in text.split(",") if part.strip()]
        return value

    # ---- Observability ----
    otel_enabled: bool = False
    otel_endpoint: str | None = None
    metrics_enabled: bool = True

    # Self-service account creation. This is a company-internal platform: there
    # is no open sign-up. Accounts are created on the sign-in page by claiming
    # ``allowed_login_email`` (see below), which is the one identity the
    # deployment accepts.
    allow_self_registration: bool = False

    # Single-account deployment. Exactly one address is authorized on the
    # platform: ``allowed_login_email``. It is the only address that may sign
    # in, the only address that may be created on the sign-in page, and it
    # cannot be disabled. Any other address is refused. Set RESTRICT_LOGIN=false
    # to restore the normal multi-role accounts.
    restrict_login: bool = True
    allowed_login_email: str = "pharsightspatent@gmail.com"

    # When true, the single allowed address is the only account the platform
    # will hold: an existing account cannot be moved onto another address and
    # no second account can be provisioned. Set BLOCK_ADDITIONAL_ACCOUNTS=false
    # to allow the normal admin-only flow.
    block_additional_accounts: bool = True

    # ---- Automatic monitoring ----
    # The platform monitors the sources on its own cadence; users never run a
    # sweep by hand. Production overrides the cadence via Airflow, but the
    # in-process scheduler keeps the local deployment equally automatic.
    scheduler_enabled: bool = True
    scheduler_interval_minutes: int = 360

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def artifacts_dir(self) -> Path:
        self.storage_local_dir.mkdir(parents=True, exist_ok=True)
        return self.storage_local_dir


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
    return settings


settings = get_settings()
