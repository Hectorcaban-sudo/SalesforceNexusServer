from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel

from ..auth import get_current_user, require_role
from ..database import integrations_table, Q
from ..models import IntegrationCreate, IntegrationUpdate, IntegrationOut, new_id, now_ts
from ..logging_config import log_event
from ..template_renderer import build_integration_body

router = APIRouter(prefix="/api/integrations", tags=["integrations"], dependencies=[Depends(get_current_user)])


class TemplatePreviewRequest(BaseModel):
    body_template: str
    # Optional overrides so the UI can preview against a custom sample
    sample_payload: Optional[dict] = None
    sample_result: Optional[dict] = None
    sample_status: Optional[str] = "published"


class TemplatePreviewResponse(BaseModel):
    ok: bool
    rendered: Optional[object] = None   # dict or str
    error: Optional[str] = None


def _mask(cfg: dict) -> dict:
    masked = dict(cfg)
    masked_config = dict(masked.get("config", {}))
    for secret_field in ("secret", "api_key", "password", "auth_header", "credentials_json"):
        if masked_config.get(secret_field):
            masked_config[secret_field] = "••••••••"
    masked["config"] = masked_config
    return masked


@router.get("", response_model=List[IntegrationOut])
def list_integrations():
    return [_mask(i) for i in integrations_table.all()]


@router.post("", response_model=IntegrationOut, dependencies=[Depends(require_role("admin"))])
def create_integration(integration: IntegrationCreate):
    record = integration.model_dump()
    record.update({"id": new_id(), "last_status": None, "last_run_at": None, "last_error": None, "last_result": None})
    integrations_table.insert(record)
    log_event("info", f"Integration '{record['name']}' ({record['type']}) created")
    return _mask(record)


@router.put("/{integration_id}", response_model=IntegrationOut, dependencies=[Depends(require_role("admin"))])
def update_integration(integration_id: str, updates: IntegrationUpdate):
    existing = integrations_table.get(Q.id == integration_id)
    if not existing:
        raise HTTPException(404, "Integration not found")
    data = {k: v for k, v in updates.model_dump().items() if v is not None}
    if "config" in data:
        # merge rather than replace so masked/omitted secret fields aren't wiped out
        merged_config = dict(existing.get("config", {}))
        merged_config.update(data["config"])
        data["config"] = merged_config
    integrations_table.update(data, Q.id == integration_id)
    log_event("info", f"Integration '{existing['name']}' updated", fields=list(data.keys()))
    return _mask(integrations_table.get(Q.id == integration_id))


@router.delete("/{integration_id}", dependencies=[Depends(require_role("admin"))])
def delete_integration(integration_id: str):
    existing = integrations_table.get(Q.id == integration_id)
    if not existing:
        raise HTTPException(404, "Integration not found")
    integrations_table.remove(Q.id == integration_id)
    log_event("warning", f"Integration '{existing['name']}' deleted")
    return {"detail": "deleted"}


@router.post("/preview-template", response_model=TemplatePreviewResponse, dependencies=[Depends(require_role("admin"))])
def preview_template(req: TemplatePreviewRequest):
    """Render a body_template against a sample transaction so the admin UI can
    show a live preview while the operator edits the Jinja2 template.
    Does not send anything — pure render only.
    """
    sample = {
        "id": "preview-" + new_id()[:8],
        "org_id": "preview-org",
        "org_name": "Acme Corp",
        "direction": "subscribe",
        "channel": "Opportunity_Update__e",
        "status": req.sample_status or "published",
        "payload": req.sample_payload or {
            "Message__c": "Sample Salesforce event",
            "Subject__c": "Q3 Pipeline Review",
            "OpportunityName__c": "Acme Corp – Renewal",
            "Amount__c": 125000,
            "StageName__c": "Negotiation",
        },
        "result": req.sample_result or {
            "status": "ok",
            "summary": "High-confidence renewal opportunity",
            "insight": "Customer expanded usage 40% this quarter; recommend executive sponsor outreach.",
        },
        "error": None if (req.sample_status or "published") != "failed" else "Sample processing error",
        "created_at": now_ts(),
    }
    cfg = {"body_mode": "template", "body_template": req.body_template}
    try:
        rendered = build_integration_body(cfg, sample)
        return TemplatePreviewResponse(ok=True, rendered=rendered)
    except Exception as exc:  # noqa: BLE001
        return TemplatePreviewResponse(ok=False, error=str(exc))


@router.post("/{integration_id}/test", dependencies=[Depends(require_role("admin"))])
def test_integration(integration_id: str):
    cfg = integrations_table.get(Q.id == integration_id)
    if not cfg:
        raise HTTPException(404, "Integration not found")

    test_transaction = {
        "id": "test-" + new_id(),
        "org_id": cfg.get("org_id") or "test-org",
        "org_name": "Test Org",
        "direction": "publish",
        "channel": "Test__e",
        "status": "published",
        "payload": {
            "Message__c": "This is a test event from Salesforce Nexus AI Server",
            "Subject__c": "Test Subject",
            "OpportunityName__c": "Acme Corp – Renewal",
            "Amount__c": 125000,
        },
        "result": {
            "status": "ok",
            "summary": "Test AI summary",
            "insight": "This is a sample processor result for template testing.",
        },
        "error": None,
        "created_at": now_ts(),
    }
    # run just this one sink synchronously so we can report success/failure immediately
    from ..integrations import _SENDERS, _record_result  # noqa: PLC0415
    sender = _SENDERS.get(cfg["type"])
    if sender is None:
        raise HTTPException(400, f"Unknown integration type '{cfg['type']}'")
    try:
        result = sender(cfg, test_transaction)
        _record_result(integration_id, "ok", result=result)
        return {"detail": "Test event sent successfully", "result": result}
    except Exception as exc:  # noqa: BLE001
        _record_result(integration_id, "error", str(exc))
        raise HTTPException(400, f"Test failed: {exc}")
