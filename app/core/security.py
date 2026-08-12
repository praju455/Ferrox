import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db import get_db
from app.models import User, UserRole


try:
    import jwt as pyjwt
except ImportError:
    pyjwt = None

try:
    from pwdlib import PasswordHash

    password_hash = PasswordHash.recommended()
except ImportError:
    password_hash = None


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    user_id: str | None
    email: str
    role: UserRole
    service: bool = False


def hash_password(password: str) -> str:
    if password_hash is not None:
        return password_hash.hash(password)
    iterations = 600_000
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    if encoded.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt, expected = encoded.split("$", 3)
            digest = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode(),
                base64.urlsafe_b64decode(salt),
                int(iterations),
            )
            return hmac.compare_digest(base64.urlsafe_b64encode(digest).decode(), expected)
        except (ValueError, TypeError):
            return False
    return bool(password_hash and password_hash.verify(password, encoded))


def create_access_token(user: User, settings: Settings | None = None) -> tuple[str, int]:
    settings = settings or get_settings()
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured")
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": user.id,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    if pyjwt is not None:
        token = pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    else:
        token = _encode_hs256(payload, settings.jwt_secret)
    return token, settings.access_token_expire_minutes * 60


def decode_access_token(token: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if not settings.jwt_secret:
        raise ValueError("JWT authentication is not configured")
    if pyjwt is not None:
        payload = pyjwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )
    else:
        payload = _decode_hs256(token, settings)
    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise ValueError("JWT subject is missing")
    return subject


def _encode_hs256(payload: dict, secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    segments = [_b64json(header), _b64json(payload)]
    signing_input = ".".join(segments).encode()
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return ".".join([*segments, _b64(signature)])


def _decode_hs256(token: str, settings: Settings) -> dict:
    try:
        header_segment, payload_segment, signature_segment = token.split(".")
        signing_input = f"{header_segment}.{payload_segment}".encode()
        expected = hmac.new((settings.jwt_secret or "").encode(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(_b64(expected), signature_segment):
            raise ValueError("Invalid JWT signature")
        header = json.loads(_b64decode(header_segment))
        payload = json.loads(_b64decode(payload_segment))
    except Exception as exc:
        raise ValueError("Malformed JWT") from exc
    if header.get("alg") != "HS256":
        raise ValueError("Unsupported JWT algorithm")
    now = int(datetime.now(timezone.utc).timestamp())
    if int(payload.get("exp", 0)) <= now:
        raise ValueError("JWT has expired")
    if payload.get("iss") != settings.jwt_issuer or payload.get("aud") != settings.jwt_audience:
        raise ValueError("Invalid JWT issuer or audience")
    return payload


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _b64json(value: dict) -> str:
    return _b64(json.dumps(value, separators=(",", ":"), sort_keys=True).encode())


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def current_principal(
    db: Session = Depends(get_db),
    x_api_key: str | None = Security(api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> Principal:
    settings = get_settings()
    supplied = bearer.credentials if bearer else None
    if settings.internal_api_key:
        service_key = x_api_key or supplied
        if service_key and hmac.compare_digest(service_key, settings.internal_api_key):
            return Principal(None, "service@ferrox.internal", UserRole.admin, service=True)
    if supplied and settings.jwt_secret:
        try:
            user_id = decode_access_token(supplied, settings)
        except Exception as exc:
            raise _unauthorized("Invalid or expired access token") from exc
        user = db.get(User, user_id)
        if not user or not user.is_active:
            raise _unauthorized("User account is inactive or missing")
        return Principal(user.id, user.email, user.role)
    if not settings.internal_api_key and not settings.jwt_secret and not settings.is_production:
        return Principal(None, "local@ferrox.dev", UserRole.admin, service=True)
    raise _unauthorized("Authentication required")


def require_roles(*roles: UserRole) -> Callable:
    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return principal

    return dependency


require_reviewer = require_roles(UserRole.reviewer, UserRole.admin)
require_admin = require_roles(UserRole.admin)
require_internal_api_key = require_reviewer


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )
