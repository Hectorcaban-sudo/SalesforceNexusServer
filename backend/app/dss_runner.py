"""
Runs a Dataiku DSS LLM call in an isolated subprocess so it can be
hard-cancelled (SIGKILL), exactly like custom payload processors -
`dataikuapi.DSSClient` is a sync-only third-party SDK with no async variant,
so unlike Langflow/Salesforce (which were rewritten to native async httpx),
there's no way to make an in-process DSSClient call cancellable other than
running it somewhere that can be killed from outside: a real OS process.

This module doubles as both:
  1. A library used by worker.py (`run_dss_client`) - spawns the subprocess,
     polls for completion/cancellation/timeout.
  2. The subprocess entry point itself (the `if __name__ == "__main__"` block
     at the bottom) - reads {"config": ..., "payload": ...} JSON from stdin,
     makes the actual dataikuapi call, prints the result JSON to stdout.
"""
import json
import subprocess
import sys
import time
from typing import Optional

from .config import settings

DSS_TIMEOUT_SECONDS = settings.processor_timeout_seconds  # reuse the same configurable timeout as custom scripts


class DSSClientCancelled(RuntimeError):
    """Raised when a DSSClient call is cancelled mid-flight (subprocess
    killed) - distinct from a genuine failure, same spirit as
    processors.ProcessorCancelled."""


def run_dss_client(payload: dict, cancel_check=None) -> dict:
    """
    Runs the DSSClient call in a subprocess, polling roughly every 100ms for
    completion, a timeout, or `cancel_check()` returning True (in which case
    the subprocess is killed immediately and DSSClientCancelled is raised).
    Raises RuntimeError on any other failure (bad config, DSS error, etc).
    """
    from .routers.admin_config import get_dss_client_config_raw

    config = get_dss_client_config_raw()
    if not config.get("url"):
        raise RuntimeError("DSSClient is not configured (no URL set in Admin Configuration)")

    stdin_payload = json.dumps({"config": config, "payload": payload})

    start = time.time()
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.dss_runner"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    proc.stdin.write(stdin_payload)
    proc.stdin.close()

    cancelled = False
    while proc.poll() is None:
        if cancel_check is not None and cancel_check():
            proc.kill()
            proc.wait()
            cancelled = True
            break
        if time.time() - start > DSS_TIMEOUT_SECONDS:
            proc.kill()
            proc.wait()
            raise RuntimeError(f"DSSClient call timed out after {DSS_TIMEOUT_SECONDS}s")
        time.sleep(0.1)

    stdout = proc.stdout.read()
    stderr = proc.stderr.read()

    if cancelled:
        raise DSSClientCancelled("DSSClient call was cancelled")

    if proc.returncode != 0:
        raise RuntimeError(f"DSSClient call failed: {stderr.strip()[:500]}")

    try:
        return json.loads(stdout.strip() or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"DSSClient runner produced invalid JSON: {stdout.strip()[:300]}") from exc


def _run_in_subprocess():
    """The actual subprocess entry point - see module docstring."""
    try:
        request = json.loads(sys.stdin.read() or "{}")
        config = request["config"]
        payload = request["payload"]

        import dataikuapi  # imported lazily so the main app still runs if this optional dependency isn't installed

        conversation_id = payload.get("Conversation_Id__c")
        client = dataikuapi.DSSClient(config.get("url"), config.get("api_key"), no_check_certificate=True)
        agent = client.get_project(config["project_name"]).get_llm(config["llm"])
        completion = agent.new_completion()
        completion.with_message(payload.get("User_Message__c", ""))
        response = completion.execute()

        result = {
            "Conversation_Id__c": conversation_id,
            "Status__c": "Ok",
            "Payload_Json__c": json.dumps({"replyText": response.text}),
        }
        print(json.dumps(result))
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _run_in_subprocess()
