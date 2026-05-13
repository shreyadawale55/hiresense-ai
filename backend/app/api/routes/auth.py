"""Authentication and RBAC endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    hash_token,
    require_roles,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole
from app.schemas.auth import (
    AuthBootstrapResponse,
    CurrentUserResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserRead,
)

router = APIRouter()


def _user_to_schema(user: User) -> UserRead:
    return UserRead.model_validate(user)


async def _persist_refresh_token(
    *,
    db: AsyncSession,
    user: User,
    token: str,
    request: Request | None = None,
) -> RefreshToken:
    token_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(token),
        user_agent=request.headers.get("user-agent") if request else None,
        ip_address=(request.client.host if request and request.client else None),
        expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(token_record)
    await db.flush()
    return token_record


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    access_token = create_access_token(
        str(user.id),
        role=user.role.value,
        user_id=str(user.id),
    )
    refresh_token = create_refresh_token(
        str(user.id),
        role=user.role.value,
        user_id=str(user.id),
    )
    await _persist_refresh_token(db=db, user=user, token=refresh_token, request=request)
    user.last_login_at = datetime.utcnow()
    await db.flush()

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=_user_to_schema(user),
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(payload: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)):
    claims = decode_token(payload.refresh_token)
    if claims.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token required")

    token_hash = hash_token(payload.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
        )
    )
    token_record = result.scalar_one_or_none()
    if not token_record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked or unknown")
    if token_record.expires_at and token_record.expires_at < datetime.utcnow():
        token_record.revoked_at = datetime.utcnow()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    user_result = await db.execute(select(User).where(User.id == token_record.user_id))
    user = user_result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")

    token_record.revoked_at = datetime.utcnow()
    access_token = create_access_token(
        str(user.id),
        role=user.role.value,
        user_id=str(user.id),
    )
    new_refresh_token = create_refresh_token(
        str(user.id),
        role=user.role.value,
        user_id=str(user.id),
    )
    await _persist_refresh_token(db=db, user=user, token=new_refresh_token, request=request)
    await db.flush()

    return TokenPair(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=_user_to_schema(user),
    )


@router.post("/logout")
async def logout(payload: LogoutRequest, db: AsyncSession = Depends(get_db)):
    if payload.refresh_token:
        token_hash = hash_token(payload.refresh_token)
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None))
        )
        token_record = result.scalar_one_or_none()
        if token_record:
            token_record.revoked_at = datetime.utcnow()
    return {"detail": "Logged out"}


@router.get("/me", response_model=CurrentUserResponse)
async def me(current_user=Depends(get_current_user)):
    return CurrentUserResponse(user=_user_to_schema(current_user))


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles("admin")),
):
    if payload.role == UserRole.ADMIN and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can create admins")

    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        role=payload.role,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists") from exc
    return _user_to_schema(user)


@router.get("/bootstrap", response_model=AuthBootstrapResponse)
async def bootstrap_status(db: AsyncSession = Depends(get_db)):
    """Expose whether the bootstrap admin exists, useful for smoke tests."""
    result = await db.execute(select(User).where(User.role == UserRole.ADMIN))
    admin = result.scalars().first()
    return AuthBootstrapResponse(created=admin is not None, user=_user_to_schema(admin) if admin else None)
