"""Per-sink circuit breaker. Open skips that sink; other sinks still run."""
import time
from collections import defaultdict
from .config import settings

_state = defaultdict(lambda: {"fails": 0, "opened_at": 0.0})


def is_open(sink_id: str) -> bool:
    s = _state[sink_id]
    if s["opened_at"] and (time.time() - s["opened_at"]) < settings.circuit_open_seconds:
        return True
    if s["opened_at"] and (time.time() - s["opened_at"]) >= settings.circuit_open_seconds:
        s["fails"] = 0
        s["opened_at"] = 0.0
    return False


def record_success(sink_id: str) -> None:
    _state[sink_id] = {"fails": 0, "opened_at": 0.0}


def record_failure(sink_id: str) -> None:
    s = _state[sink_id]
    s["fails"] += 1
    if s["fails"] >= settings.circuit_fail_threshold:
        s["opened_at"] = time.time()


def snapshot() -> dict:
    now = time.time()
    out = {}
    for k, s in _state.items():
        out[k] = {
            "fails": s["fails"],
            "open": bool(s["opened_at"] and (now - s["opened_at"]) < settings.circuit_open_seconds),
        }
    return out
