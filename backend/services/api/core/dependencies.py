"""FastAPI dependencies for authentication and tenant resolution.

Dual-path auth:
  1. JWT Bearer token  → full SaaS user/tenant resolution
  2. X-API-Key header  → backward-compat, maps to sentinel tenant

Usage:
    @router.get("/jobs")
    async def list_jobs(tenant: CurrentTenant, db: AsyncSession = Depends(get_db)):
        ...
"""

from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.core.config import get_settings
from services.api.core.database import get_db
from services.api.core.security import decode_token
from services.api.models.db import SENTINEL_TENANT_ID, Tenant, User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the authenticated user from JWT Bearer or X-API-Key."""
    settings = get_settings()

    # ── Path 1: X-API-Key (backward compat) ──────────────────────────────
    if x_api_key and x_api_key == settings.admin_api_key:
        return _get_synthetic_api_key_user()

    # ── Path 2: JWT Bearer ────────────────────────────────────────────────
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type."
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

    from services.api.repositories.user_repo import get_user_by_id
    user = await get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")

    return user


async def get_current_tenant(
    user: "User" = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """Resolve the tenant from the authenticated user."""
    from services.api.repositories.tenant_repo import get_tenant_by_id
    tenant = await get_tenant_by_id(db, user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found.")
    return tenant


# ── Annotated shortcuts ───────────────────────────────────────────────────────

CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentTenant = Annotated[Tenant, Depends(get_current_tenant)]


def require_role(*roles: str):
    """Dependency factory that enforces one of the given roles.

    Returns a callable suitable for use with FastAPI's Depends():
        async def endpoint(_: User = Depends(require_role("owner"))): ...
    """
    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {' or '.join(roles)}.",
            )
        return user
    return _check


# Convenience callables — use as: Depends(OwnerOnly) or Depends(AdminPlus)
def OwnerOnly(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("owner",):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner access required.")
    return user


def AdminPlus(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("owner", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")
    return user


# ── Synthetic user for X-API-Key ─────────────────────────────────────────────

def _get_synthetic_api_key_user() -> User:
    """Returns a transient duck-typed user wired to the sentinel tenant.

    SimpleNamespace avoids SQLAlchemy ORM initialisation (no _sa_instance_state).
    """
    from types import SimpleNamespace
    return SimpleNamespace(  # type: ignore[return-value]
        id="api-key-service-account",
        tenant_id=SENTINEL_TENANT_ID,
        role="owner",
        is_active=True,
        is_verified=True,
        email="api@internal",
        hashed_password="",
    )
