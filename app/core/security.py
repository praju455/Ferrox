import hmac

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


def require_internal_api_key(
    x_api_key: str | None = Security(api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> None:
    expected = get_settings().internal_api_key
    if not expected:
        return
    supplied = x_api_key or (bearer.credentials if bearer else None)
    if supplied and hmac.compare_digest(supplied, expected):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Valid internal API key required",
        headers={"WWW-Authenticate": "Bearer"},
    )
