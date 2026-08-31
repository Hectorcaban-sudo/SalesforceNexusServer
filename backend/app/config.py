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

    # Internal broker
    broker_max_queue: int = 10000

    # Worker
    worker_poll_interval_seconds: float = 0.25

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
