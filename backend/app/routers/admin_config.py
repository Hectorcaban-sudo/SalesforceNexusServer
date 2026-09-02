from fastapi import APIRouter, Depends

from ..auth import require_role
from ..database import admin_settings_table, Q
from ..models import (
    DSSClientConfigUpdate, DSSClientConfigOut, ProcessingModeConfig, BrokerConfig, BrokerConfigOut,
    LangflowConfigUpdate, LangflowConfigOut, EmailSettingsUpdate, EmailSettingsOut,
)
from ..logging_config import log_event
from ..broker import broker, BROKER_CONFIG_ID

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
    Exports Salesforce orgs, event configs, and integrations as a single JSON
    bundle for backup/migration to another instance.

    SECURITY NOTE: this bundle includes org credentials (client secret,
    password, security token) and integration secrets (API keys, webhook
    signing secrets) in plaintext, because an export that couldn't restore
    working connections wouldn't be useful as a backup. Treat the downloaded
    file exactly like a credentials backup: store it securely, don't email
    it around, and delete it once it's no longer needed.
    """
    from ..database import orgs_table, event_configs_table, integrations_table
    from ..models import now_ts

    return {
        "version": EXPORT_VERSION,
        "exported_at": now_ts(),
        "orgs": orgs_table.all(),
        "event_configs": event_configs_table.all(),
        "integrations": integrations_table.all(),
    }


@router.post("/import")
async def import_configuration(bundle: dict):
    """
    Imports a bundle produced by /export. Records are upserted by their
    original `id` (overwriting any existing record with the same id), which
    preserves cross-references between event configs, their routed publish
    channels, and their routed integrations. Triggers a CometD resync
    afterward so imported orgs/channels connect immediately.
    """
    from ..database import orgs_table, event_configs_table, integrations_table, Q as _Q
    from ..cometd_client import cometd_manager

    counts = {"orgs": 0, "event_configs": 0, "integrations": 0}

    for org in bundle.get("orgs", []):
        if orgs_table.get(_Q.id == org["id"]):
            orgs_table.update(org, _Q.id == org["id"])
        else:
            orgs_table.insert(org)
        counts["orgs"] += 1

    for cfg in bundle.get("event_configs", []):
        if event_configs_table.get(_Q.id == cfg["id"]):
            event_configs_table.update(cfg, _Q.id == cfg["id"])
        else:
            event_configs_table.insert(cfg)
        counts["event_configs"] += 1

    for integ in bundle.get("integrations", []):
        if integrations_table.get(_Q.id == integ["id"]):
            integrations_table.update(integ, _Q.id == integ["id"])
        else:
            integrations_table.insert(integ)
        counts["integrations"] += 1

    log_event("info", f"Configuration imported: {counts}")
    await cometd_manager.sync()
    return {"detail": "Import complete", "counts": counts}
