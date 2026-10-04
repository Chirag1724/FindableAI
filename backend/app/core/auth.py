import hmac
import logging

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_auth = HTTPBearer(auto_error=False)


async def verify_api_key(
    header_key: str | None = Security(api_key_header),
    bearer_creds: HTTPAuthorizationCredentials | None = Security(bearer_auth),
) -> bool:
    """
    Enforces API key authentication when settings.API_KEY is defined.
    Accepts keys via 'X-API-Key' header or 'Authorization: Bearer <key>'.
    In development with no API_KEY set, requests are permitted.
    In production with no API_KEY set, a warning is logged.
    """
    configured_key = settings.API_KEY.strip()
    if not configured_key:
        if settings.ENVIRONMENT == "production":
            logger.warning("API_KEY is not configured in production environment; mutating requests are open.")
        return True

    provided_key = None
    if header_key and header_key.strip():
        provided_key = header_key.strip()
    elif bearer_creds and bearer_creds.credentials.strip():
        provided_key = bearer_creds.credentials.strip()

    if not provided_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key. Provide via 'X-API-Key' header or 'Authorization: Bearer <key>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(provided_key, configured_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True
