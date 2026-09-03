"""
Central configuration for Salesforce Nexus AI Server.
Values can be overridden with environment variables or a .env file.
"""
from pydantic_settings import BaseSettings
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    app_name: str = "Salesforce Nexus AI Server"

    # JWT / auth
    secret_key: str = "CHANGE_ME_super_secret_key_please_rotate"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 8

    # Database (SQLite) file location
    db_path: str = str(DATA_DIR / "nexus.db")

    # Logging
    log_file: str = str(LOG_DIR / "nexus.log")
    log_level: str = "INFO"
    # "time" = daily (or interval-based) rotation, "size" = rotate once a
    # size threshold is hit. Both are configurable via env vars so ops can
    # tune retention without a code change.
    log_rotation_type: str = "time"          # "time" | "size"
    log_rotation_when: str = "midnight"      # TimedRotatingFileHandler `when` (midnight/H/D/etc.) - only used for "time"
    log_rotation_interval: int = 1           # rotate every N `log_rotation_when` units - only used for "time"
    log_rotation_backup_count: int = 14      # how many rotated files to keep
    log_rotation_max_bytes: int = 5_000_000  # only used for "size"

    # Internal broker
    broker_max_queue: int = 10000

    # Worker
    worker_poll_interval_seconds: float = 0.25

    # CometD reconnect backoff (issue: keep retrying instead of giving up)
    cometd_reconnect_min_delay_seconds: float = 2.0
    cometd_reconnect_max_delay_seconds: float = 60.0
    cometd_reconnect_backoff_factor: float = 2.0

    # Custom payload processor subprocess timeout
    processor_timeout_seconds: int = 20

    # Uvicorn server settings (used by run.py) - configurable so the same
    # image/checkout can be pointed at a different bind address/port purely
    # via environment, without touching run.py.
    #
    # IMPORTANT: leave uvicorn_workers at 1. Every background task this app
    # runs (CometD listeners per org, the broker consumers, the internal
    # message broker itself when using the default in-process backend) lives
    # in a single process's memory. Running more than one uvicorn worker
    # would start a completely separate, independent copy of all of that in
    # each worker process - meaning every Salesforce org would be listened
    # to multiple times over, and every event would be processed and
    # published multiple times. If you need to scale beyond one process,
    # put a real broker in front of it (RabbitMQ, see Admin Configuration ->
    # Message broker) and run multiple independent *instances* of this app
    # behind a load balancer instead, each pointed at the same broker and
    # SQLite/database - not multiple uvicorn workers inside one instance.
    uvicorn_host: str = "0.0.0.0"
    uvicorn_port: int = 8000
    uvicorn_reload: bool = False
    uvicorn_workers: int = 1
    uvicorn_log_level: str = "info"

    # OpenTelemetry
    otel_service_name: str = "salesforce-nexus-ai-server"
    otel_exporter_otlp_endpoint: str = ""     # e.g. http://otel-collector:4318 - leave blank to disable OTLP export
    otel_console_exporter: bool = False       # print spans to stdout - handy for local debugging without a collector

    # SSO (generic OIDC - works with Okta, Azure AD, Auth0, Google Workspace, etc.)
    sso_issuer: str = ""             # e.g. https://your-tenant.okta.com  - leave blank to disable SSO
    sso_client_id: str = ""
    sso_client_secret: str = ""
    sso_redirect_uri: str = "http://localhost:8000/api/auth/sso/callback"
    sso_scope: str = "openid email profile"
    sso_default_role: str = "viewer"  # role assigned to newly-created SSO users
    frontend_base_url: str = "http://localhost:8000"  # where to send the browser back to after SSO login

    class Config:
        env_file = ".env"


settings = Settings()
