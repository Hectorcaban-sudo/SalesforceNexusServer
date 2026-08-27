"""Helpers for creating/updating transaction records (the audit trail the
admin dashboard displays for every event that flows through the system)."""
from typing import Optional
from .database import transactions_table, Q
from .models import new_id, now_ts


def record_transaction(
    org_id: str,
    org_name: str,
    direction: str,
    channel: str,
    status: str,
    payload: dict,
    result: Optional[dict] = None,
    error: Optional[str] = None,
) -> dict:
    record = {
        "id": new_id(),
        "org_id": org_id,
        "org_name": org_name,
        "direction": direction,
        "channel": channel,
        "status": status,
        "payload": payload,
        "result": result,
        "error": error,
        "attempts": 0,
        "created_at": now_ts(),
        "updated_at": now_ts(),
    }
    transactions_table.insert(record)
    return record


def update_transaction(transaction_id: str, **fields):
    fields["updated_at"] = now_ts()
    transactions_table.update(fields, Q.id == transaction_id)


def get_transaction(transaction_id: str) -> Optional[dict]:
    return transactions_table.get(Q.id == transaction_id)
