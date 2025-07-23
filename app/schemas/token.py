from typing import Optional
from pydantic import BaseModel


class Token(BaseModel):
    """Schema for token response"""
    access_token: str
    refresh_token: str
    token_type: str
    password_reset_required: bool = False


class TokenPayload(BaseModel):
    """Schema for token payload"""
    sub: int
    exp: int


class RefreshToken(BaseModel):
    """Schema for refresh token request"""
    refresh_token: str
