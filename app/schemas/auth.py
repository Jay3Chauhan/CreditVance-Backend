"""
Authentication & User Pydantic Schemas.
"""

from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegisterRequest(BaseModel):
    email: EmailStr = Field(..., description="Valid user email address")
    password: str = Field(..., min_length=8, description="Strong password (min 8 characters)")
    full_name: Optional[str] = Field(None, max_length=150, description="User full display name")


class UserLoginRequest(BaseModel):
    email: EmailStr = Field(..., description="Registered email address")
    password: str = Field(..., description="Account password")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in_minutes: int


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., description="Valid JWT refresh token")


class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, max_length=150, description="Updated full name")


class PasswordForgotRequest(BaseModel):
    email: EmailStr = Field(..., description="Account email to send reset instructions to")


class PasswordForgotResponse(BaseModel):
    message: str
    reset_token: Optional[str] = Field(None, description="Reset token (provided for testing / mock email delivery)")


class PasswordResetRequest(BaseModel):
    token: str = Field(..., description="Password reset token")
    new_password: str = Field(..., min_length=8, description="New account password (min 8 characters)")


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: Optional[str] = None
    is_active: bool
    is_admin: bool
