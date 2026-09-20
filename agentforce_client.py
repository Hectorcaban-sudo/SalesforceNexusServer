#!/usr/bin/env python3
"""
Salesforce Agentforce Agent API client + interactive chat CLI.

Docs:
  https://developer.salesforce.com/docs/ai/agentforce/guide/agent-api-get-started.html
  https://developer.salesforce.com/docs/ai/agentforce/guide/agent-api-examples.html

Setup
-----
    pip install requests

    export SF_ACCESS_TOKEN="eyJ0bmsi..."                    # token you already minted
    export SF_AGENT_ID="0XxXXXXXXXXXXXXXXX"                 # agent ID (not the Default Agentforce agent)
    export SF_MY_DOMAIN_URL="your-org.my.salesforce.com"    # My Domain URL, NOT *.lightning.force.com
    # export SF_GOV_CLOUD=true                              # Government Cloud orgs (api.gov.salesforce.com)

Usage
-----
    python agentforce_client.py                     # interactive chat, streaming
    python agentforce_client.py --no-stream         # interactive chat, synchronous
    python agentforce_client.py -m "Show me my open cases"   # one-shot

As a library
------------
    from agentforce_client import AgentforceClient

    with AgentforceClient(token, "your-org.my.salesforce.com") as client:
        client.start_session(agent_id)
        print(client.send_message("Hello"))
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

import requests

COMMERCIAL_BASE_URL = "https://api.salesforce.com"
GOV_CLOUD_BASE_URL = "https://api.gov.salesforce.com"
API_PREFIX = "/einstein/ai-agent/v1"


class AgentAPIError(Exception):
    """Raised when the Agent API returns a non-2xx response."""

    def __init__(self, status_code: int, message: str, body: Any = None):
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.body = body


class AgentforceClient:
    """Thin wrapper around the Agentforce Agent API (session lifecycle + messaging)."""

    def __init__(
        self,
        access_token: str,
        my_domain_url: str,
        *,
        gov_cloud: bool = False,
        base_url: Optional[str] = None,
        timeout: int = 60,
    ):
        if not access_token:
            raise ValueError("access_token is required")
        if not my_domain_url:
            raise ValueError("my_domain_url is required")

        self.access_token = access_token
        self.my_domain_url = self._normalize_domain(my_domain_url)
        self.base_url = (base_url or (GOV_CLOUD_BASE_URL if gov_cloud else COMMERCIAL_BASE_URL)).rstrip("/")
        self.timeout = timeout

        self.session_id: Optional[str] = None
        self._sequence_id = 0
        self._http = requests.Session()

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        """Accept 'org.my.salesforce.com' or 'https://org.my.salesforce.com/' -> 'https://org.my.salesforce.com'."""
        domain = domain.strip().rstrip("/")
        if not domain.startswith(("http://", "https://")):
            domain = f"https://{domain}"
        return domain

    def _headers(self, accept: str = "application/json") -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": accept,
        }

    def _url(self, path: str) -> str:
        return f"{self.base_url}{API_PREFIX}{path}"

    @staticmethod
    def _raise_for_error(resp: requests.Response) -> None:
        if resp.ok:
            return
        try:
            body: Any = resp.json()
        except ValueError:
            body = resp.text
        hint = ""
        if resp.status_code == 401:
            hint = " (token expired/invalid, or missing scopes: api, chatbot_api, sfap_api)"
        raise AgentAPIError(resp.status_code, f"{resp.reason}{hint}: {body}", body)

    def _require_session(self) -> str:
        if not self.session_id:
            raise RuntimeError("No active session. Call start_session() first.")
        return self.session_id

    def _next_sequence_id(self) -> int:
        self._sequence_id += 1
        return self._sequence_id

    # ------------------------------------------------------------ session calls

    def start_session(
        self,
        agent_id: str,
        *,
        bypass_user: bool = True,
        variables: Optional[list[dict[str, Any]]] = None,
        external_session_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Start a session with an agent. Returns the full response (includes the greeting in `messages`).

        bypass_user=True  -> run as the agent-assigned user (right for client-credentials tokens)
        bypass_user=False -> run as the user tied to the token
        variables         -> optional agent variables, passed through as-is
                             (see .../guide/agent-api-variables.html)
        """
        payload: dict[str, Any] = {
            "externalSessionKey": external_session_key or str(uuid.uuid4()),
            "instanceConfig": {"endpoint": self.my_domain_url},
            "streamingCapabilities": {"chunkTypes": ["Text"]},
            "bypassUser": bypass_user,
        }
        if variables:
            payload["variables"] = variables

        resp = self._http.post(
            self._url(f"/agents/{agent_id}/sessions"),
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        self._raise_for_error(resp)
        data = resp.json()

        self.session_id = data["sessionId"]
        self._sequence_id = 0
        return data

    def end_session(self, reason: str = "UserRequest") -> Optional[dict[str, Any]]:
        """End the current session (no-op if there isn't one)."""
        if not self.session_id:
            return None
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "x-session-end-reason": reason,
        }
        resp = self._http.delete(
            self._url(f"/sessions/{self.session_id}"),
            headers=headers,
            timeout=self.timeout,
        )
        self.session_id = None
        self._raise_for_error(resp)
        try:
            return resp.json()
        except ValueError:
            return None

    # -------------------------------------------------------------- messaging

    def _message_body(self, text: str) -> dict[str, Any]:
        return {"message": {"sequenceId": self._next_sequence_id(), "type": "Text", "text": text}}

    def send_message_raw(self, text: str) -> dict[str, Any]:
        """Synchronous send; returns the full JSON response."""
        session_id = self._require_session()
        resp = self._http.post(
            self._url(f"/sessions/{session_id}/messages"),
            headers=self._headers(),
            json=self._message_body(text),
            timeout=self.timeout,
        )
        self._raise_for_error(resp)
        return resp.json()

    def send_message(self, text: str) -> str:
        """Synchronous send; returns the agent's reply text."""
        return self.extract_text(self.send_message_raw(text))

    def stream_message(self, text: str) -> Iterator[dict[str, Any]]:
        """
        Streaming send (server-sent events). Yields each parsed event as a dict, e.g.:

            {"message": {"type": "ProgressIndicator", "message": "Working on it", ...}, ...}
            {"message": {"type": "TextChunk", "message": "Here", ...}, ...}
            {"message": {"type": "Inform", "message": "<full reply>", ...}, ...}
            {"message": {"type": "EndOfTurn", ...}, ...}

        The generator stops after EndOfTurn (or when the server closes the stream).
        """
        session_id = self._require_session()
        resp = self._http.post(
            self._url(f"/sessions/{session_id}/messages/stream"),
            headers=self._headers(accept="text/event-stream"),
            json=self._message_body(text),
            timeout=self.timeout,
            stream=True,
        )
        try:
            self._raise_for_error(resp)
            resp.encoding = "utf-8"
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue  # skip blanks, "event:" / "id:" lines, comments
                raw = line[len("data:"):].strip()
                if not raw or raw == "[DONE]":
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                yield event
                if self.event_type(event) == "EndOfTurn":
                    break
        finally:
            resp.close()

    def submit_feedback(self, feedback_id: str, feedback: str = "GOOD", text: str = "") -> None:
        """Submit feedback ('GOOD' / 'BAD') for a reply, using the `feedbackId` from an Inform message."""
        session_id = self._require_session()
        body: dict[str, Any] = {"feedbackId": feedback_id, "feedback": feedback}
        if text:
            body["text"] = text
        resp = self._http.post(
            self._url(f"/sessions/{session_id}/feedback"),
            headers=self._headers(),
            json=body,
            timeout=self.timeout,
        )
        self._raise_for_error(resp)  # 201 on success

    # ---------------------------------------------------------- response utils

    @staticmethod
    def event_type(event: dict[str, Any]) -> Optional[str]:
        """Type of a streaming event (handles both {"message": {...}} and {"messages": [...]} shapes)."""
        msg = event.get("message")
        if isinstance(msg, dict):
            return msg.get("type")
        msgs = event.get("messages")
        if isinstance(msgs, list) and msgs:
            return msgs[0].get("type")
        return None

    @staticmethod
    def extract_text(response: dict[str, Any]) -> str:
        """Join the text of all messages in a sync response."""
        parts = [m.get("message", "") for m in response.get("messages", []) if m.get("message")]
        return "\n".join(parts)

    @staticmethod
    def extract_citations(response: dict[str, Any]) -> list[dict[str, Any]]:
        """Collect `citedReferences` from a sync response's Inform messages."""
        cites: list[dict[str, Any]] = []
        for m in response.get("messages", []):
            cites.extend(m.get("citedReferences") or [])
        return cites

    # ------------------------------------------------------- context manager

    def __enter__(self) -> "AgentforceClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        try:
            self.end_session()
        except Exception as e:  # don't mask the original exception
            print(f"[warn] failed to end session cleanly: {e}", file=sys.stderr)
        self._http.close()


