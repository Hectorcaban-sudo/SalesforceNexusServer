from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
import uuid
import time


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now_ts() -> float:
    return time.time()


# ---------- Auth / RBAC ----------
class Role(str, Enum):
    admin = "admin"        # full access: orgs, events, users, integrations, admin config
    operator = "operator"  # can manage orgs/events/reprocess transactions, no user/integration admin
    viewer = "viewer"      # read-only: dashboard, transactions, logs


class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    username: str
    role: str = "admin"
    auth_provider: str = "local"   # local | sso
    created_at: Optional[float] = None


class UserCreate(BaseModel):
    username: str
    password: str
    role: Role = Role.viewer


class UserUpdate(BaseModel):
    role: Optional[Role] = None
    password: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# ---------- Salesforce Org ----------
class AuthType(str, Enum):
    password = "password"          # username/password/security-token flow
    client_credentials = "client_credentials"
    jwt_bearer = "jwt_bearer"


class OrgBase(BaseModel):
    name: str
    description: Optional[str] = ""
    login_url: str = "https://login.salesforce.com"
    auth_type: AuthType = AuthType.password
    client_id: str = ""
    client_secret: str = ""
    username: Optional[str] = None
    password: Optional[str] = None
    security_token: Optional[str] = None
    api_version: str = "60.0"
    active: bool = True


class OrgCreate(OrgBase):
    pass


class OrgUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    login_url: Optional[str] = None
    auth_type: Optional[AuthType] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    security_token: Optional[str] = None
    api_version: Optional[str] = None
    active: Optional[bool] = None


class OrgOut(OrgBase):
    id: str
    status: str = "disconnected"       # disconnected | connecting | connected | error
    last_error: Optional[str] = None
    last_connected_at: Optional[float] = None


# ---------- Event configuration ----------
class EventDirection(str, Enum):
    subscribe = "subscribe"
    publish = "publish"


class EventConfigBase(BaseModel):
    org_id: str
    channel: str                       # e.g. /event/My_Custom_Event__e
    direction: EventDirection
    enabled: bool = True
    description: Optional[str] = ""
    # optional mapping used when publishing: which broker topic feeds this channel
    broker_topic: Optional[str] = "default"
    # Routing (only meaningful on direction="subscribe" entries): which
    # publish-direction event configs and which integrations should receive
    # the processed result of events received on this channel. Empty lists
    # fall back to legacy behavior (first enabled publish channel for the
    # org, and integrations auto-matched by their own org/trigger rules).
    route_publish_channel_ids: List[str] = Field(default_factory=list)
    route_integration_ids: List[str] = Field(default_factory=list)
    route_alert_ids: List[str] = Field(default_factory=list)
    # Per-event processor override (only meaningful on direction="subscribe"
    # entries): pins this channel to a specific processing mode/processor
    # instead of using the global Admin Configuration default. None/omitted
    # means "use the global default".
    processing_mode: Optional[str] = None      # "local" | "dss_client" | "custom_script" | "langflow" | "rule_engine"
    processor_id: Optional[str] = None          # the uploaded processor's id (custom_script) or rule's id (rule_engine)
    # Only meaningful on direction="subscribe" entries. When False, receiving
    # and processing an event on this channel does NOT automatically publish
    # the result back to Salesforce - it's still processed, and any routed
    # (or globally auto-matched) integrations/alerts still fire off the
    # "processed" transaction, but nothing is queued onto the outbound
    # publish path. Defaults to True (existing behavior).
    auto_publish: bool = True


class EventConfigCreate(EventConfigBase):
    pass


class EventConfigUpdate(BaseModel):
    channel: Optional[str] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None
    broker_topic: Optional[str] = None
    route_publish_channel_ids: Optional[List[str]] = None
    route_integration_ids: Optional[List[str]] = None
    route_alert_ids: Optional[List[str]] = None
    processing_mode: Optional[str] = None
    processor_id: Optional[str] = None
    auto_publish: Optional[bool] = None


class EventConfigOut(EventConfigBase):
    id: str


