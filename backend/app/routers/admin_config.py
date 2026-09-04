from fastapi import APIRouter, Depends, HTTPException
import os
import pathlib

from ..auth import require_role
from ..database import admin_settings_table, Q
from ..models import (
    DSSClientConfigUpdate, DSSClientConfigOut, ProcessingModeConfig, BrokerConfig, BrokerConfigOut,
    LangflowConfigUpdate, LangflowConfigOut, EmailSettingsUpdate, EmailSettingsOut,
    DatabaseConfigUpdate, DatabaseConfigOut, DatabaseTestRequest,
)
from ..logging_config import log_event
from ..broker import broker, BROKER_CONFIG_ID
from ..config import settings

router = APIRouter(prefix="/api/admin-config", tags=["admin-config"], dependencies=[Depends(require_role("admin"))])

DSS_CLIENT_ID = "dss_client"
PROCESSING_MODE_ID = "processing_mode"
LANGFLOW_ID = "langflow"
EMAIL_SETTINGS_ID = "email_settings"


def _get_raw() -> dict:
    return admin_settings_table.get(Q.id == DSS_CLIENT_ID) or {
        "id": DSS_CLIENT_ID, "url": "", "project_name": "", "llm": "", "api_key": "",
    }


def _mask(cfg: dict) -> DSSClientConfigOut:
    return DSSClientConfigOut(
        url=cfg.get("url", ""),
        project_name=cfg.get("project_name", ""),
        llm=cfg.get("llm", ""),
        api_key="••••••••" if cfg.get("api_key") else "",
        configured=bool(cfg.get("url")),
    )


@router.get("/dss-client", response_model=DSSClientConfigOut)
def get_dss_client_config():
    return _mask(_get_raw())


def get_dss_client_config_raw() -> dict:
    """Internal accessor (unmasked) used by the payload processor - not exposed as an API route."""
    return _get_raw()


@router.put("/dss-client", response_model=DSSClientConfigOut)
def upsert_dss_client_config(updates: DSSClientConfigUpdate):
    """
    Upsert: creates the DSSClient config record if it doesn't exist yet,
    otherwise updates only the fields that were actually sent. As with
    Salesforce org secrets, an empty/omitted `api_key` on an update leaves
    the previously stored key untouched rather than blanking it out.
    """
    data = {k: v for k, v in updates.model_dump().items() if v is not None and v != ""}

    existing = admin_settings_table.get(Q.id == DSS_CLIENT_ID)
    if existing:
        if data:
            admin_settings_table.update(data, Q.id == DSS_CLIENT_ID)
        log_event("info", "DSSClient admin configuration updated", fields=list(data.keys()))
    else:
        record = {"id": DSS_CLIENT_ID, "url": "", "project_name": "", "llm": "", "api_key": ""}
        record.update(data)
        admin_settings_table.insert(record)
        log_event("info", "DSSClient admin configuration created")

    return _mask(admin_settings_table.get(Q.id == DSS_CLIENT_ID))


# ---------- Processing mode (local / DSSClient / custom uploaded script) ----------
@router.get("/processing-mode", response_model=ProcessingModeConfig)
def get_processing_mode():
    row = admin_settings_table.get(Q.id == PROCESSING_MODE_ID)
    return ProcessingModeConfig(**row) if row else ProcessingModeConfig()


def get_processing_mode_raw() -> dict:
    """Internal accessor used by worker.process_payload() - not exposed as an API route."""
    row = admin_settings_table.get(Q.id == PROCESSING_MODE_ID)
    return row or {"mode": "local", "active_processor_id": None}


@router.put("/processing-mode", response_model=ProcessingModeConfig)
def set_processing_mode(config: ProcessingModeConfig):
    record = {"id": PROCESSING_MODE_ID, "mode": config.mode.value, "active_processor_id": config.active_processor_id}
    existing = admin_settings_table.get(Q.id == PROCESSING_MODE_ID)
    if existing:
        admin_settings_table.update(record, Q.id == PROCESSING_MODE_ID)
    else:
        admin_settings_table.insert(record)
    log_event("info", f"Processing mode set to '{config.mode.value}'", active_processor_id=config.active_processor_id)
    return ProcessingModeConfig(**record)


