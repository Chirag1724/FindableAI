import hmac
import logging

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_auth = HTTPBearer(auto_error=False)


def is_production_environment() -> bool:
    return settings.ENVIRONMENT.strip().lower() == "production"


def production_api_key_configured() -> bool:
    return bool(settings.API_KEY.strip())


def assert_production_security_config() -> None:
    """Fail closed: production must have a non-empty API_KEY.

    Development/test may run without an API key intentionally.
    """
    if is_production_environment() and not production_api_key_configured():
        raise RuntimeError(
            "Refusing to start: ENVIRONMENT=production requires a non-empty API_KEY. "
            "Unauthenticated mutating access is not permitted in production."
        )


async def verify_api_key(
    header_key: str | None = Security(api_key_header),
    bearer_creds: HTTPAuthorizationCredentials | None = Security(bearer_auth),
) -> bool:
    """
    Enforces API key authentication when settings.API_KEY is defined.
    Accepts keys via 'X-API-Key' header or 'Authorization: Bearer <key>'.

    Production without API_KEY is rejected at startup/readiness; if somehow
    reached, this dependency also fails closed (401) rather than allowing open access.
    """
    configured_key = settings.API_KEY.strip()
    if not configured_key:
        if is_production_environment():
            logger.error(
                "API_KEY missing in production; rejecting request (fail-closed auth)."
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Server misconfigured: API_KEY required in production.",
            )
        # Explicit development/test behavior: open when API_KEY unset.
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