# ====================================================================== CLI


def _print_stream(client: AgentforceClient, text: str) -> None:
    """Stream a reply to stdout, printing text chunks as they arrive."""
    got_chunks = False
    for event in client.stream_message(text):
        msg = event.get("message") if isinstance(event.get("message"), dict) else {}
        etype = client.event_type(event)

        if etype == "ProgressIndicator":
            print(f"  [{msg.get('message', 'working')}...]", file=sys.stderr, flush=True)
        elif etype == "TextChunk":
            if not got_chunks:
                print("Agent: ", end="", flush=True)
                got_chunks = True
            print(msg.get("message", ""), end="", flush=True)
        elif etype == "ValidationFailureChunk":
            # Per the docs: discard chunks rendered so far and show only the new content.
            print("\n  [response failed validation; discarding streamed text]", file=sys.stderr)
            got_chunks = False
        elif etype == "Inform":
            # Full message. If no chunks were streamed (or they were discarded), show it now.
            if not got_chunks:
                print(f"Agent: {msg.get('message', '')}", end="", flush=True)
                got_chunks = True
        elif etype == "EndOfTurn":
            break
    print()


def _print_sync(client: AgentforceClient, text: str) -> None:
    response = client.send_message_raw(text)
    print(f"Agent: {client.extract_text(response)}")
    for cite in client.extract_citations(response):
        print(f"  source: {cite.get('value')}")