# ---------- Langflow ----------
def _get_langflow_raw() -> dict:
    return admin_settings_table.get(Q.id == LANGFLOW_ID) or {
        "id": LANGFLOW_ID, "base_url": "", "flow_id": "", "api_key": "", "input_field": "input_value", "output_path": "",
    }


def get_langflow_config_raw() -> dict:
    """Internal accessor (unmasked) used by worker.process_payload() - not exposed as an API route."""
    return _get_langflow_raw()


def _mask_langflow(cfg: dict) -> LangflowConfigOut:
    return LangflowConfigOut(
        base_url=cfg.get("base_url", ""),
        flow_id=cfg.get("flow_id", ""),
        api_key="••••••••" if cfg.get("api_key") else "",
        input_field=cfg.get("input_field") or "input_value",
        output_path=cfg.get("output_path", ""),
        configured=bool(cfg.get("base_url") and cfg.get("flow_id")),
    )


@router.get("/langflow", response_model=LangflowConfigOut)
def get_langflow_config():
    return _mask_langflow(_get_langflow_raw())


@router.put("/langflow", response_model=LangflowConfigOut)
def upsert_langflow_config(updates: LangflowConfigUpdate):
    """Upsert, same pattern as DSSClient - api_key is never blanked out by leaving it empty."""
    data = {k: v for k, v in updates.model_dump().items() if v is not None and v != ""}

    existing = admin_settings_table.get(Q.id == LANGFLOW_ID)
    if existing:
        if data:
            admin_settings_table.update(data, Q.id == LANGFLOW_ID)
        log_event("info", "Langflow admin configuration updated", fields=list(data.keys()))
    else:
        record = {"id": LANGFLOW_ID, "base_url": "", "flow_id": "", "api_key": "", "input_field": "input_value", "output_path": ""}
        record.update(data)
        admin_settings_table.insert(record)
        log_event("info", "Langflow admin configuration created")

    return _mask_langflow(admin_settings_table.get(Q.id == LANGFLOW_ID))


# ---------- Email (SMTP) settings ----------
def _get_email_raw() -> dict:
    return admin_settings_table.get(Q.id == EMAIL_SETTINGS_ID) or {
        "id": EMAIL_SETTINGS_ID, "host": "", "port": 587, "username": "", "password": "",
        "use_tls": True, "from_address": "",
    }


def get_email_settings_raw() -> dict:
    """Internal accessor (unmasked) used by integrations.py's email sender - not exposed as an API route."""
    return _get_email_raw()


def _mask_email(cfg: dict) -> EmailSettingsOut:
    return EmailSettingsOut(
        host=cfg.get("host", ""),
        port=cfg.get("port", 587),
        username=cfg.get("username", ""),
        password="••••••••" if cfg.get("password") else "",
        use_tls=cfg.get("use_tls", True),
        from_address=cfg.get("from_address", ""),
        configured=bool(cfg.get("host") and cfg.get("from_address")),
    )


@router.get("/email", response_model=EmailSettingsOut)
def get_email_settings():
    return _mask_email(_get_email_raw())


@router.put("/email", response_model=EmailSettingsOut)
def upsert_email_settings(updates: EmailSettingsUpdate):
    """Upsert, same pattern as DSSClient/Langflow - password is never blanked out by leaving it empty."""
    data = {k: v for k, v in updates.model_dump().items() if v is not None and v != ""}

    existing = admin_settings_table.get(Q.id == EMAIL_SETTINGS_ID)
    if existing:
        if data:
            admin_settings_table.update(data, Q.id == EMAIL_SETTINGS_ID)
        log_event("info", "Email (SMTP) admin configuration updated", fields=list(data.keys()))
    else:
        record = {"id": EMAIL_SETTINGS_ID, "host": "", "port": 587, "username": "", "password": "", "use_tls": True, "from_address": ""}
        record.update(data)
        admin_settings_table.insert(record)
        log_event("info", "Email (SMTP) admin configuration created")

    return _mask_email(admin_settings_table.get(Q.id == EMAIL_SETTINGS_ID))


