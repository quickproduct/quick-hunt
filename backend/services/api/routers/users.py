"""User management endpoints."""

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.core.database import get_db
from services.api.core.dependencies import AdminPlus, CurrentTenant, CurrentUser, OwnerOnly
from services.api.core.security import hash_password, verify_password
from services.api.models.db import Membership, User
from services.api.repositories import user_repo
from services.api.schemas.auth_schemas import (
    ChangeRoleRequest,
    InviteUserRequest,
    UpdateProfileRequest,
    UserResponse,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def get_me(user: CurrentUser):
    return user


@router.put("/me", response_model=UserResponse)
async def update_me(
    body: UpdateProfileRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    if body.new_password:
        if not body.current_password or not verify_password(
            body.current_password, user.hashed_password
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect.",
            )
        user.hashed_password = hash_password(body.new_password)
    if body.email:
        user.email = body.email
    await db.commit()
    return user


@router.get("", response_model=List[UserResponse])
async def list_users(
    tenant: CurrentTenant,
    _: User = Depends(AdminPlus),
    db: AsyncSession = Depends(get_db),
):
    return await user_repo.list_tenant_users(db, tenant.id)


@router.post("/invite", status_code=201)
async def invite_user(
    body: InviteUserRequest,
    tenant: CurrentTenant,
    _: User = Depends(AdminPlus),
    db: AsyncSession = Depends(get_db),
):
    """Invite a user to the tenant (creates account with temporary password)."""
    import secrets
    temp_password = secrets.token_urlsafe(12)
    new_user = await user_repo.create_user(
        db,
        tenant_id=tenant.id,
        email=body.email,
        hashed_password=hash_password(temp_password),
        role=body.role,
    )
    membership = Membership(
        id=str(uuid.uuid4()),
        user_id=new_user.id,
        tenant_id=tenant.id,
        role=body.role,
    )
    db.add(membership)
    await db.commit()
    # TODO: send invite email with temp_password
    return {"id": new_user.id, "email": new_user.email, "role": new_user.role}


@router.delete("/{user_id}", status_code=204)
async def remove_user(
    user_id: str,
    current_user: CurrentUser,
    tenant: CurrentTenant,
    _: User = Depends(OwnerOnly),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove yourself."
        )
    target = await user_repo.get_user_by_id(db, user_id)
    if not target or target.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    target.is_active = False
    await db.commit()


@router.patch("/{user_id}/role", response_model=UserResponse)
async def change_role(
    user_id: str,
    body: ChangeRoleRequest,
    tenant: CurrentTenant,
    _: User = Depends(OwnerOnly),
    db: AsyncSession = Depends(get_db),
):
    target = await user_repo.get_user_by_id(db, user_id)
    if not target or target.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    target.role = body.role
    await db.commit()
    return target
