"""Password hashing, session authentication and API access policy."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from schedule_service.core.database import get_async_session
from schedule_service.models.user import LoginSession, User, UserRole

bearer = HTTPBearer(auto_error=False)
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]
CredentialsDep = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, salt, expected = stored.split("$")
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError):
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def get_current_user(credentials: CredentialsDep, session: SessionDep) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    query = select(LoginSession, User).join(User, LoginSession.user_id == User.id)
    query = query.where(LoginSession.token_hash == token_digest(credentials.credentials))
    result = (await session.execute(query)).one_or_none()
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid session")
    login_session, user = result
    expires_at = login_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if not user.is_active or expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=401, detail="Invalid session")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_schedule_access(request: Request, user: CurrentUser) -> None:
    if user.role not in {role.value for role in UserRole}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    if request.method not in {"GET", "HEAD", "OPTIONS"} and user.role == UserRole.READER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )


async def require_admin(user: CurrentUser) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    return user
