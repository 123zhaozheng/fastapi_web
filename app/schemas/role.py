from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel


# Base Role Schema
class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_default: Optional[bool] = False


# Schema for creating a role
class RoleCreate(RoleBase):
    menu_ids: Optional[List[int]] = []
    button_ids: Optional[List[int]] = []


# Schema for updating a role
class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_default: Optional[bool] = None


# Schema returned to client
class Role(RoleBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Schema for role with permissions details
class RoleWithPermissions(Role):
    menu_ids: List[int] = []
    button_ids: List[int] = []
    users_count: int

    class Config:
        from_attributes = True


# Schema for user assignment to role
class RoleUsersAssign(BaseModel):
    user_ids: List[int]


# Schema for menu assignment to role
class RoleMenusAssign(BaseModel):
    menu_ids: List[int]


# Schema for button assignment to role
class RoleButtonsAssign(BaseModel):
    button_ids: List[int]