# ---------- Transactions ----------
class TransactionStatus(str, Enum):
    received = "received"
    queued = "queued"
    processing = "processing"
    processed = "processed"
    publishing = "publishing"
    published = "published"
    failed = "failed"


class TransactionOut(BaseModel):
    id: str
    org_id: str
    org_name: Optional[str] = None
    direction: EventDirection
    channel: str
    status: TransactionStatus
    payload: dict
    result: Optional[dict] = None
    error: Optional[str] = None
    attempts: int = 0
    parent_transaction_id: Optional[str] = None
    created_at: float
    updated_at: float


# ---------- Manual publish ----------
class PublishEventRequest(BaseModel):
    org_id: str
    channel: str
    payload: dict


# ---------- Admin configuration: DSSClient ----------
class DSSClientConfig(BaseModel):
    url: str = ""
    project_name: str = ""
    llm: str = ""
    api_key: str = ""


class DSSClientConfigOut(BaseModel):
    url: str = ""
    project_name: str = ""
    llm: str = ""
    api_key: str = ""          # masked when returned to the browser
    configured: bool = False   # true once a URL has been set


class DSSClientConfigUpdate(BaseModel):
    url: Optional[str] = None
    project_name: Optional[str] = None
    llm: Optional[str] = None
    api_key: Optional[str] = None


# ---------- Langflow ----------
class LangflowConfig(BaseModel):
    base_url: str = ""       # e.g. http://localhost:7860
    flow_id: str = ""
    api_key: str = ""
    input_field: str = "input_value"    # which field in the /run request body carries the payload
    output_path: str = ""               # optional dotted path into the response to extract; blank = best-effort auto-extract


class LangflowConfigUpdate(BaseModel):
    base_url: Optional[str] = None
    flow_id: Optional[str] = None
    api_key: Optional[str] = None
    input_field: Optional[str] = None
    output_path: Optional[str] = None


class LangflowConfigOut(BaseModel):
    base_url: str = ""
    flow_id: str = ""
    api_key: str = ""          # masked when returned to the browser
    input_field: str = "input_value"
    output_path: str = ""
    configured: bool = False


# ---------- Email (SMTP) settings ----------
class EmailSettings(BaseModel):
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True           # STARTTLS
    from_address: str = ""