# ---------- Database backend ----------
# This one is fundamentally different from every other setting on this page:
# the database itself is where all the OTHER settings live, so which
# database to connect to can't be stored inside the database - it has to be
# known before a connection is ever made. That means it can only come from
# the environment (.env / real env vars), and - like the message broker -
# changing it always requires a restart. This section is a config-builder
# and connection-tester, not a live-apply control: it can write the new
# values to a .env file for you (if the file is writable) so you just need
# to restart, but it never touches the live connection.
ENV_FILE_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / ".env"


def _build_test_url(cfg: DatabaseTestRequest) -> str:
    import sqlalchemy as sa

    db_type = cfg.database_type.lower()
    if db_type == "sqlite":
        raise HTTPException(400, "SQLite doesn't need a connection test - it's a local file, always available")
    if db_type == "postgres":
        port = cfg.database_port or 5432
        return str(sa.URL.create(
            "postgresql+psycopg2", username=cfg.database_user, password=cfg.database_password,
            host=cfg.database_host, port=port, database=cfg.database_name,
        ))
    if db_type == "sqlserver":
        port = cfg.database_port or 1433
        return str(sa.URL.create(
            "mssql+pyodbc", username=cfg.database_user, password=cfg.database_password,
            host=cfg.database_host, port=port, database=cfg.database_name,
            query={"driver": "ODBC Driver 18 for SQL Server", "TrustServerCertificate": "yes"},
        ))
    if db_type == "oracle":
        port = cfg.database_port or 1521
        return str(sa.URL.create(
            "oracle+oracledb", username=cfg.database_user, password=cfg.database_password,
            host=cfg.database_host, port=port, query={"service_name": cfg.database_name},
        ))
    raise HTTPException(400, f"Unknown database_type '{cfg.database_type}'")


@router.get("/database", response_model=DatabaseConfigOut)
def get_database_config():
    return DatabaseConfigOut(
        database_type=settings.database_type,
        database_host=settings.database_host,
        database_port=settings.database_port,
        database_name=settings.database_name,
        database_user=settings.database_user,
        database_password="••••••••" if settings.database_password else "",
        db_path=settings.db_path,
        env_file_writable=_env_file_writable(),
    )


def _env_file_writable() -> bool:
    try:
        if ENV_FILE_PATH.exists():
            return os.access(ENV_FILE_PATH, os.W_OK)
        return os.access(ENV_FILE_PATH.parent, os.W_OK)
    except Exception:  # noqa: BLE001
        return False


@router.post("/database/test")
def test_database_connection(cfg: DatabaseTestRequest):
    """Tries a real connection with the given parameters WITHOUT touching
    the app's live database connection - safe to try before committing to a
    restart."""
    import sqlalchemy as sa

    if cfg.database_type.lower() == "sqlite":
        return {"detail": "SQLite doesn't need a connection test - it's a local file, always available"}

    url = _build_test_url(cfg)
    try:
        engine = sa.create_engine(url, connect_args={"connect_timeout": 5} if "postgresql" in url else {})
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        engine.dispose()
        return {"detail": f"Connected successfully to {cfg.database_type}"}
    except ModuleNotFoundError as exc:
        raise HTTPException(400, f"Driver not installed for {cfg.database_type}: {exc}. See requirements.txt for the pip package this backend needs.")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Connection failed: {exc}")


