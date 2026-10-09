"""Signed tokens for edits. Passwords stay plain text, as stored by install.py."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

TOKEN_LIFETIME_SECONDS = 3600


def passwords_match(given: str, stored: str) -> bool:
    return hmac.compare_digest(
        hashlib.sha256(given.encode("utf-8")).digest(),
        hashlib.sha256(stored.encode("utf-8")).digest(),
    )


def issue_token(username: str, secret: str, *, now: int) -> str:
    header = _encode({"alg": "HS256", "typ": "JWT"})
    payload = _encode({"sub": username, "exp": now + TOKEN_LIFETIME_SECONDS})
    signature = _sign(f"{header}.{payload}", secret)
    return f"{header}.{payload}.{signature}"


def read_token(token: str, secret: str, *, now: int) -> tuple[str, str]:
    """Return (state, username). State is ok, expired, or invalid."""
    parts = token.split(".")
    if len(parts) != 3:
        return "invalid", ""
    header_text, payload_text, signature = parts
    expected = _sign(f"{header_text}.{payload_text}", secret)
    if not hmac.compare_digest(signature, expected):
        return "invalid", ""
    try:
        header = _decode(header_text)
        payload = _decode(payload_text)
    except (ValueError, json.JSONDecodeError, UnicodeError):
        return "invalid", ""
    if not isinstance(header, dict) or header.get("alg") != "HS256":
        return "invalid", ""
    if not isinstance(payload, dict):
        return "invalid", ""
    username = payload.get("sub")
    expires_at = payload.get("exp")
    if not isinstance(username, str) or not username:
        return "invalid", ""
    if isinstance(expires_at, bool) or not isinstance(expires_at, int):
        return "invalid", ""
    if now >= expires_at:
        return "expired", ""
    return "ok", username


def _encode(value: dict[str, Any]) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode(text: str) -> Any:
    padding = "=" * (-len(text) % 4)
    raw = base64.urlsafe_b64decode(text + padding)
    return json.loads(raw.decode("utf-8"))


def _sign(signing_input: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
