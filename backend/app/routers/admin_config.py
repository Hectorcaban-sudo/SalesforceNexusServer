from fastapi import APIRouter, Depends

from ..auth import require_role
from ..database import admin_settings_table, Q
from ..models import DSSClientConfigUpdate, DSSClientConfigOut, ProcessingModeConfig
from ..logging_config import log_event

router = APIRouter(prefix="/api/admin-config", tags=["admin-config"], dependencies=[Depends(require_role("admin"))])

DSS_CLIENT_ID = "dss_client"
PROCESSING_MODE_ID = "processing_mode"


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
