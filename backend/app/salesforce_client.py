"""
Thin Salesforce REST API client used to:
  1. Authenticate against a configured org (username/password/security-token
     flow, or client-credentials flow) and obtain an access token + instance URL.
  2. Publish platform events back to Salesforce via the sObject REST endpoint.

Multiple orgs are supported concurrently - each org keeps its own cached
session (token + instance_url) which is refreshed on 401 responses.
"""
import time
import requests
from typing import Optional, Dict
from .logging_config import log_event


class SalesforceAuthError(Exception):
    pass


class SalesforceSession:
    def __init__(self, org: dict):
        self.org = org
        self.access_token: Optional[str] = None
        self.instance_url: Optional[str] = None
        self.obtained_at: float = 0

    def is_valid(self) -> bool:
        return bool(self.access_token and self.instance_url)


class SalesforceClient:
    """Manages one authenticated session per Salesforce org id."""

    def __init__(self):
        self._sessions: Dict[str, SalesforceSession] = {}

    def _token_url(self, org: dict) -> str:
        return f"{org['login_url'].rstrip('/')}/services/oauth2/token"

    def login(self, org: dict) -> SalesforceSession:
        auth_type = org.get("auth_type", "password")
        data = {
            "client_id": org.get("client_id", ""),
            "client_secret": org.get("client_secret", ""),
        }
        if auth_type == "password":
            data.update(
                {
                    "grant_type": "password",
                    "username": org.get("username", ""),
                    "password": f"{org.get('password', '')}{org.get('security_token', '') or ''}",
                }
            )
        elif auth_type == "client_credentials":
            data.update({"grant_type": "client_credentials"})
        else:
            raise SalesforceAuthError(
                f"Auth type '{auth_type}' requires a JWT bearer flow which must be "
                "configured with a signed assertion; not implemented in this build."
            )

        try:
            resp = requests.post(self._token_url(org), data=data, timeout=15)
        except requests.RequestException as exc:
            raise SalesforceAuthError(f"Network error contacting Salesforce: {exc}") from exc

        if resp.status_code != 200:
            raise SalesforceAuthError(
                f"Salesforce login failed ({resp.status_code}): {resp.text[:300]}"
            )

        body = resp.json()
        session = SalesforceSession(org)
        session.access_token = body["access_token"]
        session.instance_url = body["instance_url"]
        session.obtained_at = time.time()
        self._sessions[org["id"]] = session
        log_event("info", f"Authenticated to Salesforce org '{org['name']}'", org_id=org["id"])
        return session

    def get_session(self, org: dict, force_refresh: bool = False) -> SalesforceSession:
        session = self._sessions.get(org["id"])
        if session and session.is_valid() and not force_refresh:
            return session
        return self.login(org)

    def publish_platform_event(self, org: dict, channel: str, payload: dict) -> dict:
        """
        Publish a platform event. `channel` may be given either as the API name
        ('My_Event__e') or the streaming channel form ('/event/My_Event__e').
        """
        event_api_name = channel.split("/")[-1]
        session = self.get_session(org)
        url = f"{session.instance_url}/services/data/v{org.get('api_version', '60.0')}/sobjects/{event_api_name}/"
        headers = {
            "Authorization": f"Bearer {session.access_token}",
            "Content-Type": "application/json",
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=15)

        if resp.status_code == 401:
            # token expired mid-flight - refresh once and retry
            session = self.get_session(org, force_refresh=True)
            headers["Authorization"] = f"Bearer {session.access_token}"
            resp = requests.post(url, json=payload, headers=headers, timeout=15)

        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Failed to publish event '{event_api_name}' to org '{org['name']}': "
                f"{resp.status_code} {resp.text[:300]}"
            )
        return resp.json()


sf_client = SalesforceClient()
