from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel


# Base Button Schema
class ButtonBase(BaseModel):
    name: str
    permission_key: str
    description: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = 0


# Schema for creating a button
class ButtonCreate(ButtonBase):
    menu_id: int


# Schema for updating a button
class ButtonUpdate(BaseModel):
    name: Optional[str] = None
    permission_key: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None


# Schema returned to client
class Button(ButtonBase):
    id: int
    menu_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Base Menu Schema
class MenuBase(BaseModel):
    name: str
    path: Optional[str] = None
    component: Optional[str] = None
    redirect: Optional[str] = None
    icon: Optional[str] = None
    title: str
    is_hidden: Optional[bool] = False
    sort_order: Optional[int] = 0
    parent_id: Optional[int] = None


# Schema for creating a menu
class MenuCreate(MenuBase):
    pass


# Schema for updating a menu
class MenuUpdate(BaseModel):
    name: Optional[str] = None
    path: Optional[str] = None
    component: Optional[str] = None
    redirect: Optional[str] = None
    icon: Optional[str] = None
    title: Optional[str] = None
    is_hidden: Optional[bool] = None
    sort_order: Optional[int] = None
    parent_id: Optional[int] = None


# Schema returned to client
class Menu(MenuBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Schema for menu with buttons
class MenuWithButtons(Menu):
    buttons: List[Button] = []

    class Config:
        from_attributes = True


# Schema for menu tree structure
class MenuNode(BaseModel):
    id: int
    name: str
    path: Optional[str] = None
    component: Optional[str] = None
    redirect: Optional[str] = None
    icon: Optional[str] = None
    title: str
    is_hidden: bool
    sort_order: int
    buttons: List[Button] = []
    children: List['MenuNode'] = []


# Update forward reference for recursive type
MenuNode.model_rebuild()


# Schema for user permissions (menus + buttons)
class UserPermissions(BaseModel):
    menus: List[MenuNode] = []
    buttons: List[str] = []  # List of permission keys