@router.put("/database", response_model=DatabaseConfigOut)
def update_database_config(cfg: DatabaseConfigUpdate):
    """
    Writes the new database settings to the backend's .env file (creating it
    if it doesn't exist) and returns the result. This does NOT reconnect the
    running app - restart the server for it to take effect (see the module
    docstring above for why a live-apply isn't possible here).
    """
    env_updates = {"DATABASE_TYPE": cfg.database_type}
    if cfg.database_host is not None:
        env_updates["DATABASE_HOST"] = cfg.database_host
    if cfg.database_port is not None:
        env_updates["DATABASE_PORT"] = str(cfg.database_port)
    if cfg.database_name is not None:
        env_updates["DATABASE_NAME"] = cfg.database_name
    if cfg.database_user is not None:
        env_updates["DATABASE_USER"] = cfg.database_user
    if cfg.database_password:  # never blank out a saved password by leaving the field empty
        env_updates["DATABASE_PASSWORD"] = cfg.database_password

    if not _env_file_writable():
        raise HTTPException(
            400,
            f"Cannot write to {ENV_FILE_PATH} - set these environment variables manually instead: "
            + ", ".join(f"{k}={v}" for k, v in env_updates.items() if k != "DATABASE_PASSWORD"),
        )

    _write_env_vars(env_updates)
    log_event("warning", f"Database configuration written to .env (type={cfg.database_type}) - restart required to take effect")

    return DatabaseConfigOut(
        database_type=cfg.database_type,
        database_host=cfg.database_host or settings.database_host,
        database_port=cfg.database_port or settings.database_port,
        database_name=cfg.database_name or settings.database_name,
        database_user=cfg.database_user or settings.database_user,
        database_password="••••••••" if (cfg.database_password or settings.database_password) else "",
        db_path=settings.db_path,
        env_file_writable=True,
    )


def _write_env_vars(updates: dict):
    lines = []
    if ENV_FILE_PATH.exists():
        lines = ENV_FILE_PATH.read_text().splitlines()

    remaining = dict(updates)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in remaining:
            lines[i] = f"{key}={remaining.pop(key)}"

    for key, value in remaining.items():
        lines.append(f"{key}={value}")

    ENV_FILE_PATH.write_text("\n".join(lines) + "\n")


# ---------- Message broker (internal in-process vs RabbitMQ) ----------
def _mask_broker(cfg: dict) -> BrokerConfigOut:
    rmq = dict(cfg.get("rabbitmq", {}))
    if rmq.get("password"):
        rmq["password"] = "••••••••"
    return BrokerConfigOut(
        type=cfg.get("type", "internal"),
        rabbitmq=rmq,
        active_backend=broker.backend_name,
        connection_error=broker.last_error,
    )


@router.get("/broker", response_model=BrokerConfigOut)
def get_broker_config():
    cfg = admin_settings_table.get(Q.id == BROKER_CONFIG_ID) or {"id": BROKER_CONFIG_ID, "type": "internal", "rabbitmq": {}}
    return _mask_broker(cfg)


@router.put("/broker", response_model=BrokerConfigOut)
def set_broker_config(config: BrokerConfig):
    existing = admin_settings_table.get(Q.id == BROKER_CONFIG_ID) or {}
    existing_rmq = existing.get("rabbitmq", {})

    new_rmq = config.rabbitmq.model_dump()
    # keep-unless-changed for the password, same pattern as other secrets
    if not new_rmq.get("password"):
        new_rmq["password"] = existing_rmq.get("password", "")

    record = {"id": BROKER_CONFIG_ID, "type": config.type.value, "rabbitmq": new_rmq}
    if existing:
        admin_settings_table.update(record, Q.id == BROKER_CONFIG_ID)
    else:
        admin_settings_table.insert(record)

    log_event("info", f"Message broker configuration set to '{config.type.value}' (restart required to take effect)")
    result = _mask_broker(record)
    result.connection_error = None
    return result


# ---------- Configuration export / import (orgs, events, integrations) ----------
EXPORT_VERSION = 1


