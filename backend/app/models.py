from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
import uuid
import time


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now_ts() -> float:
    return time.time()


# ---------- Auth ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    username: str
    role: str = "admin"


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


class EventConfigCreate(EventConfigBase):
    pass


class EventConfigUpdate(BaseModel):
    channel: Optional[str] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None
    broker_topic: Optional[str] = None


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
    created_at: float
    updated_at: float


# ---------- Manual publish ----------
class PublishEventRequest(BaseModel):
    org_id: str
    channel: str
    payload: dict


# ---------- Logs ----------
class LogEntryOut(BaseModel):
    id: str
    timestamp: float
    level: str
    logger: str
    message: str
    context: Optional[dict] = None
