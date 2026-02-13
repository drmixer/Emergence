"""Internal admin auth dependency for private ops endpoints."""
from __future__ import annotations

import hmac
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request, status

from app.core.config import settings


@dataclass(frozen=True)
class AdminActor:
    actor_id: str
    client_ip: str


def _extract_token(request: Request) -> str:
    auth_header = request.headers.get("authorization") or ""
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return str(request.headers.get("x-admin-token") or "").strip()


def _ip_allowed(client_ip: str) -> bool:
    allowed = get_admin_ip_allowlist_entries()
    if not allowed:
        return True
    return client_ip in allowed


def get_admin_ip_allowlist_entries() -> set[str]:
    raw_allowlist = str(getattr(settings, "ADMIN_IP_ALLOWLIST", "") or "").strip()
    if not raw_allowlist:
        return set()
    return {part.strip() for part in raw_allowlist.split(",") if part.strip()}


def assert_admin_write_access(*, client_ip: str) -> None:
    if not bool(getattr(settings, "ADMIN_ENABLED", False)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if not bool(getattr(settings, "ADMIN_WRITE_ENABLED", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin write controls are disabled in this environment",
        )

    environment = str(getattr(settings, "ENVIRONMENT", "development") or "development").strip().lower()
    if environment != "production":
        return

    allowlist = get_admin_ip_allowlist_entries()
    if not allowlist:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin write IP allowlist is required in production",
        )
    if client_ip not in allowlist:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin write IP not allowed")


def require_admin_auth(
    request: Request,
    x_admin_user: str | None = Header(default=None),
) -> AdminActor:
    if not bool(getattr(settings, "ADMIN_ENABLED", False)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    expected_token = str(getattr(settings, "ADMIN_API_TOKEN", "") or "").strip()
    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API not configured",
        )

    client_ip = request.client.host if request.client else "unknown"
    if not _ip_allowed(client_ip):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin IP not allowed")

    presented_token = _extract_token(request)
    if not presented_token or not hmac.compare_digest(presented_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
        )

    actor_id = str(x_admin_user or "admin").strip() or "admin"
    return AdminActor(actor_id=actor_id[:120], client_ip=client_ip)
