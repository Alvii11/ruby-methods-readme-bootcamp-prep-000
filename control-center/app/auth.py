"""Password login + signed session cookies for the Control Center.

The dashboard can start arbitrary processes, so any time it is reachable beyond
localhost it MUST require auth. Authentication is a single shared password;
on success we hand out a short HMAC-signed session token stored in a cookie.
No external dependencies — just hashlib/hmac/secrets from the stdlib.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

from .config import AuthConfig

COOKIE_NAME = "cc_session"


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def configured_password_hash(auth: AuthConfig) -> str | None:
    """The expected password as a sha256 hex digest, or None if unconfigured."""
    if auth.password_sha256:
        return auth.password_sha256.strip().lower()
    plain = os.environ.get(auth.password_env)
    if plain:
        return _sha256_hex(plain)
    return None


def verify_password(auth: AuthConfig, candidate: str) -> bool:
    expected = configured_password_hash(auth)
    if not expected:
        return False
    return hmac.compare_digest(expected, _sha256_hex(candidate))


def resolve_secret(auth: AuthConfig) -> bytes:
    """Cookie-signing key: config.secret, else $CC_SECRET, else a random one
    generated once for this process."""
    raw = auth.secret or os.environ.get("CC_SECRET")
    if raw:
        return raw.encode("utf-8")
    global _RUNTIME_SECRET
    if _RUNTIME_SECRET is None:
        _RUNTIME_SECRET = secrets.token_bytes(32)
    return _RUNTIME_SECRET


_RUNTIME_SECRET: bytes | None = None


def _sign(secret: bytes, payload: str) -> str:
    return hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def make_token(auth: AuthConfig) -> str:
    secret = resolve_secret(auth)
    expiry = int(time.time()) + auth.session_hours * 3600
    payload = str(expiry)
    return f"{payload}.{_sign(secret, payload)}"


def check_token(auth: AuthConfig, token: str | None) -> bool:
    if not token or "." not in token:
        return False
    payload, sig = token.rsplit(".", 1)
    secret = resolve_secret(auth)
    if not hmac.compare_digest(sig, _sign(secret, payload)):
        return False
    try:
        return int(payload) > int(time.time())
    except ValueError:
        return False
