from fastapi import APIRouter, Depends, HTTPException
from typing import List

from ..auth import get_current_user, require_role
from ..database import rules_table, Q
from ..models import RuleCreate, RuleUpdate, RuleOut, RuleTestRequest, new_id
from ..logging_config import log_event
from .. import rules as rules_module

router = APIRouter(prefix="/api/rules", tags=["rules"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=List[RuleOut])
def list_rules():
    return rules_table.all()


@router.get("/example")
def get_example_jdm():
    """Returns a starter JDM decision graph so the admin UI can offer a
    "load example" action."""
    return {"jdm": rules_module.EXAMPLE_JDM}


@router.get("/{rule_id}/jdm")
def get_rule_jdm(rule_id: str):
    rule = rules_table.get(Q.id == rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")
    return {"jdm": rule["jdm"]}


@router.post("", response_model=RuleOut, dependencies=[Depends(require_role("admin"))])
def create_rule(rule: RuleCreate):
    error = rules_module.validate_jdm(rule.jdm)
    if error:
        raise HTTPException(400, f"Invalid decision graph: {error}")
    rule_id = new_id()
    record = rules_module.save_rule(rule_id, rule.name, rule.description or "", rule.jdm)
    log_event("info", f"Rule '{rule.name}' created", rule_id=rule_id)
    return record


@router.put("/{rule_id}", response_model=RuleOut, dependencies=[Depends(require_role("admin"))])
def update_rule(rule_id: str, updates: RuleUpdate):
    existing = rules_table.get(Q.id == rule_id)
    if not existing:
        raise HTTPException(404, "Rule not found")

    data = {k: v for k, v in updates.model_dump().items() if v is not None}
    if "jdm" in data:
        error = rules_module.validate_jdm(data["jdm"])
        if error:
            raise HTTPException(400, f"Invalid decision graph: {error}")

    rules_table.update(data, Q.id == rule_id)
    log_event("info", f"Rule '{existing['name']}' updated", fields=list(data.keys()))
    return rules_table.get(Q.id == rule_id)


@router.delete("/{rule_id}", dependencies=[Depends(require_role("admin"))])
def delete_rule(rule_id: str):
    existing = rules_table.get(Q.id == rule_id)
    if not existing:
        raise HTTPException(404, "Rule not found")
    rules_table.remove(Q.id == rule_id)
    log_event("warning", f"Rule '{existing['name']}' deleted")
    return {"detail": "deleted"}


@router.post("/{rule_id}/test", dependencies=[Depends(require_role("admin"))])
def test_rule(rule_id: str, req: RuleTestRequest):
    if not rules_table.get(Q.id == rule_id):
        raise HTTPException(404, "Rule not found")
    try:
        result = rules_module.evaluate_rule(rule_id, req.payload)
        return {"detail": "Rule evaluated successfully", "result": result}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))