def main() -> int:
    p = argparse.ArgumentParser(description="Chat with a Salesforce Agentforce agent via the Agent API.")
    p.add_argument("--token", default=os.getenv("SF_ACCESS_TOKEN"), help="Access token (env: SF_ACCESS_TOKEN)")
    p.add_argument("--agent-id", default=os.getenv("SF_AGENT_ID"), help="Agent ID (env: SF_AGENT_ID)")
    p.add_argument("--domain", default=os.getenv("SF_MY_DOMAIN_URL"), help="My Domain URL (env: SF_MY_DOMAIN_URL)")
    p.add_argument("--base-url", default=os.getenv("SF_API_BASE_URL"),
                   help="Override API base URL, e.g. the `api_instance_url` from your token response")
    p.add_argument("--gov", action="store_true",
                   default=os.getenv("SF_GOV_CLOUD", "").lower() in ("1", "true", "yes"),
                   help="Government Cloud: use api.gov.salesforce.com (env: SF_GOV_CLOUD)")
    p.add_argument("--no-stream", action="store_true", help="Use the synchronous endpoint instead of streaming")
    p.add_argument("--run-as-token-user", action="store_true",
                   help="Set bypassUser=false (run as the user tied to the token instead of the agent user)")
    p.add_argument("-m", "--message", help="Send a single message and exit")
    args = p.parse_args()

    missing = [n for n, v in (("--token / SF_ACCESS_TOKEN", args.token),
                              ("--agent-id / SF_AGENT_ID", args.agent_id),
                              ("--domain / SF_MY_DOMAIN_URL", args.domain)) if not v]
    if missing:
        p.error("missing required: " + ", ".join(missing))

    send = _print_sync if args.no_stream else _print_stream

    try:
        with AgentforceClient(args.token, args.domain, gov_cloud=args.gov, base_url=args.base_url) as client:
            start = client.start_session(args.agent_id, bypass_user=not args.run_as_token_user)
            print(f"[session {client.session_id} started]")
            greeting = client.extract_text(start)
            if greeting:
                print(f"Agent: {greeting}")

            if args.message:
                send(client, args.message)
                return 0

            print("Type 'exit' or 'quit' to end the session.\n")
            while True:
                try:
                    user_input = input("You: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit"):
                    break
                send(client, user_input)
                print()
        print("[session ended]")
        return 0
    except AgentAPIError as e:
        print(f"API error: {e}", file=sys.stderr)
        return 1
    except requests.RequestException as e:
        print(f"Network error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
