from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
import uuid
import time


def new_id() -> str:
    return uuid.uuid4().hex[:12]


# ---------- Projects (customer / solution boundary) ----------
class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = ""
    enabled: bool = True


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None


class ProjectOut(ProjectBase):
    id: str
    created_at: Optional[str] = None


class ProjectMemberOut(BaseModel):
    id: str
    project_id: str
    user_id: str
    username: Optional[str] = None
    role: str = "project_admin"  # project_admin | operator | viewer


class ProjectMemberCreate(BaseModel):
    user_id: str
    role: str = "project_admin"


class FlowTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    project_id: Optional[str] = None  # None = global library
    graph: dict = Field(default_factory=dict)
    placeholders: bool = True


class FlowTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    project_id: Optional[str] = None
    graph: Optional[dict] = None


class FlowTemplateOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = ""
    project_id: Optional[str] = None
    graph: dict = Field(default_factory=dict)
    placeholders: bool = True
    created_at: Optional[str] = None
    source_event_id: Optional[str] = None


class FlowDryRunRequest(BaseModel):
    payload: dict = Field(default_factory=dict)
    graph: Optional[dict] = None  # unsaved canvas; else event.flow_graph




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
    failed_login_count: int = 0
    locked_until: Optional[float] = None


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
    project_id: Optional[str] = None
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
    project_id: Optional[str] = None
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
    processing_mode: Optional[str] = None      # "local" | "dss_client" | "custom_script" | "langflow"
    processor_id: Optional[str] = None          # the uploaded processor's id, used when processing_mode == "custom_script"
    # Only meaningful on direction="subscribe" entries. When set, this rule
    # is evaluated against every event received on this channel BEFORE any
    # processing happens - the rule's decision graph must produce a boolean
    # `process` field in its output (true = continue processing normally,
    # false = skip - the event is received and recorded but never processed
    # or published). This is a gate, not a processing mode: it decides
    # *whether* an event gets processed, using the same rule engine that
    # used to (incorrectly) double as a processing mode itself.
    rule_id: Optional[str] = None
    # Only meaningful on direction="subscribe" entries. When False, receiving
    # and processing an event on this channel does NOT automatically publish
    # the result back to Salesforce - it's still processed, and any routed
    # (or globally auto-matched) integrations/alerts still fire off the
    # "processed" transaction, but nothing is queued onto the outbound
    # publish path. Defaults to True (existing behavior).
    auto_publish: bool = True
    result_transform_template: Optional[str] = None  # Jinja2 transform of result before publish
    # Schema validation (subscribe): JSON Schema + optional sample payload
    sample_payload: Optional[dict] = None
    payload_schema: Optional[dict] = None  # JSON Schema object
    schema_validation_mode: str = "off"  # off | warn | reject
    # Publish mapping: Salesforce field name -> Jinja2 over {payload, result}
    publish_field_map: Optional[dict] = None
    # Visual flow designer graph {nodes, edges}. When present the worker walks it.
    flow_graph: Optional[dict] = None


class EventConfigCreate(EventConfigBase):
    pass


class EventConfigUpdate(BaseModel):
    result_transform_template: Optional[str] = None
    channel: Optional[str] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None
    broker_topic: Optional[str] = None
    route_publish_channel_ids: Optional[List[str]] = None
    route_integration_ids: Optional[List[str]] = None
    route_alert_ids: Optional[List[str]] = None
    processing_mode: Optional[str] = None
    processor_id: Optional[str] = None
    rule_id: Optional[str] = None
    auto_publish: Optional[bool] = None
    sample_payload: Optional[dict] = None
    payload_schema: Optional[dict] = None
    schema_validation_mode: Optional[str] = None
    publish_field_map: Optional[dict] = None
    flow_graph: Optional[dict] = None


class EventConfigOut(EventConfigBase):
    id: str


# ---------- Transactions ----------
class TransactionStatus(str, Enum):
    received = "received"
    queued = "queued"
    processing = "processing"
    processed = "processed"
    skipped = "skipped"          # a validation rule decided this event should not be processed
    publishing = "publishing"
    published = "published"
    failed = "failed"
    cancelled = "cancelled"       # cancelled by an admin - see "Cancelling transactions"


