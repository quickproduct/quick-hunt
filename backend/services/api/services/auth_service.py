"""Auth service — register, login, token refresh, logout, email verification."""

from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.core.security import (
    create_access_token,
    create_email_verification_token,
    create_password_reset_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from services.api.models.db import Membership, User
from services.api.repositories import tenant_repo, user_repo
from services.api.schemas.auth_schemas import TokenResponse

logger = structlog.get_logger(__name__)

_REFRESH_TTL_SECONDS = 7 * 24 * 3600  # 7 days

_async_redis_client = None


def _redis():
    """Singleton async Redis client for refresh-token jti storage.

    Uses redis.asyncio so that retry backoff and socket timeouts run on the
    event loop rather than blocking it.  A synchronous client would freeze
    all in-flight requests for up to socket_timeout × retries seconds
    whenever Upstash's idle-connection reaper closes the socket.
    """
    global _async_redis_client
    if _async_redis_client is None:
        import redis.asyncio as redis_lib
        from redis.backoff import ExponentialBackoff
        from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError
        from redis.retry import Retry
        from services.api.core.config import get_settings
        settings = get_settings()
        retry = Retry(ExponentialBackoff(cap=2, base=0.5), retries=3)
        _async_redis_client = redis_lib.from_url(
            settings.redis_url,
            decode_responses=True,
            retry=retry,
            retry_on_error=[RedisConnectionError, RedisTimeoutError],
            socket_connect_timeout=5,
            socket_timeout=5,
            health_check_interval=30,
        )
    return _async_redis_client


async def register(
    session: AsyncSession,
    tenant_name: str,
    email: str,
    plain_password: str,
) -> TokenResponse:
    """Create tenant + owner user, send verification email."""
    tenant = await tenant_repo.create_tenant(session, tenant_name)

    verification_token = create_email_verification_token()
    user = await user_repo.create_user(
        session,
        tenant_id=tenant.id,
        email=email,
        hashed_password=hash_password(plain_password),
        role="owner",
        verification_token=verification_token,
    )

    # Add membership row
    import uuid
    membership = Membership(
        id=str(uuid.uuid4()),
        user_id=user.id,
        tenant_id=tenant.id,
        role="owner",
    )
    session.add(membership)
    await session.commit()

    # TODO: send verification email via email adapter
    logger.info("user_registered", user_id=user.id, tenant_id=tenant.id)

    access_token = create_access_token(user.id, tenant.id, user.role)
    refresh_token, jti = create_refresh_token(user.id, tenant.id)
    await _store_refresh_jti(user.id, jti)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


async def login(
    session: AsyncSession,
    email: str,
    plain_password: str,
    tenant_id: Optional[str] = None,
) -> TokenResponse:
    """Authenticate user and return JWT pair.

    If tenant_id is not provided, finds the first active tenant for this email.
    """
    if not tenant_id:
        # Find user by email across all tenants (picks first match)
        from sqlalchemy import select
        result = await session.execute(
            select(User).where(User.email == email, User.is_active == True)  # noqa
        )
        user = result.scalars().first()
    else:
        user = await user_repo.get_user_by_email(session, email, tenant_id)

    if not user or not verify_password(plain_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled.")

    access_token = create_access_token(user.id, user.tenant_id, user.role)
    refresh_token, jti = create_refresh_token(user.id, user.tenant_id)
    await _store_refresh_jti(user.id, jti)

    logger.info("user_logged_in", user_id=user.id)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


async def refresh_tokens(session: AsyncSession, refresh_token: str) -> TokenResponse:
    """Rotate refresh token — invalidate old jti, issue new pair."""
    from jose import JWTError
    from services.api.core.security import decode_token

    try:
        payload = decode_token(refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token."
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type."
        )

    jti = payload.get("jti", "")
    user_id = payload["sub"]

    if not await _validate_and_revoke_jti(user_id, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token already used or revoked.",
        )

    user = await user_repo.get_user_by_id(session, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")

    access_token = create_access_token(user.id, user.tenant_id, user.role)
    new_refresh, new_jti = create_refresh_token(user.id, user.tenant_id)
    await _store_refresh_jti(user.id, new_jti)

    return TokenResponse(access_token=access_token, refresh_token=new_refresh)


async def logout(user_id: str, refresh_token: str) -> None:
    """Revoke the refresh token jti."""
    from jose import JWTError
    from services.api.core.security import decode_token
    try:
        payload = decode_token(refresh_token)
        jti = payload.get("jti", "")
        await _validate_and_revoke_jti(user_id, jti)
    except JWTError:
        pass  # already expired or invalid — fine


async def verify_email(session: AsyncSession, token: str) -> None:
    user = await user_repo.get_user_by_verification_token(session, token)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token.")
    user.is_verified = True
    user.verification_token = None
    await session.commit()


async def forgot_password(session: AsyncSession, email: str) -> None:
    """Generate reset token and (TODO) send reset email."""
    from sqlalchemy import select
    result = await session.execute(
        select(User).where(User.email == email, User.is_active == True)  # noqa
    )
    user = result.scalars().first()
    if not user:
        return  # don't leak whether email exists

    reset_token = create_password_reset_token()
    settings_ttl = timedelta(hours=1)
    user.reset_token = reset_token
    user.reset_token_expires = datetime.now(timezone.utc) + settings_ttl
    await session.commit()
    # TODO: send reset email via email adapter
    logger.info("password_reset_requested", user_id=user.id)


async def reset_password(session: AsyncSession, token: str, new_password: str) -> None:
    user = await user_repo.get_user_by_reset_token(session, token)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token.")
    if user.reset_token_expires and user.reset_token_expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token expired.")
    user.hashed_password = hash_password(new_password)
    user.reset_token = None
    user.reset_token_expires = None
    await session.commit()


# ── Redis jti helpers ─────────────────────────────────────────────────────────

def _jti_key(user_id: str) -> str:
    return f"refresh_jti:{user_id}"


async def _store_refresh_jti(user_id: str, jti: str) -> None:
    try:
        r = _redis()
        await r.setex(_jti_key(user_id), _REFRESH_TTL_SECONDS, jti)
    except Exception as exc:
        logger.warning("refresh_jti_store_failed", error=str(exc))


async def _validate_and_revoke_jti(user_id: str, jti: str) -> bool:
    """Return True and delete the stored jti if it matches; False otherwise."""
    try:
        r = _redis()
        stored = await r.get(_jti_key(user_id))
        if stored == jti:
            await r.delete(_jti_key(user_id))
            return True
        return False
    except Exception:
        # Redis unavailable — allow the refresh (degrade gracefully)
        return True
