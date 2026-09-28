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
    app_version: str = "1.2.6"

    secret_key: str = "CHANGE_ME_super_secret_key_please_rotate"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 8

    db_path: str = str(DATA_DIR / "nexus.db")
    database_type: str = "sqlite"
    database_host: str = "localhost"
    database_port: int = 0
    database_name: str = "nexus"
    database_user: str = ""
    database_password: str = ""

    log_file: str = str(LOG_DIR / "nexus.log")
    log_level: str = "INFO"
    log_rotation_type: str = "time"
    log_rotation_when: str = "midnight"
    log_rotation_interval: int = 1
    log_rotation_backup_count: int = 14
    log_rotation_max_bytes: int = 5_000_000

    broker_max_queue: int = 10000
    worker_poll_interval_seconds: float = 0.25
    cometd_reconnect_min_delay_seconds: float = 2.0
    cometd_reconnect_max_delay_seconds: float = 60.0
    cometd_reconnect_backoff_factor: float = 2.0
    processor_timeout_seconds: int = 20
    dss_use_subprocess: bool = False
    dss_warmup_on_start: bool = True
    dss_timeout_seconds: int = 180
    worker_max_concurrency: int = 10
    max_failed_login_attempts: int = 5
    lockout_duration_seconds: int = 900
    uvicorn_host: str = "0.0.0.0"
    uvicorn_port: int = 8000
    uvicorn_reload: bool = False
    uvicorn_workers: int = 1
    uvicorn_log_level: str = "info"
    otel_service_name: str = "salesforce-nexus-ai-server"
    otel_exporter_otlp_endpoint: str = ""
    otel_console_exporter: bool = False
    sso_issuer: str = ""
    sso_client_id: str = ""
    sso_client_secret: str = ""
    sso_redirect_uri: str = "http://localhost:8000/api/auth/sso/callback"
    sso_scope: str = "openid email profile"
    sso_default_role: str = "viewer"
    frontend_base_url: str = "http://localhost:8000"
    http_connect_timeout: float = 5.0
    http_read_timeout: float = 30.0
    http_write_timeout: float = 30.0
    circuit_fail_threshold: int = 5
    circuit_open_seconds: float = 60.0
    worker_max_retries: int = 3
    json_logs: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
