"""
Authentication for the secure inference platform gateway.

Validates caller identity before admission control. Supports API key
authentication with tenant mapping. Disabled by default for demo mode.

Usage:
    from ai_inference.gateway.auth import ApiKeyAuthProvider, AuthResult

    provider = ApiKeyAuthProvider(keys={"sk-abc123": "tenant-a", "sk-def456": "tenant-b"})
    result = provider.authenticate("Bearer sk-abc123")
    # result.authenticated == True, result.tenant_id == "tenant-a"
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Protocol


@dataclass
class AuthResult:
    """Result of an authentication attempt."""

    authenticated: bool
    tenant_id: Optional[str] = None
    reason: str = ""


class AuthProvider(Protocol):
    def authenticate(self, authorization: Optional[str]) -> AuthResult: ...


class ApiKeyAuthProvider:
    """Validates API keys and maps them to tenant identities."""

    def __init__(self, keys: Dict[str, str]) -> None:
        """keys: mapping of api_key -> tenant_id"""
        self._keys = keys

    def authenticate(self, authorization: Optional[str]) -> AuthResult:
        if not authorization:
            return AuthResult(authenticated=False, reason="Missing Authorization header")

        parts = authorization.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return AuthResult(authenticated=False, reason="Invalid Authorization format, expected 'Bearer <key>'")

        key = parts[1]
        tenant_id = self._keys.get(key)
        if tenant_id is None:
            return AuthResult(authenticated=False, reason="Invalid API key")

        return AuthResult(authenticated=True, tenant_id=tenant_id)


class NoAuthProvider:
    """Allows all requests. Used in demo mode."""

    def authenticate(self, authorization: Optional[str]) -> AuthResult:
        return AuthResult(authenticated=True, reason="Auth disabled")
