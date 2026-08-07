from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import secrets
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request, status

from backend.config import Config, get_settings


def random_token(bytes_count: int = 32) -> str:
    return secrets.token_urlsafe(bytes_count)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def keyed_hash(value: str, secret: str | None = None) -> str:
    key = (secret or get_settings().IDENTITY_SIGNING_SECRET).encode("utf-8")
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def token_cipher(settings: Config | None = None) -> Fernet:
    config = settings or get_settings()
    key = config.SESSION_ENCRYPTION_KEY
    if not key:
        seed = config.IDENTITY_SIGNING_SECRET or "craveai-local-development-only"
        key = base64.urlsafe_b64encode(hashlib.sha256(seed.encode()).digest()).decode()
    return Fernet(key.encode("ascii"))


def encrypt_secret(value: str) -> str:
    return token_cipher().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    try:
        return token_cipher().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Unable to decrypt stored authentication material.") from exc


def request_ip(request: Request) -> str:
    """Use forwarding headers only when the immediate peer is explicitly trusted."""
    settings = get_settings()
    direct = request.client.host if request.client else "unknown"
    if direct in settings.TRUSTED_PROXY_IPS:
        forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if forwarded:
            return forwarded
    return direct


def ip_prefix(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return "unknown"
    if address.version == 4:
        return str(ipaddress.ip_network(f"{address}/24", strict=False))
    return str(ipaddress.ip_network(f"{address}/56", strict=False))


def actor_ip_hash(request: Request) -> str:
    return keyed_hash(f"ip-prefix:{ip_prefix(request_ip(request))}")


def require_allowed_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return
    settings = get_settings()
    normalized = origin.rstrip("/")
    allowed = {item.rstrip("/") for item in settings.ALLOWED_ORIGINS}
    allowed.add(settings.FRONTEND_ORIGIN.rstrip("/"))
    if normalized not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "origin_not_allowed"},
        )


def safe_next_path(value: str | None, default: str = "/") -> str:
    if not value or not value.startswith("/") or value.startswith("//"):
        return default
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return default
    return value[:256]

