"""Dataiku DSS LLM calls. In-process path streams chunks into System Logs."""
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
        log_event("info", "DSS: creating client (cold)", logger_name="nexus.dss")
        _client = dataikuapi.DSSClient(cfg.get("url"), cfg.get("api_key"), no_check_certificate=True)
        _agent = _client.get_project(cfg["project_name"]).get_llm(cfg["llm"])
        _cache_key = key
        return _agent


def _log(message: str, transaction_id: Optional[str] = None):
    extra = {"transaction_id": transaction_id} if transaction_id else {}
    log_event("info", message, logger_name="nexus.dss", **extra)


def _result(conversation_id, text: str) -> dict:
    return {
        "Conversation_Id__c": conversation_id,
        "Status__c": "Ok",
        "Payload_Json__c": json.dumps({"replyText": text or ""}),
    }


def _complete_blocking(completion):
    response = completion.execute()
    if not getattr(response, "success", True):
        error_detail = getattr(response, "text", None) or "DSS completion returned success=False"
        raise RuntimeError(f"DSS completion failed: {error_detail}")
    return getattr(response, "text", "") or ""


def _complete_streamed(completion, transaction_id: Optional[str] = None) -> str:
    try:
        from dataikuapi.dss.llm import DSSLLMStreamedCompletionChunk, DSSLLMStreamedCompletionFooter
    except Exception:
        DSSLLMStreamedCompletionChunk = None
        DSSLLMStreamedCompletionFooter = None
    if not hasattr(completion, "execute_streamed"):
        return _complete_blocking(completion)
    parts = []
    buf = []
    last = time.time()
    _log("DSS stream started", transaction_id)
    for chunk in completion.execute_streamed():
        data = getattr(chunk, "data", None) or {}
        is_text = DSSLLMStreamedCompletionChunk is None or isinstance(chunk, DSSLLMStreamedCompletionChunk)
        is_footer = DSSLLMStreamedCompletionFooter is not None and isinstance(chunk, DSSLLMStreamedCompletionFooter)
        if is_footer:
            if not getattr(data, "get", lambda *_: None)("success") and data.get("success") is False:
                raise RuntimeError(f"DSS stream failed: {data}")
            continue
        if not is_text:
            continue
        piece = data.get("text") or ""
        if not piece:
            continue
        parts.append(piece)
        buf.append(piece)
        if time.time() - last >= 1.5 or sum(len(x) for x in buf) >= 240:
            _log("".join(buf)[:500], transaction_id)
            buf = []
            last = time.time()
    if buf:
        _log("".join(buf)[:500], transaction_id)
    text = "".join(parts)
    _log(f"DSS stream complete ({len(text)} chars)", transaction_id)
    return text


def _complete(cfg: dict, payload: dict, transaction_id: Optional[str] = None) -> dict:
    agent = _get_agent(cfg)
    conversation_id = payload.get("Conversation_Id__c")
    completion = agent.new_completion()
    completion.with_message(payload.get("User_Message__c", "") or "")
    try:
        text = _complete_streamed(completion, transaction_id)
    except Exception as exc:
        _log(f"DSS stream unavailable, using execute(): {exc}", transaction_id)
        text = _complete_blocking(completion)
    return _result(conversation_id, text)


def run_dss_client_inprocess(payload: dict, transaction_id: Optional[str] = None) -> dict:
    return _complete(_config(), payload, transaction_id)


def warmup_dss() -> dict:
    cfg = _config()
    ping = {"Conversation_Id__c": "nexus-warmup", "User_Message__c": "ping"}
    start = time.time()
    result = _complete(cfg, ping)
    log_event("info", f"DSS warmup finished in {time.time() - start:.1f}s", logger_name="nexus.dss")
    return result


def run_dss_client_subprocess(payload: dict, cancel_check=None, transaction_id: Optional[str] = None) -> dict:
    cfg = _config()
    stdin_payload = json.dumps({"config": cfg, "payload": payload, "transaction_id": transaction_id})
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
            proc.kill(); proc.wait(); cancelled = True; break
        if time.time() - start > DSS_TIMEOUT_SECONDS:
            proc.kill(); proc.wait()
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


def run_dss_client(payload: dict, cancel_check=None, transaction_id: Optional[str] = None) -> dict:
    if getattr(settings, "dss_use_subprocess", False):
        return run_dss_client_subprocess(payload, cancel_check=cancel_check, transaction_id=transaction_id)
    return run_dss_client_inprocess(payload, transaction_id)


def _run_in_subprocess():
    try:
        request = json.loads(sys.stdin.read() or "{}")
        print(json.dumps(_complete(request["config"], request["payload"], request.get("transaction_id"))))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    _run_in_subprocess()
