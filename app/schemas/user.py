from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from .role import Role


# Base User Schema
class UserBase(BaseModel):
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    phone: Optional[str] = None
    avatar: Optional[str] = None
    is_active: Optional[bool] = True
    department_id: Optional[int] = None


# Schema for creating a user
class UserCreate(UserBase):
    password: str
    is_admin: Optional[bool] = False
    role_ids: Optional[List[int]] = []


# Schema for updating a user
class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    department_id: Optional[int] = None
    is_admin: Optional[bool] = None


# Schema for updating user profile by user themselves
class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    avatar: Optional[str] = None


# Schema for password change
class UserPasswordChange(BaseModel):
    current_password: str
    new_password: str


# Schema for password reset by admin
class UserPasswordReset(BaseModel):
    new_password: str


# Schema returned to client
class User(UserBase):
    id: int
    is_admin: bool
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    roles: List[Role] = []  # Add roles field

    class Config:
        from_attributes = True


# Schema for user profile
class UserProfile(BaseModel):
    id: int
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    phone: Optional[str] = None
    avatar: Optional[str] = None
    is_active: bool
    is_admin: bool
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    role_ids: List[int] = []
    role_names: List[str] = []
    created_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


# Schema for avatar upload response
class UserAvatarUploadResponse(BaseModel):
    url: str
    thumbnails: Optional[dict] = None
# Schema for user login
class UserLogin(BaseModel):
    username: str
    password: str
