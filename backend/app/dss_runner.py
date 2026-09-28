"""Dataiku DSS LLM calls. Phase A: cached in-process client + optional subprocess."""
import json
import subprocess
import sys
import threading
import time
from typing import Optional

from .config import settings
from .logging_config import log_event

DSS_TIMEOUT_SECONDS = getattr(settings, "dss_timeout_seconds", None) or settings.processor_timeout_seconds

_lock = threading.Lock()
_cache_key = None
_client = None
_agent = None


class DSSClientCancelled(RuntimeError):
    pass


def _config():
    from .routers.admin_config import get_dss_client_config_raw
    cfg = get_dss_client_config_raw()
    if not cfg.get("url"):
        raise RuntimeError("DSSClient is not configured (no URL set in Admin Configuration)")
    return cfg


def _get_agent(cfg: dict):
    global _cache_key, _client, _agent
    key = (cfg.get("url"), cfg.get("project_name"), cfg.get("llm"), cfg.get("api_key"))
    with _lock:
        if _agent is not None and _cache_key == key:
            return _agent
        import dataikuapi
        log_event("info", "DSS: creating client (cold)")
        _client = dataikuapi.DSSClient(cfg.get("url"), cfg.get("api_key"), no_check_certificate=True)
        _agent = _client.get_project(cfg["project_name"]).get_llm(cfg["llm"])
        _cache_key = key
        return _agent


def _complete(cfg: dict, payload: dict) -> dict:
    agent = _get_agent(cfg)
    conversation_id = payload.get("Conversation_Id__c")
    completion = agent.new_completion()
    completion.with_message(payload.get("User_Message__c", "") or "")
    response = completion.execute()
    if not getattr(response, "success", True):
        error_detail = getattr(response, "text", None) or "DSS completion returned success=False"
        raise RuntimeError(f"DSS completion failed: {error_detail}")
    return {
        "Conversation_Id__c": conversation_id,
        "Status__c": "Ok",
        "Payload_Json__c": json.dumps({"replyText": getattr(response, "text", "")}),
    }


def run_dss_client_inprocess(payload: dict) -> dict:
    return _complete(_config(), payload)


def warmup_dss() -> dict:
    cfg = _config()
    ping = {"Conversation_Id__c": "nexus-warmup", "User_Message__c": "ping"}
    start = time.time()
    result = _complete(cfg, ping)
    log_event("info", f"DSS warmup finished in {time.time() - start:.1f}s")
    return result


def run_dss_client_subprocess(payload: dict, cancel_check=None) -> dict:
    cfg = _config()
    stdin_payload = json.dumps({"config": cfg, "payload": payload})
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


def run_dss_client(payload: dict, cancel_check=None) -> dict:
    if getattr(settings, "dss_use_subprocess", False):
        return run_dss_client_subprocess(payload, cancel_check=cancel_check)
    return run_dss_client_inprocess(payload)


def _run_in_subprocess():
    try:
        request = json.loads(sys.stdin.read() or "{}")
        print(json.dumps(_complete(request["config"], request["payload"])))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _run_in_subprocess()
