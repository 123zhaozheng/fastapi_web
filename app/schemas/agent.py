from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class AgentPermissionTypeEnum(str, Enum):
    """Enum for agent permission types"""
    ROLE = "role"
    DEPARTMENT = "department"
    GLOBAL = "global"


# Base Agent Schema
class AgentBase(BaseModel):
    name: Optional[str] = None # Made name optional
    description: Optional[str] = None
    icon: Optional[str] = None
    is_active: bool = True
    is_digital_human: bool = False
    department_id: Optional[int] = None


# Schema for creating an agent
class AgentCreate(AgentBase):
    # Name and description will be fetched from Dify /info endpoint
    dify_app_id: Optional[str] = None
    api_endpoint: str = Field(..., description="Dify App Base URL (e.g., http://<host>/v1)")
    api_key: str = Field(..., description="Dify App API Key")
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)


# Schema for updating an agent
class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    is_active: Optional[bool] = None
    is_digital_human: Optional[bool] = None
    department_id: Optional[int] = None
    dify_app_id: Optional[str] = None
    api_endpoint: Optional[str] = None
    api_key: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


# Schema returned to client
class Agent(AgentBase):
    id: int
    dify_app_id: Optional[str] = None
    api_endpoint: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Schema for agent with detailed info
class AgentDetail(Agent):
    config: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        from_attributes = True


# Schema for agent permission
class AgentPermission(BaseModel):
    id: int
    agent_id: int
    type: AgentPermissionTypeEnum
    role_id: Optional[int] = None
    department_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Schema for setting agent permissions
class AgentPermissionCreate(BaseModel):
    type: AgentPermissionTypeEnum
    role_id: Optional[int] = None
    department_id: Optional[int] = None


# Schema for agent permissions setup
class AgentPermissions(BaseModel):
    permissions: List[AgentPermissionCreate]
    global_access: bool = False


# Schema for agent with permission details
class AgentWithPermissions(AgentDetail):
    permissions: List[AgentPermission] = []
    global_access: bool = False

    class Config:
        from_attributes = True


# Schema for the response of setting agent permissions
class AgentPermissionsResponse(BaseModel):
    agent_id: int
    permissions: List[AgentPermission] # Use the existing AgentPermission Pydantic schema
    global_access: bool

    class Config:
        from_attributes = True # Enable ORM mode for automatic conversion


# Schema for agent list item with minimal info
class AgentListItem(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    is_active: bool
    is_digital_human: bool = False
    department_id: Optional[int] = None

    class Config:
        from_attributes = True

class AgentIconUploadResponse(BaseModel):
    """Response model for agent icon upload"""
    url: str
