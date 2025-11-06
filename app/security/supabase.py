"""Supabase JWT verification helpers for FastAPI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urljoin

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
import httpx
from time import time

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


def _jwks_url() -> str:
    if settings.supabase_jwks_url:
        return settings.supabase_jwks_url
    if not settings.supabase_project_url:
        raise RuntimeError(
            "Supabase project URL is not configured. "
            "Set SUPABASE_PROJECT_URL before enabling authenticated endpoints."
        )
    base = settings.supabase_project_url.rstrip("/") + "/"
    return urljoin(base, "auth/v1/.well-known/jwks.json")


def _validate_config() -> tuple[str, str, str, str]:
    """Read config values needed for token verification."""
    audience = settings.supabase_jwt_audience or "authenticated"
    issuer = _build_issuer()
    jwks_url = _jwks_url()
    return jwks_url, audience, issuer, settings.supabase_project_url or ""


_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


async def _get_jwks(jwks_url: str) -> dict[str, Any]:
    ttl = max(settings.supabase_jwks_cache_ttl_seconds, 60)
    cached = _JWKS_CACHE.get(jwks_url)
    now = time()
    if cached and now - cached[0] < ttl:
        return cached[1]

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(jwks_url)
            response.raise_for_status()
            jwks = response.json()
    except httpx.HTTPError as exc:  # pragma: no cover - network failure
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to fetch Supabase signing keys",
        ) from exc

    _JWKS_CACHE[jwks_url] = (now, jwks)
    return jwks


async def _build_key(token: str, jwks_url: str) -> tuple[dict[str, Any], Optional[str]]:
    jwks = await _get_jwks(jwks_url)
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    if not kid:
        raise JWTError("Supabase token missing key id")
    keys = jwks.get("keys", [])
    for key in keys:
        if key.get("kid") == kid:
            return key, header.get("alg") or key.get("alg")
    raise JWTError("Supabase signing key not found for token")


async def _decode_token(token: str) -> Dict[str, Any]:
    jwks_url, audience, issuer, _ = _validate_config()
    key, algorithm = await _build_key(token, jwks_url)
    allowed_algorithms: list[str] = []
    if isinstance(algorithm, str):
        allowed_algorithms = [algorithm]
    elif isinstance(key, dict) and isinstance(key.get("alg"), str):
        allowed_algorithms = [key["alg"]]
    else:
        allowed_algorithms = ["RS256"]
    return jwt.decode(
        token,
        key,
        algorithms=allowed_algorithms,
        audience=audience,
        issuer=issuer,
    )


async def verify_supabase_token(token: str) -> AuthenticatedUser:
    """Verify a Supabase access token and return the authenticated user."""
    try:
        payload = await _decode_token(token)
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
    return await verify_supabase_token(credentials.credentials)


__all__ = ["AuthenticatedUser", "get_current_user", "verify_supabase_token"]