class EmailSettingsUpdate(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    use_tls: Optional[bool] = None
    from_address: Optional[str] = None


class EmailSettingsOut(BaseModel):
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""          # masked when returned to the browser
    use_tls: bool = True
    from_address: str = ""
    configured: bool = False


# ---------- Custom payload processors (uploaded Python scripts) ----------
class ProcessorOut(BaseModel):
    id: str
    name: str
    filename: str
    uploaded_at: float
    last_status: Optional[str] = None
    last_run_at: Optional[float] = None
    last_error: Optional[str] = None


class ProcessingMode(str, Enum):
    local = "local"
    dss_client = "dss_client"
    custom_script = "custom_script"
    langflow = "langflow"
    rule_engine = "rule_engine"


class ProcessingModeConfig(BaseModel):
    mode: ProcessingMode = ProcessingMode.local
    active_processor_id: Optional[str] = None


class ProcessorTestRequest(BaseModel):
    payload: dict = Field(default_factory=lambda: {"Message__c": "test payload"})
    org_id: Optional[str] = None   # optional: test with a real org's settings available via NEXUS_ORG


# ---------- Rule engine (GoRules JSON Decision Model / "Zen Engine") ----------
class RuleCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    jdm: dict     # the JSON Decision Model decision graph (nodes/edges), e.g. exported from https://editor.gorules.io


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    jdm: Optional[dict] = None


class RuleOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = ""
    uploaded_at: float
    last_status: Optional[str] = None
    last_run_at: Optional[float] = None
    last_error: Optional[str] = None
    # jdm is intentionally omitted from the list/summary response (can be
    # large); fetch it via GET /api/rules/{id}/jdm when needed (e.g. to edit).


class RuleTestRequest(BaseModel):
    payload: dict = Field(default_factory=lambda: {"Message__c": "test payload"})


# ---------- Message broker configuration ----------
class BrokerType(str, Enum):
    internal = "internal"
    rabbitmq = "rabbitmq"


class RabbitMQSettings(BaseModel):
    host: str = "localhost"
    port: int = 5672
    username: str = "guest"
    password: str = ""
    vhost: str = "/"
    use_tls: bool = False


class BrokerConfig(BaseModel):
    type: BrokerType = BrokerType.internal
    rabbitmq: RabbitMQSettings = Field(default_factory=RabbitMQSettings)


class BrokerConfigOut(BaseModel):
    type: str = "internal"
    rabbitmq: RabbitMQSettings = Field(default_factory=RabbitMQSettings)
    active_backend: str = "internal"          # which backend is actually running right now
    connection_error: Optional[str] = None     # set if the last RabbitMQ connect attempt failed


# ---------- Outbound integrations (fan-out sinks) ----------
class IntegrationType(str, Enum):
    webhook = "webhook"
    slack = "slack"
    teams = "teams"
    snowflake = "snowflake"
    bigquery = "bigquery"
    custom_api = "custom_api"
    email = "email"


class IntegrationTrigger(str, Enum):
    always = "always"
    on_success = "on_success"
    on_failure = "on_failure"


class IntegrationBase(BaseModel):
    name: str
    type: IntegrationType
    enabled: bool = True
    trigger: IntegrationTrigger = IntegrationTrigger.always
    org_id: Optional[str] = None   # None = applies to every org
    config: dict = Field(default_factory=dict)
    # When true, this sink is excluded from normal per-transaction fan-out
    # (dispatch_integrations) and can only be reached via an Alert rule that
    # explicitly points at it. Prevents a dedicated alert-delivery channel
    # from also firing on every ordinary transaction because its trigger/org
    # happen to match (e.g. trigger="always", org=None matches everything).
    alert_only: bool = False


class IntegrationCreate(IntegrationBase):
    pass


class IntegrationUpdate(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    trigger: Optional[IntegrationTrigger] = None
    org_id: Optional[str] = None
    config: Optional[dict] = None
    alert_only: Optional[bool] = None


class IntegrationOut(IntegrationBase):
    id: str
    last_status: Optional[str] = None
    last_run_at: Optional[float] = None
    last_error: Optional[str] = None
    last_result: Optional[dict] = None


# ---------- Alerts ----------
class AlertScope(str, Enum):
    transaction = "transaction"                      # a transaction (any direction) reached a terminal state - see `trigger`
    connection_failed = "connection_failed"         # a Salesforce org's CometD connection went to "error"
    integration_failed = "integration_failed"       # an integration sink dispatch raised an exception
    broker_degraded = "broker_degraded"             # configured RabbitMQ broker failed to connect at startup


class AlertTrigger(str, Enum):
    always = "always"            # fire on every terminal transaction (published/processed/failed)
    on_success = "on_success"    # fire only when the transaction succeeded (published or processed with no error)
    on_failure = "on_failure"    # fire only when the transaction failed (default - matches prior behavior)


class AlertBase(BaseModel):
    name: str
    scope: AlertScope
    enabled: bool = True
    org_id: Optional[str] = None       # None = applies to every org (ignored for broker_degraded)
    integration_id: str                # which configured integration sink delivers this alert
    # Only meaningful when scope == "transaction". Other scopes are inherently
    # single-outcome events (a connection/integration/broker failure) with no
    # natural "success" counterpart, so trigger is ignored for those.
    trigger: AlertTrigger = AlertTrigger.on_failure


class AlertCreate(AlertBase):
    pass


class AlertUpdate(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    org_id: Optional[str] = None
    integration_id: Optional[str] = None
    trigger: Optional[AlertTrigger] = None


class AlertOut(AlertBase):
    id: str
    last_fired_at: Optional[float] = None
    last_status: Optional[str] = None
    last_error: Optional[str] = None


# ---------- Logs ----------
class LogEntryOut(BaseModel):
    id: str
    timestamp: float
    level: str
    logger: str
    message: str
    context: Optional[dict] = None
