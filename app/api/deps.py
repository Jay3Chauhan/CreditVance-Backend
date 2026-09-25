"""
FastAPI Dependencies for Database, Authentication, and Admin Authorization.
"""

from typing import AsyncGenerator, Optional
from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.exceptions import AuthenticationError, ForbiddenError
from app.core.security import decode_access_token
from app.models.user import User

security_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that yields an async database session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_current_user(
    auth_header: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticates the user from Bearer JWT token."""
    if not auth_header:
        raise AuthenticationError("Missing Authorization Bearer header.")

    token = auth_header.credentials
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Invalid token subject.")

    stmt = select(User).where(User.id == int(user_id))
    user = (await db.execute(stmt)).scalar_one_or_none()
    if not user:
        raise AuthenticationError("User associated with token not found.")
    if not user.is_active:
        raise ForbiddenError("User account is deactivated.")

    return user


async def get_optional_user(
    auth_header: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Returns the authenticated user if valid token present, otherwise None."""
    if not auth_header:
        return None
    try:
        token = auth_header.credentials
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if not user_id:
            return None
        stmt = select(User).where(User.id == int(user_id))
        user = (await db.execute(stmt)).scalar_one_or_none()
        return user if user and user.is_active else None
    except Exception:
        return None


async def verify_admin_key(
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-API-Key"),
    current_user: Optional[User] = Depends(get_optional_user),
) -> bool:
    """Authorizes either via matching X-Admin-API-Key header or via admin user JWT."""
    if x_admin_key and x_admin_key == settings.ADMIN_API_KEY:
        return True
    if current_user and current_user.is_admin:
        return True

    raise ForbiddenError("Admin credentials or valid X-Admin-API-Key required.")
