from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel


# Base Department Schema
class DepartmentBase(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    manager_id: Optional[int] = None


# Schema for creating a department
class DepartmentCreate(DepartmentBase):
    pass


# Schema for updating a department
class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None
    manager_id: Optional[int] = None


# Schema returned to client
class Department(DepartmentBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Schema for department with additional details
class DepartmentDetail(Department):
    manager_name: Optional[str] = None
    parent_name: Optional[str] = None
    users_count: int

    class Config:
        from_attributes = True


# Schema for department tree structure
class DepartmentNode(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    manager_id: Optional[int] = None
    manager_name: Optional[str] = None
    children: List['DepartmentNode'] = []


# Update forward reference for recursive type
DepartmentNode.model_rebuild()
