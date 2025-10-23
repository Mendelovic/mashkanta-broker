"""Supabase JWT verification helpers for FastAPI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urljoin

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from ..config import settings

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    """Represents a Supabase-authenticated user."""

    user_id: str
    email: Optional[str]
    phone: Optional[str]
    session_id: Optional[str]
    claims: Dict[str, Any]


def _build_issuer() -> str:
    """Derive the expected issuer URL."""
    if settings.supabase_jwt_issuer:
        return settings.supabase_jwt_issuer
    if not settings.supabase_project_url:
        raise RuntimeError(
            "Supabase project URL is not configured. "
            "Set SUPABASE_PROJECT_URL before enabling authenticated endpoints."
        )
    base = settings.supabase_project_url.rstrip("/") + "/"
    return urljoin(base, "auth/v1")


def _validate_config() -> tuple[str, str, str]:
    """Read config values needed for token verification."""
    if not settings.supabase_jwt_secret:
        raise RuntimeError(
            "Supabase JWT secret is not configured. "
            "Set SUPABASE_JWT_SECRET before enabling authenticated endpoints."
        )
    audience = settings.supabase_jwt_audience or "authenticated"
    issuer = _build_issuer()
    return settings.supabase_jwt_secret, audience, issuer


def _decode_token(token: str) -> Dict[str, Any]:
    secret, audience, issuer = _validate_config()
    return jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        audience=audience,
        issuer=issuer,
    )


def verify_supabase_token(token: str) -> AuthenticatedUser:
    """Verify a Supabase access token and return the authenticated user."""
    try:
        payload = _decode_token(token)
    except JWTError as exc:  # pragma: no cover - exercised via dependency
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate Supabase credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Supabase token missing subject claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthenticatedUser(
        user_id=user_id,
        email=payload.get("email"),
        phone=payload.get("phone"),
        session_id=payload.get("session_id"),
        claims=payload,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedUser:
    """FastAPI dependency that enforces Supabase authentication."""
    if credentials is None or not credentials.scheme.lower() == "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_supabase_token(credentials.credentials)


__all__ = ["AuthenticatedUser", "get_current_user", "verify_supabase_token"]
