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
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from .config import DATA_DIR
from .database import processors_table, Q
from .logging_config import log_event

PROCESSORS_DIR = DATA_DIR / "processors"
PROCESSORS_DIR.mkdir(exist_ok=True)

PROCESSOR_TIMEOUT_SECONDS = 20

EXAMPLE_TEMPLATE = '''"""
Example Salesforce Nexus AI Server payload processor.

Contract: read one JSON object from stdin, print one JSON object to stdout.
A non-zero exit code, invalid JSON on stdout, or exceeding the timeout is
treated as a processing failure.

Logging: print any diagnostic/log messages to stderr (not stdout - stdout is
reserved for the JSON result). Every stderr line is automatically mirrored
into the Salesforce Nexus AI Server System Logs page, tagged with this
processor's name, whether the run succeeds or fails.
"""
import sys
import json


def process(payload: dict) -> dict:
    # Anything printed here goes to the System Logs page automatically.
    print(f"Received payload with keys: {list(payload.keys())}", file=sys.stderr)

    # Your custom logic goes here. This example just echoes the payload
    # back with a computed field, as a starting point.
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
    """Returns an error message string if the code doesn't even parse as
    valid Python, or None if it looks syntactically fine."""
    try:
        compile(code, "<uploaded processor>", "exec")
        return None
    except SyntaxError as exc:
        return f"Syntax error at line {exc.lineno}: {exc.msg}"


def save_processor_file(processor_id: str, code: str):
    _script_path(processor_id).write_text(code)


def read_processor_code(processor_id: str) -> str:
    path = _script_path(processor_id)
    return path.read_text() if path.exists() else ""


def delete_processor_file(processor_id: str):
    path = _script_path(processor_id)
    if path.exists():
        path.unlink()


def _log_processor_stderr(processor_id: str, name: str, stderr: str):
    """Custom processor scripts are expected to print their own log lines to
    stderr (stdout is reserved for the JSON result) - pipe each non-empty
    line into the system Logs page under a distinct logger name so they're
    visible and attributable to this specific processor, exactly like any
    other component's logs."""
    if not stderr:
        return
    logger_name = f"nexus.processor.{name or processor_id}"
    for line in stderr.strip().splitlines():
        if line.strip():
            log_event("info", line.strip(), logger_name=logger_name, processor_id=processor_id)


def run_processor(processor_id: str, payload: dict) -> dict:
    """Executes an uploaded processor script in an isolated subprocess and
    returns its JSON result. Raises RuntimeError with a descriptive message
    on any failure (non-zero exit, bad JSON output, or timeout). Anything
    the script prints to stderr is captured and mirrored into the system
    Logs page regardless of success or failure - see `_log_processor_stderr`."""
    path = _script_path(processor_id)
    if not path.exists():
        raise RuntimeError(f"Processor script file not found for id '{processor_id}'")

    record = processors_table.get(Q.id == processor_id)
    name = record["name"] if record else processor_id

    start = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, str(path)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=PROCESSOR_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        _log_processor_stderr(processor_id, name, exc.stderr or "")
        raise RuntimeError(f"Processor timed out after {PROCESSOR_TIMEOUT_SECONDS}s") from exc

    duration_ms = round((time.time() - start) * 1000)
    _log_processor_stderr(processor_id, name, proc.stderr)

    if proc.returncode != 0:
        raise RuntimeError(f"Processor exited with code {proc.returncode}: {proc.stderr.strip()[:500]}")

    try:
        result = json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Processor did not print valid JSON to stdout: {proc.stdout.strip()[:300]}") from exc

    log_event("info", f"Processor '{processor_id}' ran in {duration_ms}ms", processor_id=processor_id)
    return result
