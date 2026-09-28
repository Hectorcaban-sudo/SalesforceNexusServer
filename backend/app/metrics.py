"""In-process counters. Exposed as Prometheus text on GET /metrics."""
import time
from collections import defaultdict

_counters = defaultdict(int)
_last = {}


def inc(name: str, n: int = 1) -> None:
    _counters[name] += n


def set_gauge(name: str, value: float) -> None:
    _last[name] = value


def observe_latency(name: str, seconds: float) -> None:
    inc(f"{name}_seconds_count")
    _counters[f"{name}_seconds_sum"] += int(seconds * 1000)


def render_prometheus() -> str:
    lines = ["# TYPE nexus_info gauge", "nexus_info 1"]
    for k, v in sorted(_counters.items()):
        lines.append(f"nexus_{k} {v}")
    for k, v in sorted(_last.items()):
        lines.append(f"nexus_{k} {v}")
    lines.append(f"nexus_scrape_timestamp {int(time.time())}")
    return "\n".join(lines) + "\n"
