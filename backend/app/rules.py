"""
Rule engine: a validation gate for deciding *whether* an event should be
processed at all, using GoRules' open-source "Zen Engine" (JSON Decision
Model / JDM) instead of code. A JDM decision graph is plain JSON data
(nodes + edges - decision tables, expressions, switch nodes, etc.) rather
than executable code, so unlike uploaded processor scripts, evaluating a
rule is NOT run in a subprocess - the Zen Engine's evaluator only
interprets declarative decision logic, it cannot execute arbitrary code or
make network/filesystem calls, so there's no meaningful sandboxing concern
here the way there is for uploaded Python scripts.

This is deliberately NOT a processing mode (it doesn't replace DSSClient/
Langflow/custom scripts/local) - it's a gate that runs before whichever of
those actually processes the event. See worker.py:evaluate_rule_gate() and
its use in inbound_worker().

Rules are authored as JDM JSON - the easiest way is GoRules' free online
visual editor (https://editor.gorules.io): build a decision table/graph
there, export the JSON, and paste/upload it here. The graph's input is the
Salesforce event payload; its output must include a boolean `process` field
(true/omitted = continue processing, false = skip this event).
"""
import time
from typing import Optional

import zen

from .database import rules_table, Q
from .logging_config import log_event


def save_rule(rule_id: str, name: str, description: str, jdm: dict):
    record = {
        "id": rule_id, "name": name, "description": description, "jdm": jdm,
        "uploaded_at": time.time(), "last_status": None, "last_run_at": None, "last_error": None,
    }
    rules_table.insert(record)
    return record


def get_rule(rule_id: str) -> Optional[dict]:
    return rules_table.get(Q.id == rule_id)


def validate_jdm(jdm: dict) -> Optional[str]:
    """Returns an error message if the JDM content doesn't even parse/build
    as a valid decision graph, or None if it looks structurally fine."""
    import json
    try:
        engine = zen.ZenEngine()
        engine.create_decision(json.dumps(jdm))
        return None
    except Exception as exc:  # noqa: BLE001
        return str(exc)


def evaluate_rule(rule_id: str, payload: dict) -> dict:
    """Evaluates a stored JDM decision graph against `payload` and returns
    its output. Raises RuntimeError with a descriptive message on any
    failure (rule not found, invalid graph, or the graph itself raising -
    e.g. a "Custom Node" or expression referencing a missing field)."""
    import json

    rule = rules_table.get(Q.id == rule_id)
    if not rule:
        raise RuntimeError(f"Rule not found for id '{rule_id}'")

    start = time.time()
    try:
        engine = zen.ZenEngine()
        decision = engine.create_decision(json.dumps(rule["jdm"]))
        outcome = decision.evaluate(payload)
    except Exception as exc:  # noqa: BLE001
        rules_table.update({"last_status": "error", "last_run_at": time.time(), "last_error": str(exc)}, Q.id == rule_id)
        raise RuntimeError(f"Rule evaluation failed: {exc}") from exc

    duration_ms = round((time.time() - start) * 1000)
    rules_table.update({"last_status": "ok", "last_run_at": time.time(), "last_error": None}, Q.id == rule_id)
    log_event("info", f"Rule '{rule['name']}' evaluated in {duration_ms}ms", rule_id=rule_id)

    # Zen Engine wraps the actual decision output in {"result": ..., "performance": ...}
    return outcome.get("result", outcome) if isinstance(outcome, dict) else outcome


EXAMPLE_JDM = {
    "contentType": "application/vnd.gorules.decision",
    "nodes": [
        {"id": "input1", "name": "Request", "type": "inputNode", "position": {"x": 0, "y": 0}},
        {"id": "output1", "name": "Response", "type": "outputNode", "position": {"x": 500, "y": 0}},
        {
            "id": "table1", "name": "Processing gate", "type": "decisionTableNode",
            "position": {"x": 250, "y": 0},
            "content": {
                "hitPolicy": "first",
                "inputs": [{"id": "in1", "name": "Amount", "field": "amount"}],
                "outputs": [
                    # The "process" field is the gate convention this engine looks for:
                    # true/omitted = let the event continue to normal processing,
                    # false = skip it entirely (never processed or published).
                    {"id": "out1", "name": "process", "field": "process"},
                    {"id": "out2", "name": "reason", "field": "reason"},
                ],
                "rules": [
                    {"in1": ">1000", "out1": "false", "out2": "\"Amount exceeds the threshold for automatic processing\""},
                    {"in1": "", "out1": "true", "out2": "\"Within threshold\""},
                ],
            },
        },
    ],
    "edges": [
        {"id": "e1", "sourceId": "input1", "targetId": "table1", "type": "edge"},
        {"id": "e2", "sourceId": "table1", "targetId": "output1", "type": "edge"},
    ],
}
