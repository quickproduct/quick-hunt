"""Pydantic schemas for auth, user, and tenant endpoints."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    tenant_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class VerifyEmailRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


# ── User ──────────────────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    email: str
    role: str
    is_verified: bool
    is_active: bool
    created_at: Optional[datetime] = None


class UpdateProfileRequest(BaseModel):
    email: Optional[EmailStr] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = Field(None, min_length=8)


class InviteUserRequest(BaseModel):
    email: EmailStr
    role: str = "member"


class ChangeRoleRequest(BaseModel):
    role: str = Field(..., pattern="^(owner|admin|member)$")


# ── Tenant ────────────────────────────────────────────────────────────────────

class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    plan: str
    status: str
    requires_approval: bool
    auto_send: bool
    score_threshold: int


class UpdateTenantRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    requires_approval: Optional[bool] = None
    auto_send: Optional[bool] = None
    score_threshold: Optional[int] = Field(None, ge=0, le=100)
