"""APScheduler: cron ticks enqueue inbound messages. Walker does the work."""
from datetime import datetime
from typing import Optional

from .logging_config import log_event

_scheduler = None


async def start_scheduler():
    global _scheduler
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
    except ImportError:
        log_event("warning", "APScheduler not installed — scheduled jobs disabled")
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.start()
    await reload_jobs()
    log_event("info", "Scheduler started")


async def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


async def reload_jobs():
    if not _scheduler:
        return
    from .database import scheduled_jobs_table
    _scheduler.remove_all_jobs()
    for job in scheduled_jobs_table.all():
        if not job.get("enabled"):
            continue
        try:
            trigger = _cron_trigger(job.get("cron") or "0 2 * * *", job.get("timezone") or "UTC")
            _scheduler.add_job(
                _run_job,
                trigger=trigger,
                id=job["id"],
                args=[job["id"]],
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=900,
            )
        except Exception as exc:
            log_event("error", f"Schedule '{job.get('name')}' invalid: {exc}", job_id=job.get("id"))


def _cron_trigger(expr: str, tz: str):
    from apscheduler.triggers.cron import CronTrigger
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError("cron must have 5 fields: min hour dom mon dow")
    minute, hour, day, month, dow = parts
    return CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=dow, timezone=tz)


async def _run_job(job_id: str):
    from .database import scheduled_jobs_table, orgs_table, Q
    from . import transactions as tx
    from .broker import broker
    from .salesforce_client import sf_client
    from .models import now_ts

    job = scheduled_jobs_table.get(Q.id == job_id)
    if not job or not job.get("enabled"):
        return
    org = orgs_table.get(Q.id == job.get("org_id"))
    if not org:
        _stamp(job_id, error="Org not found")
        return
    soql = (job.get("soql") or "").strip()
    if not soql:
        _stamp(job_id, error="SOQL is empty")
        return
    try:
        data = await sf_client.soql_query(org, soql)
        records = data.get("records") or []
    except Exception as exc:
        _stamp(job_id, error=str(exc))
        log_event("error", f"Schedule SOQL failed: {exc}", job_id=job_id)
        return

    limit = int(job.get("max_records") or 500)
    records = records[:limit]
    pipe_ids = job.get("pipeline_ids") or []
    channel = f"schedule:{job_id}"
    queued = 0
    mode = job.get("mode") or "per_record"
    payloads = records if mode != "batch" else ([{"records": records, "job_id": job_id}] if records else [])
    for rec in payloads:
        payload = rec if isinstance(rec, dict) else {"record": rec}
        payload.setdefault("_schedule_job_id", job_id)
        record = tx.record_transaction(
            org_id=org["id"], org_name=org.get("name"), direction="subscribe",
            channel=channel, status="queued", payload=payload,
        )
        await broker.publish("inbound", {
            "transaction_id": record["id"], "org_id": org["id"],
            "channel": channel, "payload": payload, "pipeline_ids": pipe_ids,
        })
        queued += 1
    _stamp(job_id, last_count=queued, error=None)
    log_event("info", f"Schedule '{job.get('name')}' queued {queued} record(s)", job_id=job_id)


def _stamp(job_id: str, last_count=None, error=None):
    from .database import scheduled_jobs_table, Q
    from .models import now_ts
    data = {"last_run_at": now_ts()}
    if last_count is not None:
        data["last_count"] = last_count
    if error is not None:
        data["last_error"] = error
    elif last_count is not None:
        data["last_error"] = None
    scheduled_jobs_table.update(data, Q.id == job_id)


async def run_now(job_id: str):
    await _run_job(job_id)
