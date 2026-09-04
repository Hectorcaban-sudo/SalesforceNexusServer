from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional, List

from ..auth import get_current_user, require_role
from ..database import transactions_table, Q
from ..models import TransactionOut, now_ts
from ..worker import reprocess_transaction
from ..logging_config import log_event

router = APIRouter(prefix="/api/transactions", tags=["transactions"], dependencies=[Depends(get_current_user)])

TERMINAL_STATUSES = ("published", "failed", "skipped", "cancelled")


@router.get("", response_model=List[TransactionOut])
def list_transactions(
    org_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    direction: Optional[str] = None,
    limit: int = 200,
):
    rows = transactions_table.all()
    if org_id:
        rows = [r for r in rows if r["org_id"] == org_id]
    if status_filter:
        rows = [r for r in rows if r["status"] == status_filter]
    if direction:
        rows = [r for r in rows if r["direction"] == direction]
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return rows[:limit]


@router.get("/stats")
def transaction_stats():
    rows = transactions_table.all()
    total = len(rows)
    by_status = {}
    by_org = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        key = r.get("org_name") or r["org_id"]
        by_org[key] = by_org.get(key, 0) + 1
    failed = by_status.get("failed", 0)
    published = by_status.get("published", 0)
    success_rate = round((published / total) * 100, 1) if total else 100.0
    return {
        "total": total,
        "by_status": by_status,
        "by_org": by_org,
        "failed": failed,
        "published": published,
        "success_rate": success_rate,
    }


@router.post("/{transaction_id}/reprocess", dependencies=[Depends(require_role("operator"))])
async def reprocess(transaction_id: str):
    """Re-drive a single transaction back through the internal broker."""
    try:
        record = await reprocess_transaction(transaction_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"detail": "requeued", "transaction": record}


@router.post("/reprocess-failed", dependencies=[Depends(require_role("operator"))])
async def reprocess_all_failed(org_id: Optional[str] = None):
    """Bulk-requeue every transaction currently in a 'failed' state
    (optionally scoped to one org)."""
    rows = transactions_table.search(Q.status == "failed")
    if org_id:
        rows = [r for r in rows if r["org_id"] == org_id]

    requeued = []
    for r in rows:
        try:
            await reprocess_transaction(r["id"])
            requeued.append(r["id"])
        except Exception as exc:  # noqa: BLE001
            log_event("error", f"Bulk reprocess failed for transaction {r['id']}: {exc}", transaction_id=r["id"])

    return {"detail": f"requeued {len(requeued)} transaction(s)", "transaction_ids": requeued}


@router.post("/{transaction_id}/cancel", dependencies=[Depends(require_role("operator"))])
def cancel_transaction(transaction_id: str):
    """
    Cancels a transaction. What actually happens depends on how far along it
    already is:
      - "received"/"queued" (not yet picked up for processing): cancelled
        immediately - the worker checks for this the moment it would
        otherwise start work and skips it entirely.
      - "processing"/"publishing" (actively running): flags the transaction
        with `cancel_requested`. For custom-script processing this kills the
        subprocess immediately. For everything else (local/DSSClient/
        Langflow processing, and the Salesforce publish call itself) there's
        no way to abort an in-flight blocking network call, so the current
        step finishes first and the cancellation takes effect right after -
        the event will NOT proceed to publishing (if still processing) or
        won't be treated as published (if it was about to be), and no
        integrations/alerts fire for it either way.
      - Anything already in a terminal state (published/failed/skipped/
        already cancelled) can't be cancelled - 400.
    """
    record = transactions_table.get(Q.id == transaction_id)
    if not record:
        raise HTTPException(404, "Transaction not found")

    status = record["status"]
    if status in TERMINAL_STATUSES:
        raise HTTPException(400, f"Transaction is already in a terminal state ({status}) and can't be cancelled")

    if status in ("received", "queued"):
        transactions_table.update(
            {"status": "cancelled", "error": "Cancelled by admin before processing started", "updated_at": now_ts()},
            Q.id == transaction_id,
        )
        log_event("warning", f"Transaction {transaction_id} cancelled before processing started", transaction_id=transaction_id)
        return {"detail": "Transaction cancelled"}

    # Actively processing or publishing - best-effort. See docstring above
    # for exactly what "cancel" means for each processing mode.
    transactions_table.update({"cancel_requested": True, "updated_at": now_ts()}, Q.id == transaction_id)
    log_event(
        "warning",
        f"Cancellation requested for in-flight transaction {transaction_id} (status={status})",
        transaction_id=transaction_id,
    )
    return {
        "detail": (
            "Cancellation requested. A custom-script processor is killed immediately; other "
            "processing modes and the Salesforce publish call finish their current network "
            "operation first, then stop before completing the next step."
        )
    }
