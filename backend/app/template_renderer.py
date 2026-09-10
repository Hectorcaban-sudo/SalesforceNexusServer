"""
Jinja2-based body templating for outbound integrations.

Allows each integration (Teams, Slack, Email, Webhook, Custom API, …) to
optionally define a custom message body via a Jinja2 template instead of
using the hard-coded default.

Context variables available in every template:

    id, org_id, org_name, channel, direction, status, error, created_at
    payload   – original Salesforce event payload (dict)
    result    – processor / AI output (dict)
    t         – the full transaction dict (convenience alias)

body_mode values:
    "default"  – ignore template, use the sender's built-in card/text
    "template" – render body_template with the context above
"""
from __future__ import annotations

import json
from typing import Any, Optional, Union

from jinja2 import Environment, BaseLoader, select_autoescape, TemplateError

# Restricted environment – no filesystem access, no arbitrary Python imports.
_env = Environment(
    loader=BaseLoader(),
    autoescape=select_autoescape(enabled_extensions=()),
    trim_blocks=True,
    lstrip_blocks=True,
)

# Helpful filters
_env.filters["tojson"] = lambda v, **kw: json.dumps(v, default=str, **kw)
_env.filters["default"] = lambda v, d="": v if v is not None else d


def render_template(template_str: str, context: dict[str, Any]) -> str:
    """Render a Jinja2 template string. Raises TemplateError on syntax problems."""
    template = _env.from_string(template_str)
    return template.render(**context)


def build_integration_body(
    cfg: dict,
    transaction: dict,
) -> Optional[Union[dict, str]]:
    """
    Decide what body an integration sender should use.

    Returns
    -------
    None
        Caller should fall back to its hard-coded default.
    dict
        Already-parsed JSON object (ready for ``json=`` in requests).
    str
        Raw string body (useful for plain-text email, etc.).
    """
    mode = (cfg.get("body_mode") or "default").lower()
    template_str = cfg.get("body_template")

    if mode != "template" or not template_str:
        return None

    context = {
        "id": transaction.get("id"),
        "org_id": transaction.get("org_id"),
        "org_name": transaction.get("org_name"),
        "channel": transaction.get("channel"),
        "direction": transaction.get("direction"),
        "status": transaction.get("status"),
        "error": transaction.get("error"),
        "created_at": transaction.get("created_at"),
        "payload": transaction.get("payload") or {},
        "result": transaction.get("result") or {},
        "t": transaction,
    }

    try:
        rendered = render_template(template_str, context)
    except TemplateError as exc:
        raise RuntimeError(f"Integration body template error: {exc}") from exc

    # Most card formats are JSON – try to parse, otherwise return raw string
    try:
        return json.loads(rendered)
    except (json.JSONDecodeError, TypeError):
        return rendered
