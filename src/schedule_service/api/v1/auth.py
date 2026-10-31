"""Login and account administration endpoints."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from schedule_service.core.auth import (
    CredentialsDep,
    CurrentUser,
    SessionDep,
    hash_password,
    require_admin,
    token_digest,
    verify_password,
)
from schedule_service.core.config import get_settings
from schedule_service.models.user import LoginSession, User
from schedule_service.schemas.user import LoginRequest, TokenRead, UserCreate, UserRead, UserUpdate

router = APIRouter()
Admin = Annotated[User, Depends(require_admin)]


@router.post("/auth/login", response_model=TokenRead)
async def login(data: LoginRequest, session: SessionDep) -> TokenRead:
    user = await session.scalar(select(User).where(User.username == data.username))
    if (
        user is None
        or not user.is_active
        or not verify_password(data.password.get_secret_value(), user.password_hash)
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = secrets.token_urlsafe(32)
    lifetime = get_settings().session_lifetime_seconds
    expires_at = datetime.now(UTC) + timedelta(seconds=lifetime)
    session.add(
        LoginSession(user_id=user.id, token_hash=token_digest(token), expires_at=expires_at)
    )
    await session.flush()
    return TokenRead(access_token=token, expires_in=lifetime)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: CurrentUser, credentials: CredentialsDep, session: SessionDep) -> None:
    assert credentials is not None
    query = delete(LoginSession).where(
        LoginSession.user_id == user.id,
        LoginSession.token_hash == token_digest(credentials.credentials),
    )
    await session.execute(query)


@router.get("/auth/me", response_model=UserRead)
async def me(user: CurrentUser) -> User:
    return user


@router.get("/users", response_model=list[UserRead])
async def list_users(_admin: Admin, session: SessionDep) -> list[User]:
    return list((await session.scalars(select(User).order_by(User.id))).all())


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, _admin: Admin, session: SessionDep) -> User:
    user = User(
        username=data.username,
        password_hash=hash_password(data.password.get_secret_value()),
        role=data.role.value,
        is_active=True,
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Username already exists") from exc
    return user


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user(user_id: int, data: UserUpdate, _admin: Admin, session: SessionDep) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if data.role is not None:
        user.role = data.role.value
    if data.is_active is not None:
        user.is_active = data.is_active
        if not data.is_active:
            await session.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    await session.flush()
    return user