class TransactionOut(BaseModel):
    id: str
    org_id: str
    org_name: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    direction: EventDirection
    channel: str
    status: TransactionStatus
    payload: dict
    result: Optional[dict] = None
    error: Optional[str] = None
    attempts: int = 0
    parent_transaction_id: Optional[str] = None
    cancel_requested: bool = False   # set while an in-flight cancellation is pending - see routers/transactions.py:cancel_transaction
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


# ---------- Database backend ----------
class DatabaseConfigUpdate(BaseModel):
    database_type: str          # "sqlite" | "postgres" | "sqlserver" | "oracle"
    database_host: Optional[str] = None
    database_port: Optional[int] = None
    database_name: Optional[str] = None
    database_user: Optional[str] = None
    database_password: Optional[str] = None


class DatabaseConfigOut(BaseModel):
    database_type: str
    database_host: str
    database_port: int
    database_name: str
    database_user: str
    database_password: str = ""   # masked
    db_path: str                   # the SQLite file path, shown when database_type == "sqlite"
    env_file_writable: bool
    restart_required: bool = True


class DatabaseTestRequest(BaseModel):
    database_type: str
    database_host: Optional[str] = None
    database_port: Optional[int] = None
    database_name: Optional[str] = None
    database_user: Optional[str] = None
    database_password: Optional[str] = None


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
    sharepoint_file = "sharepoint_file"
    sharepoint_list = "sharepoint_list"


class ProcessingModeConfig(BaseModel):
    mode: ProcessingMode = ProcessingMode.local
    active_processor_id: Optional[str] = None


# ---------- SharePoint Online (GCC High) ----------
class SharePointConnectionBase(BaseModel):
    name: str
    tenant_id: str
    client_id: str
    client_secret: str = ""          # write-only on update if blank
    enabled: bool = True
    # Fixed to GCC High for this deployment; stored for forward-compat
    cloud: str = "gcchigh"


class SharePointConnectionCreate(SharePointConnectionBase):
    pass


class SharePointConnectionUpdate(BaseModel):
    name: Optional[str] = None
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    enabled: Optional[bool] = None


class SharePointConnectionOut(BaseModel):
    id: str
    name: str
    tenant_id: str
    client_id: str
    client_secret: str = "••••••••"  # always masked in API
    enabled: bool = True
    cloud: str = "gcchigh"


class SharePointFileSource(str, Enum):
    salesforce_content_version = "salesforce_content_version"
    url = "url"


class SharePointFileActionBase(BaseModel):
    name: str
    connection_id: str
    enabled: bool = True
    site_id: str = ""
    site_name: str = ""                     # optional display label when Graph browse is blocked
    drive_id: str = ""
    drive_name: str = ""                    # optional display label
    folder_path_template: str = ""          # Jinja2, e.g. "{{ year }} NBF Reports/{{ business }} Projects"
    file_name_template: str = "{{ title }}.{{ extension }}"
    create_missing_folders: bool = True
    check_in_after_upload: bool = True
    file_source: SharePointFileSource = SharePointFileSource.salesforce_content_version
    # Jinja2: resolve ContentDocumentId from any event shape
    content_document_id_template: str = "{{ payload.ContentDocumentId }}"
    # Jinja2: when file_source == url
    file_url_template: str = ""
    # Free-form SharePoint column -> Jinja2 expression
    metadata_map: dict = Field(default_factory=dict)
    # Optional: linked Salesforce record field for enrichment (Opportunity Id etc.)
    salesforce_record_id_template: str = "{{ payload.LinkedEntityId }}"
    salesforce_object: Optional[str] = "Opportunity"  # used if enrichment query needed; blank = skip


class SharePointFileActionCreate(SharePointFileActionBase):
    pass


