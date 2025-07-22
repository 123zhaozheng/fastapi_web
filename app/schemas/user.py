from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from ..config import settings
from .role import Role
import base64

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
    """User password change schema"""
    current_password: str = Field(..., description="Base64编码的当前密码")
    new_password: str = Field(..., description="Base64编码的新密码")

    def get_decoded_current_password(self) -> str:
        """解码Base64当前密码"""
        try:
            return base64.b64decode(self.current_password).decode('utf-8')
        except:
            return self.current_password

    def get_decoded_new_password(self) -> str:
        """解码Base64新密码"""
        try:
            return base64.b64decode(self.new_password).decode('utf-8')
        except:
            return self.new_password


# Schema for password reset by admin
class UserPasswordReset(BaseModel):
    """User password reset schema"""
    new_password: str = Field(..., description="Base64编码的新密码")

    def get_decoded_new_password(self) -> str:
        """解码Base64新密码"""
        try:
            return base64.b64decode(self.new_password).decode('utf-8')
        except:
            return self.new_password


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
    """User login schema"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="Base64编码的密码")

    def get_decoded_password(self) -> str:
        """解码Base64密码"""
        try:
            return base64.b64decode(self.password).decode('utf-8')
        except:
            # 如果解码失败，返回原始密码（兼容性处理）
            return self.password