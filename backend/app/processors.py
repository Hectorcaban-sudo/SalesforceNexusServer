"""
Uploadable custom payload processors.

Admins can upload a .py file that becomes an alternative to the built-in
DSSClient/local processing in `worker.py:process_payload()`. Selection of
which processing mode is active lives in the `admin_settings` table
(`processing_mode` record) so it's configured the same way as DSSClient.

SECURITY NOTE: uploaded scripts are executed as a real Python subprocess with
the same OS-level permissions as the server process. This is intentionally
isolated from the server's own memory (it cannot read secrets already loaded
into the running app, mutate live objects, or crash the server directly),
but it is NOT a security sandbox - it can still read/write the filesystem
and make network calls with whatever permissions the host process has.
Treat uploading a processor script exactly like deploying new server code:
admin-role only, and only from sources you trust.

Contract for an uploaded script:
  - Read a single JSON object from stdin (the event payload)
  - Print a single JSON object to stdout (the result to publish back)
  - Print any log/diagnostic messages to stderr - every line is mirrored
    into the System Logs page (tagged with this processor's name),
    regardless of whether the run succeeds or fails
  - A non-zero exit code, or invalid JSON on stdout, is treated as a
    processing failure
  - Must finish within PROCESSOR_TIMEOUT_SECONDS or it is killed and treated
    as a failure
"""
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

EXAMPLE_TEMPLATE = '''"""
Example Salesforce Nexus AI Server payload processor.

Contract: read one JSON object from stdin, print one JSON object to stdout.
A non-zero exit code, invalid JSON on stdout, or exceeding the timeout is
treated as a processing failure.

Logging: print any diagnostic/log messages to stderr (not stdout - stdout is
reserved for the JSON result). Every stderr line is automatically mirrored
into the Salesforce Nexus AI Server System Logs page, tagged with this
processor's name, whether the run succeeds or fails.

Context: two environment variables give you access to the rest of the
system without needing any imports:
  - NEXUS_ORG: the Salesforce org that triggered this event (login_url,
    auth_type, client_id/secret, username/password/security_token,
    api_version) - "{}" if there's no org context (e.g. a manual test run
    with no org selected).
  - NEXUS_ADMIN_CONFIG: {"dss_client": {...}, "langflow": {...},
    "email": {...}, "processing_mode": {...}} - the same admin configuration
    the built-in processing modes use, including credentials, so you can
    call out to Dataiku DSS, Langflow, or send your own email (via smtplib
    and the "email" settings) directly from your script.
"""
import sys
import os
import json


def process(payload: dict) -> dict:
    print(f"Received payload with keys: {list(payload.keys())}", file=sys.stderr)

    org = json.loads(os.environ.get("NEXUS_ORG", "{}"))
    admin_config = json.loads(os.environ.get("NEXUS_ADMIN_CONFIG", "{}"))
    if org:
        print(f"Triggered by org: {org.get('name')} ({org.get('login_url')})", file=sys.stderr)

    return {
        "status": "ok",
        "summary": "Processed by custom uploaded script",
        "echo": payload,
    }


if __name__ == "__main__":
    input_payload = json.loads(sys.stdin.read() or "{}")
    result = process(input_payload)
    print(json.dumps(result))
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


def _log_processor_stderr(processor_id: str, name: str, stderr: str):
    if not stderr:
        return
    logger_name = f"nexus.processor.{name or processor_id}"
    for line in stderr.strip().splitlines():
        if line.strip():
            log_event("info", line.strip(), logger_name=logger_name, processor_id=processor_id)


def _build_processor_env(org_id: Optional[str]) -> dict:
    from .database import orgs_table, Q as _Q
    from .routers.admin_config import (
        get_dss_client_config_raw, get_langflow_config_raw, get_email_settings_raw, get_processing_mode_raw,
    )

    org = orgs_table.get(_Q.id == org_id) if org_id else None
    admin_config = {
        "dss_client": get_dss_client_config_raw(),
        "langflow": get_langflow_config_raw(),
        "email": get_email_settings_raw(),
        "processing_mode": get_processing_mode_raw(),
    }
    env = dict(os.environ)
    env["NEXUS_ORG"] = json.dumps(org or {})
    env["NEXUS_ADMIN_CONFIG"] = json.dumps(admin_config)
    return env


class ProcessorCancelled(RuntimeError):
    pass


def run_processor(processor_id: str, payload: dict, org_id: Optional[str] = None, cancel_check=None) -> dict:
    path = _script_path(processor_id)
    if not path.exists():
        raise RuntimeError(f"Processor script file not found for id '{processor_id}'")

    record = processors_table.get(Q.id == processor_id)
    name = record["name"] if record else processor_id

    start = time.time()
    proc = subprocess.Popen(
        [sys.executable, str(path)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", env=_build_processor_env(org_id),
    )
    proc.stdin.write(json.dumps(payload))
    proc.stdin.close()

    cancelled = False
    while proc.poll() is None:
        if cancel_check is not None and cancel_check():
            proc.kill()
            proc.wait()
            cancelled = True
            break
        if time.time() - start > PROCESSOR_TIMEOUT_SECONDS:
            proc.kill()
            proc.wait()
            stderr = proc.stderr.read()
            _log_processor_stderr(processor_id, name, stderr or "")
            raise RuntimeError(f"Processor timed out after {PROCESSOR_TIMEOUT_SECONDS}s")
        time.sleep(0.1)

    stdout = proc.stdout.read()
    stderr = proc.stderr.read()
    duration_ms = round((time.time() - start) * 1000)
    _log_processor_stderr(processor_id, name, stderr)

    if cancelled:
        log_event("warning", f"Processor '{name}' cancelled after {duration_ms}ms", processor_id=processor_id)
        raise ProcessorCancelled(f"Processor '{name}' was cancelled")

    if proc.returncode != 0:
        raise RuntimeError(f"Processor exited with code {proc.returncode}: {stderr.strip()[:500]}")

    try:
        result = json.loads(stdout.strip() or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Processor did not print valid JSON to stdout: {stdout.strip()[:300]}") from exc

    log_event("info", f"Processor '{processor_id}' ran in {duration_ms}ms", processor_id=processor_id)
    return result
