from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update

from app.core.config import settings
from app.core.rate_limiter import enforce_rate_limit

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_auth = HTTPBearer(auto_error=False)


@dataclass
class TenantContext:
    org_id: uuid.UUID | None = None
    org_name: str | None = None
    plan_tier: str = "free"
    is_system_admin: bool = False
    api_key_id: uuid.UUID | None = None


def hash_api_key(raw_key: str) -> str:
    """Returns SHA-256 hex digest of the raw API key."""
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


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
    request: Request,
    header_key: str | None = Security(api_key_header),
    bearer_creds: HTTPAuthorizationCredentials | None = Security(bearer_auth),
) -> TenantContext:
    """Enforces API key authentication supporting:

    1. Static system API_KEY (dev/ops/admin).
    2. Dynamic organization-scoped API keys with token-bucket rate limiting.

    Attaches TenantContext to request.state.tenant for downstream route scoping.
    """
    configured_key = settings.API_KEY.strip()
    provided_key: str | None = None
    if header_key and header_key.strip():
        provided_key = header_key.strip()
    elif bearer_creds and bearer_creds.credentials.strip():
        provided_key = bearer_creds.credentials.strip()

    # If no key provided:
    if not provided_key:
        if not configured_key and not is_production_environment():
            ctx = TenantContext(is_system_admin=True)
            request.state.tenant = ctx
            return ctx

        if is_production_environment() and not configured_key:
            logger.error("API_KEY missing in production; rejecting request (fail-closed auth).")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Server misconfigured: API_KEY required in production.",
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key. Provide via 'X-API-Key' header or 'Authorization: Bearer <key>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. Check system static key bypass (constant-time)
    if configured_key and hmac.compare_digest(provided_key, configured_key):
        ctx = TenantContext(is_system_admin=True)
        request.state.tenant = ctx
        return ctx

    # 2. Check database for organization API key
    try:
        from app.db import AsyncSessionLocal
        from app.models.database import ApiKey, Organization

        hashed = hash_api_key(provided_key)
        async with AsyncSessionLocal() as session:
            stmt = (
                select(ApiKey, Organization)
                .join(Organization, ApiKey.org_id == Organization.id)
                .where(ApiKey.hashed_key == hashed)
            )
            result = await session.execute(stmt)
            row = result.first()
            if row is not None:
                api_key_row, org_row = row
                if api_key_row.revoked_at is not None:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="API Key has been revoked.",
                        headers={"WWW-Authenticate": "Bearer"},
                    )

                # Determine effective rate limit (key override or org plan limit)
                limit_per_min = (
                    api_key_row.rate_limit_per_min
                    if api_key_row.rate_limit_per_min is not None
                    else org_row.rate_limit_per_min
                )

                # Enforce token-bucket rate limit per organization
                await enforce_rate_limit(f"org:{org_row.id}", limit_per_min)

                # Update last_used_at best-effort
                try:
                    await session.execute(
                        update(ApiKey)
                        .where(ApiKey.id == api_key_row.id)
                        .values(last_used_at=datetime.now(UTC))
                    )
                    await session.commit()
                except Exception:
                    pass

                ctx = TenantContext(
                    org_id=org_row.id,
                    org_name=org_row.name,
                    plan_tier=org_row.plan_tier,
                    is_system_admin=False,
                    api_key_id=api_key_row.id,
                )
                request.state.tenant = ctx
                return ctx
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("Database API key lookup failed or uninitialized: %s", exc)

    # Key did not match system key or active DB key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API Key.",
        headers={"WWW-Authenticate": "Bearer"},
    )