@router.get("/export")
def export_configuration():
    """
    Exports the full admin configuration - Salesforce orgs, event configs,
    integrations, alerts, rules, uploaded processor scripts (including their
    actual code), and every Admin Configuration setting (DSSClient,
    Langflow, Email/SMTP, message broker, processing mode) - as a single
    JSON bundle for backup/migration to another instance.

    Deliberately NOT included: local user accounts/password hashes. User
    management is treated as a separate identity concern from application
    configuration - re-importing accounts across environments (especially
    password hashes) is a different kind of risk than restoring integration
    settings, so it's left out of this bundle on purpose.

    SECURITY NOTE: this bundle includes credentials in plaintext - org
    secrets (client secret, password, security token), integration secrets
    (API keys, webhook signing secrets), DSSClient/Langflow API keys, SMTP
    password, and RabbitMQ password - because an export that couldn't
    restore working connections wouldn't be useful as a backup. Treat the
    downloaded file exactly like a credentials backup: store it securely,
    don't email it around, and delete it once it's no longer needed.
    """
    from ..database import orgs_table, event_configs_table, integrations_table, alerts_table, rules_table, processors_table
    from .. import processors as proc_module
    from ..models import now_ts

    processors_export = []
    for p in processors_table.all():
        record = dict(p)
        record["code"] = proc_module.read_processor_code(p["id"])
        processors_export.append(record)

    return {
        "version": EXPORT_VERSION,
        "exported_at": now_ts(),
        "orgs": orgs_table.all(),
        "event_configs": event_configs_table.all(),
        "integrations": integrations_table.all(),
        "alerts": alerts_table.all(),
        "rules": rules_table.all(),
        "processors": processors_export,
        "admin_settings": admin_settings_table.all(),  # dss_client, langflow, email_settings, broker_config, processing_mode
    }


@router.post("/import")
async def import_configuration(bundle: dict):
    """
    Imports a bundle produced by /export. Records are upserted by their
    original `id` (overwriting any existing record with the same id), which
    preserves cross-references between event configs, their routed publish
    channels/integrations/alerts, and alert->integration links. Triggers a
    CometD resync afterward so imported orgs/channels connect immediately.

    Message broker and uvicorn/server settings are NOT applied live even
    though `admin_settings` includes the broker config record - like manual
    changes to that setting, it takes effect on the next restart (see Admin
    Configuration -> Message broker).
    """
    from ..database import orgs_table, event_configs_table, integrations_table, alerts_table, rules_table, processors_table, Q as _Q
    from .. import processors as proc_module
    from ..cometd_client import cometd_manager

    def _upsert(table, rows):
        count = 0
        for row in rows:
            if table.get(_Q.id == row["id"]):
                table.update(row, _Q.id == row["id"])
            else:
                table.insert(row)
            count += 1
        return count

    counts = {
        "orgs": _upsert(orgs_table, bundle.get("orgs", [])),
        "event_configs": _upsert(event_configs_table, bundle.get("event_configs", [])),
        "integrations": _upsert(integrations_table, bundle.get("integrations", [])),
        "alerts": _upsert(alerts_table, bundle.get("alerts", [])),
        "rules": _upsert(rules_table, bundle.get("rules", [])),
        "admin_settings": _upsert(admin_settings_table, bundle.get("admin_settings", [])),
    }

    processor_count = 0
    for p in bundle.get("processors", []):
        code = p.pop("code", "")
        error = proc_module.validate_syntax(code) if code else None
        if error:
            log_event("warning", f"Skipped importing processor '{p.get('name')}': invalid Python ({error})")
            continue
        if code:
            proc_module.save_processor_file(p["id"], code)
        if processors_table.get(_Q.id == p["id"]):
            processors_table.update(p, _Q.id == p["id"])
        else:
            processors_table.insert(p)
        processor_count += 1
    counts["processors"] = processor_count

    log_event("info", f"Configuration imported: {counts}")
    await cometd_manager.sync()
    return {"detail": "Import complete", "counts": counts}
