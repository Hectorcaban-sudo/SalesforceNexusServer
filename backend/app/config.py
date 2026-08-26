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

    # Database (TinyDB) file locations
    db_path: str = str(DATA_DIR / "nexus_db.json")

    # Logging
    log_file: str = str(LOG_DIR / "nexus.log")
    log_level: str = "INFO"

    # Internal broker
    broker_max_queue: int = 10000

    # Worker
    worker_poll_interval_seconds: float = 0.25

    class Config:
        env_file = ".env"


settings = Settings()
