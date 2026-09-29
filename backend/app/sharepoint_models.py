"""SharePoint Pydantic models with project_id."""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SharePointConnectionBase(BaseModel):
    name: str
    tenant_id: str
    client_id: str
    client_secret: str = ""
    enabled: bool = True
    cloud: str = "gcchigh"
    project_id: Optional[str] = None


class SharePointConnectionCreate(SharePointConnectionBase):
    pass


class SharePointConnectionUpdate(BaseModel):
    name: Optional[str] = None
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    enabled: Optional[bool] = None
    project_id: Optional[str] = None


class SharePointConnectionOut(BaseModel):
    id: str
    name: str
    tenant_id: str
    client_id: str
    client_secret: str = "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
    enabled: bool = True
    cloud: str = "gcchigh"
    project_id: Optional[str] = None


class SharePointFileSource(str, Enum):
    salesforce_content_version = "salesforce_content_version"
    url = "url"


class SharePointFileActionBase(BaseModel):
    name: str
    connection_id: str
    enabled: bool = True
    project_id: Optional[str] = None
    site_id: str = ""
    site_name: str = ""
    drive_id: str = ""
    drive_name: str = ""
    folder_path_template: str = ""
    file_name_template: str = "{{ title }}.{{ extension }}"
    create_missing_folders: bool = True
    check_in_after_upload: bool = True
    file_source: SharePointFileSource = SharePointFileSource.salesforce_content_version
    content_document_id_template: str = "{{ payload.ContentDocumentId }}"
    file_url_template: str = ""
    metadata_map: dict = Field(default_factory=dict)
    salesforce_record_id_template: str = "{{ payload.LinkedEntityId }}"
    salesforce_object: Optional[str] = "Opportunity"


class SharePointFileActionCreate(SharePointFileActionBase):
    pass


class SharePointFileActionUpdate(BaseModel):
    name: Optional[str] = None
    connection_id: Optional[str] = None
    enabled: Optional[bool] = None
    project_id: Optional[str] = None
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
    project_id: Optional[str] = None
    site_id: str = ""
    site_name: str = ""
    list_id: str = ""
    list_name: str = ""
    operation: SharePointListOperation = SharePointListOperation.create
    item_id_template: str = ""
    lookup_field: str = ""
    lookup_value_template: str = ""
    field_map: dict = Field(default_factory=dict)


class SharePointListActionCreate(SharePointListActionBase):
    pass


class SharePointListActionUpdate(BaseModel):
    name: Optional[str] = None
    connection_id: Optional[str] = None
    enabled: Optional[bool] = None
    project_id: Optional[str] = None
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
