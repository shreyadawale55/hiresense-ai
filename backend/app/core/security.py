"""Security utilities for authentication, password hashing, and RBAC."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def hash_password(password: str, *, salt: Optional[str] = None) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256."""
    if not password:
        raise ValueError("Password cannot be empty")

    salt_bytes = bytes.fromhex(salt) if salt else secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        settings.PASSWORD_HASH_ROUNDS,
    )
    return f"pbkdf2_sha256${settings.PASSWORD_HASH_ROUNDS}${salt_bytes.hex()}${dk.hex()}"


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a PBKDF2 password hash."""
    try:
        scheme, rounds, salt_hex, digest_hex = hashed_password.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        candidate = hash_password(password, salt=salt_hex)
        return hmac.compare_digest(candidate, hashed_password)
    except Exception:
        return False


def _jwt_signing_input(payload: dict[str, Any]) -> str:
    header = {"alg": settings.JWT_ALGORITHM, "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}"
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def create_token(
    *,
    subject: str,
    token_type: str,
    expires_delta: timedelta,
    additional_claims: Optional[dict[str, Any]] = None,
) -> str:
    """Create a signed JWT token."""
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "iss": settings.TOKEN_ISSUER,
        "aud": settings.TOKEN_AUDIENCE,
        "jti": uuid.uuid4().hex,
    }
    if additional_claims:
        payload.update(additional_claims)
    return _jwt_signing_input(payload)


def create_access_token(subject: str, *, role: str, user_id: str, additional_claims: Optional[dict[str, Any]] = None) -> str:
    """Create an access token for the given user."""
    claims = {"role": role, "uid": user_id}
    if additional_claims:
        claims.update(additional_claims)
    return create_token(
        subject=subject,
        token_type="access",
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        additional_claims=claims,
    )


def create_refresh_token(subject: str, *, role: str, user_id: str, additional_claims: Optional[dict[str, Any]] = None) -> str:
    """Create a refresh token for the given user."""
    claims = {"role": role, "uid": user_id}
    if additional_claims:
        claims.update(additional_claims)
    return create_token(
        subject=subject,
        token_type="refresh",
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        additional_claims=claims,
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token signed with the app secret."""
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token format") from exc

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()

    if not hmac.compare_digest(_b64url_encode(expected), signature_b64):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload") from exc

    now = int(datetime.now(timezone.utc).timestamp())
    if payload.get("exp", 0) < now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    if payload.get("iss") != settings.TOKEN_ISSUER or payload.get("aud") != settings.TOKEN_AUDIENCE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token issuer mismatch")

    return payload


def hash_token(token: str) -> str:
    """Store refresh tokens as a SHA-256 digest."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """Resolve the current authenticated user from the access token."""
    from app.models.user import User

    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token required")

    user_id = payload.get("uid") or payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    try:
        resolved_id = uuid.UUID(str(user_id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user identifier") from exc

    result = await db.execute(select(User).where(User.id == resolved_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive or missing user")
    return user


def require_roles(*roles: str):
    """Dependency factory for role-protected routes."""

    async def _dependency(current_user=Depends(get_current_user)):
        current_role = getattr(current_user.role, "value", current_user.role)
        if current_role not in roles and current_role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user

    return _dependency


async def get_optional_token(request: Request) -> Optional[str]:
    """Extract an authorization token from the request if present."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip() or None
    return None


def token_subject_from_user(user_id: uuid.UUID | str) -> str:
    return str(user_id)