class SharePointFileActionUpdate(BaseModel):
    name: Optional[str] = None
    connection_id: Optional[str] = None
    enabled: Optional[bool] = None
    site_id: Optional[str] = None
    site_name: Optional[str] = None
    drive_id: Optional[str] = None
    drive_name: Optional[str] = None
    folder_path_template: Optional[str] = None
    file_name_template: Optional[str] = None
    create_missing_folders: Optional[bool] = None
    check_in_after_upload: Optional[bool] = None
    file_source: Optional[SharePointFileSource] = None
    content_document_id_template: Optional[str] = None
    file_url_template: Optional[str] = None
    metadata_map: Optional[dict] = None
    salesforce_record_id_template: Optional[str] = None
    salesforce_object: Optional[str] = None


class SharePointFileActionOut(SharePointFileActionBase):
    id: str


class SharePointListOperation(str, Enum):
    create = "create"
    update = "update"
    upsert = "upsert"
    lookup = "lookup"
    delete = "delete"


class SharePointListActionBase(BaseModel):
    name: str
    connection_id: str
    enabled: bool = True
    site_id: str = ""
    site_name: str = ""
    list_id: str = ""                   # Graph list id
    list_name: str = ""
    operation: SharePointListOperation = SharePointListOperation.create
    # Jinja2 for update/delete: item id (optional if lookup is set)
    item_id_template: str = ""
    # Lookup / upsert: find item where fields/<lookup_field> equals rendered value
    lookup_field: str = ""
    lookup_value_template: str = ""
    # Free-form SharePoint field -> Jinja2
    field_map: dict = Field(default_factory=dict)


class SharePointListActionCreate(SharePointListActionBase):
    pass


class SharePointListActionUpdate(BaseModel):
    name: Optional[str] = None
    connection_id: Optional[str] = None
    enabled: Optional[bool] = None
    site_id: Optional[str] = None
    site_name: Optional[str] = None
    list_id: Optional[str] = None
    list_name: Optional[str] = None
    operation: Optional[SharePointListOperation] = None
    item_id_template: Optional[str] = None
    lookup_field: Optional[str] = None
    lookup_value_template: Optional[str] = None
    field_map: Optional[dict] = None


class SharePointListActionOut(SharePointListActionBase):
    id: str


class ProcessorTestRequest(BaseModel):
    payload: dict = Field(default_factory=lambda: {"Message__c": "test payload"})
    org_id: Optional[str] = None   # optional: test with a real org's settings available via NEXUS_ORG


# ---------- Rule engine (GoRules JSON Decision Model / "Zen Engine") ----------
class RuleCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    jdm: dict
    project_id: Optional[str] = None     # the JSON Decision Model decision graph (nodes/edges), e.g. exported from https://editor.gorules.io


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    jdm: Optional[dict] = None
    project_id: Optional[str] = None


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
    sharepoint_file = "sharepoint_file"
    sharepoint_list = "sharepoint_list"


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
    project_id: Optional[str] = None  # selected project in the UI; omitted = unscoped/shared
    config: dict = Field(default_factory=dict)
    # When true, this sink is excluded from normal per-transaction fan-out
    # (dispatch_integrations) and can only be reached via an Alert rule that
    # explicitly points at it. Prevents a dedicated alert-delivery channel
    # from also firing on every ordinary transaction because its trigger/org
    # happen to match (e.g. trigger="always", org=None matches everything).
    alert_only: bool = False
    # Optional custom body templating (Jinja2).
    # body_mode = "default"  → use the hard-coded card/text for the integration type
    # body_mode = "template" → render body_template with transaction context
    body_mode: str = "default"          # "default" | "template"
    body_template: Optional[str] = None  # Jinja2 template string (JSON or plain text)


class IntegrationCreate(IntegrationBase):
    pass


class IntegrationUpdate(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    trigger: Optional[IntegrationTrigger] = None
    org_id: Optional[str] = None
    project_id: Optional[str] = None
    config: Optional[dict] = None
    alert_only: Optional[bool] = None
    body_mode: Optional[str] = None
    body_template: Optional[str] = None


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
    project_id: Optional[str] = None   # selected project; omitted = shared / unscoped
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
    project_id: Optional[str] = None
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
