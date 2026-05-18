"""User repository — DB queries for the users table."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.models.db import User


async def get_user_by_id(session: AsyncSession, user_id: str) -> Optional[User]:
    return await session.get(User, user_id)


async def get_user_by_email(
    session: AsyncSession, email: str, tenant_id: str
) -> Optional[User]:
    result = await session.execute(
        select(User).where(User.email == email, User.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_verification_token(
    session: AsyncSession, token: str
) -> Optional[User]:
    result = await session.execute(
        select(User).where(User.verification_token == token)
    )
    return result.scalar_one_or_none()


async def get_user_by_reset_token(
    session: AsyncSession, token: str
) -> Optional[User]:
    result = await session.execute(
        select(User).where(User.reset_token == token)
    )
    return result.scalar_one_or_none()


async def list_tenant_users(session: AsyncSession, tenant_id: str) -> list[User]:
    result = await session.execute(
        select(User).where(User.tenant_id == tenant_id, User.is_active == True)  # noqa
    )
    return list(result.scalars().all())


async def create_user(session: AsyncSession, **kwargs) -> User:
    import uuid
    user = User(id=str(uuid.uuid4()), **kwargs)
    session.add(user)
    await session.flush()
    return user
