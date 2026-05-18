"""JWT token creation/verification and password hashing."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt as _bcrypt
from jose import JWTError, jwt

from services.api.core.config import get_settings


# ── Password ──────────────────────────────────────────────────────────────────
# passlib 1.7.4 is incompatible with bcrypt 4.x/5.x: its backend probe passes
# a >72-byte test vector which bcrypt 5.x rejects with ValueError.
# We bypass passlib entirely and call bcrypt directly.  Passwords are
# SHA-256 pre-hashed so the input is always 64 bytes (well under bcrypt's 72).

def _prepare(plain: str) -> bytes:
    """Return SHA-256 hex-digest of *plain* as UTF-8 bytes (always 64 bytes)."""
    return hashlib.sha256(plain.encode()).hexdigest().encode()


def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(_prepare(plain), _bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(_prepare(plain), hashed.encode())
    except Exception:
        return False


# ── JWT ───────────────────────────────────────────────────────────────────────

def _settings():
    return get_settings()


def create_access_token(user_id: str, tenant_id: str, role: str) -> str:
    settings = _settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_ttl_minutes)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str, tenant_id: str) -> tuple[str, str]:
    """Returns (token, jti).  jti is stored in Redis to support rotation."""
    settings = _settings()
    jti = secrets.token_hex(16)
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_ttl_days)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "jti": jti,
        "type": "refresh",
        "exp": expire,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, jti


def decode_token(token: str) -> dict:
    """Decode and verify a JWT.  Raises JWTError on invalid/expired tokens."""
    settings = _settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def create_email_verification_token() -> str:
    return secrets.token_urlsafe(32)


def create_password_reset_token() -> str:
    return secrets.token_urlsafe(32)
