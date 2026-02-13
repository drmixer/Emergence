from __future__ import annotations

import importlib

import pytest
from fastapi import HTTPException

admin_auth = importlib.import_module("app.core.admin_auth")


def _set_admin_settings(
    monkeypatch,
    *,
    admin_enabled: bool = True,
    write_enabled: bool = True,
    environment: str = "development",
    allowlist: str = "",
) -> None:
    monkeypatch.setattr(admin_auth.settings, "ADMIN_ENABLED", admin_enabled, raising=False)
    monkeypatch.setattr(admin_auth.settings, "ADMIN_WRITE_ENABLED", write_enabled, raising=False)
    monkeypatch.setattr(admin_auth.settings, "ENVIRONMENT", environment, raising=False)
    monkeypatch.setattr(admin_auth.settings, "ADMIN_IP_ALLOWLIST", allowlist, raising=False)


def test_assert_admin_write_access_requires_admin_enabled(monkeypatch):
    _set_admin_settings(monkeypatch, admin_enabled=False, write_enabled=True)
    with pytest.raises(HTTPException) as exc_info:
        admin_auth.assert_admin_write_access(client_ip="127.0.0.1")
    assert exc_info.value.status_code == 404


def test_assert_admin_write_access_requires_write_flag(monkeypatch):
    _set_admin_settings(monkeypatch, admin_enabled=True, write_enabled=False)
    with pytest.raises(HTTPException) as exc_info:
        admin_auth.assert_admin_write_access(client_ip="127.0.0.1")
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Admin write controls are disabled in this environment"


def test_assert_admin_write_access_requires_allowlist_in_production(monkeypatch):
    _set_admin_settings(monkeypatch, environment="production", allowlist="")
    with pytest.raises(HTTPException) as exc_info:
        admin_auth.assert_admin_write_access(client_ip="127.0.0.1")
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Admin write IP allowlist is required in production"


def test_assert_admin_write_access_rejects_non_allowlisted_ip(monkeypatch):
    _set_admin_settings(monkeypatch, environment="production", allowlist="10.0.0.1")
    with pytest.raises(HTTPException) as exc_info:
        admin_auth.assert_admin_write_access(client_ip="127.0.0.1")
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Admin write IP not allowed"


def test_assert_admin_write_access_allows_allowlisted_ip(monkeypatch):
    _set_admin_settings(monkeypatch, environment="production", allowlist="127.0.0.1,10.0.0.1")
    admin_auth.assert_admin_write_access(client_ip="127.0.0.1")

