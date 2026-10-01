"""Uploadable custom payload processors."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from .config import DATA_DIR, settings
from .database import processors_table, Q
from .logging_config import log_event

PROCESSORS_DIR = DATA_DIR / "processors"
PROCESSORS_DIR.mkdir(exist_ok=True)
PROCESSOR_TIMEOUT_SECONDS = settings.processor_timeout_seconds

EXAMPLE_TEMPLATE = '''import sys, os, json

def process(payload):
    print("start", file=sys.stderr, flush=True)
    print("done", file=sys.stderr, flush=True)
    return {"status": "ok", "echo": payload}

if __name__ == "__main__":
    print(json.dumps(process(json.loads(sys.stdin.read() or "{}"))))
'''

def _script_path(processor_id: str) -> Path:
    return PROCESSORS_DIR / f"{processor_id}.py"

def validate_syntax(code: str) -> Optional[str]:
    try:
        compile(code, "<uploaded processor>", "exec")
        return None
    except SyntaxError as exc:
        return f"Syntax error at line {exc.lineno}: {exc.msg}"

def save_processor_file(processor_id: str, code: str):
    _script_path(processor_id).write_text(code, encoding="utf-8")

def read_processor_code(processor_id: str) -> str:
    path = _script_path(processor_id)
    return path.read_text(encoding="utf-8") if path.exists() else ""

def delete_processor_file(processor_id: str):
    path = _script_path(processor_id)
    if path.exists():
        path.unlink()

def _log_processor_stderr(processor_id: str, name: str, stderr: str, transaction_id: Optional[str] = None):
    if not stderr:
        return
    logger_name = f"nexus.processor.{name or processor_id}"
    extra = {"processor_id": processor_id}
    if transaction_id:
        extra["transaction_id"] = transaction_id
    for line in stderr.strip().splitlines():
        if line.strip():
            log_event("info", line.strip(), logger_name=logger_name, **extra)

def _build_processor_env(org_id: Optional[str], transaction_id: Optional[str] = None) -> dict:
    from .database import orgs_table, sharepoint_connections_table, Q as _Q
    from .routers.admin_config import (
        get_dss_client_config_raw, get_langflow_config_raw, get_email_settings_raw, get_processing_mode_raw,
    )
    org = orgs_table.get(_Q.id == org_id) if org_id else None
    project_id = (org or {}).get("project_id")
    admin_config = {
        "dss_client": get_dss_client_config_raw(),
        "langflow": get_langflow_config_raw(),
        "email": get_email_settings_raw(),
        "processing_mode": get_processing_mode_raw(),
    }
    scoped = []
    for c in sharepoint_connections_table.all():
        if not c.get("enabled", True):
            continue
        if (c.get("project_id") or None) != (project_id or None):
            continue
        scoped.append({
            "id": c.get("id"), "name": c.get("name"), "tenant_id": c.get("tenant_id"),
            "client_id": c.get("client_id"), "client_secret": c.get("client_secret"),
            "cloud": c.get("cloud") or "gcchigh", "project_id": c.get("project_id"),
        })
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["NEXUS_ORG"] = json.dumps(org or {})
    env["NEXUS_ADMIN_CONFIG"] = json.dumps(admin_config)
    env["NEXUS_SHAREPOINT"] = json.dumps(scoped)
    env["NEXUS_TRANSACTION_ID"] = transaction_id or ""
    return env

class ProcessorCancelled(RuntimeError):
    pass

def run_processor(processor_id: str, payload: dict, org_id: Optional[str] = None, cancel_check=None, transaction_id: Optional[str] = None) -> dict:
    path = _script_path(processor_id)
    if not path.exists():
        raise RuntimeError(f"Processor script file not found for id '{processor_id}'")
    record = processors_table.get(Q.id == processor_id)
    name = record["name"] if record else processor_id
    start = time.time()
    proc = subprocess.Popen(
        [sys.executable, "-u", str(path)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", env=_build_processor_env(org_id, transaction_id),
    )
    proc.stdin.write(json.dumps(payload))
    proc.stdin.close()
    cancelled = False
    while proc.poll() is None:
        if cancel_check is not None and cancel_check():
            proc.kill(); proc.wait(); cancelled = True; break
        if time.time() - start > PROCESSOR_TIMEOUT_SECONDS:
            proc.kill(); proc.wait()
            stderr = proc.stderr.read() or ""
            _log_processor_stderr(processor_id, name, stderr, transaction_id)
            last = " | ".join([ln.strip() for ln in stderr.splitlines() if ln.strip()][-8:]) or "no stderr"
            raise RuntimeError(f"Processor timed out after {PROCESSOR_TIMEOUT_SECONDS}s. Last lines: {last}")
        time.sleep(0.1)
    stdout = proc.stdout.read()
    stderr = proc.stderr.read()
    _log_processor_stderr(processor_id, name, stderr, transaction_id)
    if cancelled:
        raise ProcessorCancelled(f"Processor '{name}' was cancelled")
    if proc.returncode != 0:
        raise RuntimeError(f"Processor exited with code {proc.returncode}: {(stderr or '').strip()[:500]}")
    try:
        return json.loads(stdout.strip() or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Processor did not print valid JSON to stdout: {(stdout or '')[:300]}") from exc
