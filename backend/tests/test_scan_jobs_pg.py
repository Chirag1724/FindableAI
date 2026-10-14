"""PostgreSQL integration tests for durable jobs (SKIP LOCKED / concurrency).

Requires an **explicit opt-in** and a **disposable** PostgreSQL + pgvector database.

  FINDABLE_PG_INTEGRATION=1 \\
  FINDABLE_PG_DATABASE_URL='postgresql+asyncpg://findable:findable_secret@127.0.0.1:55432/findable_itest' \\
  pytest tests/test_scan_jobs_pg.py -q

Safety policy:
- Skips unless ``FINDABLE_PG_INTEGRATION`` is truthy.
- Refuses sqlite URLs.
- Refuses non-loopback hosts unless ``FINDABLE_PG_ALLOW_REMOTE=1`` (fail closed).
- Prefer ``FINDABLE_PG_DATABASE_URL`` over app ``DATABASE_URL`` so local/prod
  app settings are not reused by accident.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.jobs.queue import claim_next_job, enqueue_scan_job, request_fingerprint
from app.jobs.states import JobStatus
from app.models.database import Base, ScanJob

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _integration_enabled() -> bool:
    return os.environ.get("FINDABLE_PG_INTEGRATION", "").lower() in ("1", "true", "yes")


def _allow_remote() -> bool:
    return os.environ.get("FINDABLE_PG_ALLOW_REMOTE", "").lower() in ("1", "true", "yes")


def _normalize_async_url(url: str) -> str:
    u = (url or "").strip()
    if u.startswith("postgres://"):
        u = "postgresql+asyncpg://" + u[len("postgres://") :]
    elif u.startswith("postgresql://") and "+asyncpg" not in u:
        u = "postgresql+asyncpg://" + u[len("postgresql://") :]
    return u


def _resolve_pg_url() -> str:
    """Prefer dedicated integration URL; fall back to settings only when local."""
    raw = os.environ.get("FINDABLE_PG_DATABASE_URL") or settings.DATABASE_URL
    return _normalize_async_url(raw)


def _assert_disposable_url(url: str) -> None:
    """Fail closed: never run destructive schema resets against non-local DBs."""
    if "sqlite" in url:
        pytest.fail("PostgreSQL integration tests refuse sqlite DATABASE_URL")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in _LOOPBACK_HOSTS and not _allow_remote():
        pytest.fail(
            f"Refusing PostgreSQL integration against non-loopback host {host!r}. "
            "Use 127.0.0.1/localhost disposable Postgres, or set "
            "FINDABLE_PG_ALLOW_REMOTE=1 only for an explicitly disposable remote."
        )
    # Heuristic: block common production-ish DB names unless overridden.
    db_name = (parsed.path or "").lstrip("/")
    blocked = {"prod", "production", "live"}
    if db_name.lower() in blocked and not _allow_remote():
        pytest.fail(
            f"Refusing database name {db_name!r} without FINDABLE_PG_ALLOW_REMOTE=1"
        )


def _admin_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path="/postgres"))


def _db_name(url: str) -> str:
    name = (urlparse(url).path or "").lstrip("/")
    if not name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        pytest.fail(f"Unsafe or missing PostgreSQL database name in URL: {name!r}")
    return name


async def _ensure_database_exists(url: str) -> None:
    """Create the target database if missing (connects via /postgres)."""
    db = _db_name(url)
    admin = create_async_engine(_admin_url(url), isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    try:
        async with admin.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :n"),
                {"n": db},
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{db}"'))
    finally:
        await admin.dispose()


async def _reset_public_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


async def _create_all_with_vector(engine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)


def _run_alembic_upgrade(url: str) -> None:
    """Apply Alembic migrations to ``url`` from a clean database.

    Invokes Alembic in a subprocess with ``python -P`` so cwd ``backend/``
    cannot shadow the installed Alembic package via the local migrations
    directory named ``alembic/``. ``DATABASE_URL`` is passed in the child env
    so ``app.core.config.settings`` binds to the disposable database.
    """
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    exe = Path(sys.executable)
    candidates = [
        [str(exe), "-P", "-m", "alembic", "upgrade", "head"],
        [str(exe.parent / "alembic.exe"), "upgrade", "head"],
        [str(exe.parent / "Scripts" / "alembic.exe"), "upgrade", "head"],
        [str(exe.parent / "alembic"), "upgrade", "head"],
    ]
    last_err = ""
    for cmd in candidates:
        if cmd[0].endswith(("alembic.exe", "alembic")) and not Path(cmd[0]).exists():
            continue
        proc = subprocess.run(
            cmd,
            cwd=str(_BACKEND_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return
        last_err = (
            f"cmd={cmd!r} exit={proc.returncode}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    raise RuntimeError(f"alembic upgrade failed\n{last_err}")


pytestmark = pytest.mark.skipif(
    not _integration_enabled(),
    reason=(
        "Set FINDABLE_PG_INTEGRATION=1 with a disposable PostgreSQL+pgvector URL "
        "(prefer FINDABLE_PG_DATABASE_URL on loopback)"
    ),
)


@pytest_asyncio.fixture
async def pg_url() -> str:
    if not _integration_enabled():
        pytest.skip("FINDABLE_PG_INTEGRATION not enabled")
    url = _resolve_pg_url()
    _assert_disposable_url(url)
    try:
        await _ensure_database_exists(url)
    except Exception as exc:
        pytest.skip(f"PostgreSQL admin/bootstrap unavailable: {exc}")
    # Connectivity probe
    engine = create_async_engine(url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    await engine.dispose()
    return url


@pytest_asyncio.fixture
async def pg_session(pg_url: str):
    """Function-scoped session on a reset disposable schema (ORM create_all)."""
    engine = create_async_engine(pg_url, pool_pre_ping=True)
    try:
        await _reset_public_schema(engine)
        await _create_all_with_vector(engine)
    except Exception as exc:
        await engine.dispose()
        pytest.fail(f"Failed to prepare disposable schema with pgvector: {exc}")

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_pg_two_workers_cannot_claim_same_job(pg_session: AsyncSession, pg_url: str):
    fp = request_fingerprint(
        url="https://example.com/pg-claim", max_pages=1, personas=None, repo_url=None
    )
    async with pg_session.begin():
        await enqueue_scan_job(
            pg_session,
            scan_uuid=uuid.uuid4(),
            url="https://example.com/pg-claim",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=f"auto:{fp}-{uuid.uuid4().hex[:8]}",
            fingerprint=fp,
        )

    async def _claim(worker: str):
        engine = create_async_engine(pg_url, pool_pre_ping=True)
        try:
            factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with factory() as s:
                async with s.begin():
                    return await claim_next_job(s, worker_id=worker, lease_seconds=60)
        finally:
            await engine.dispose()

    c1, c2 = await asyncio.gather(_claim("pg-w1"), _claim("pg-w2"))
    claimed = [c for c in (c1, c2) if c is not None]
    assert len(claimed) == 1

    job = await pg_session.get(ScanJob, claimed[0].job_id)
    assert job is not None
    assert job.status == JobStatus.CLAIMED.value


@pytest.mark.asyncio
async def test_pg_migration_head_reachable(pg_url: str):
    """From a clean schema, Alembic upgrade head must create durable job columns."""
    engine = create_async_engine(pg_url, pool_pre_ping=True)
    try:
        await _reset_public_schema(engine)
        # Intentionally do NOT create_all — migrations are the source of truth.
        _run_alembic_upgrade(pg_url)

        async with engine.connect() as conn:
            ext = await conn.scalar(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            )
            assert ext == 1

            fencing = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'scan_jobs' AND column_name = 'fencing_token'"
                )
            )
            assert fencing.first() is not None

            # 0006 progress/checkpoint columns must exist at head.
            checkpoint = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'scan_jobs' AND column_name = 'checkpoint_json'"
                )
            )
            assert checkpoint.first() is not None

            progress = await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = 'scan_progress_events'"
                )
            )
            assert progress.first() is not None

            rev = await conn.scalar(text("SELECT version_num FROM alembic_version"))
            assert rev == "0006_progress_checkpoints"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_pg_lease_recovery_and_fencing(pg_session: AsyncSession):
    from datetime import UTC, datetime, timedelta

    from app.jobs.queue import complete_job

    fp = request_fingerprint(
        url="https://example.com/pg-lease", max_pages=1, personas=None, repo_url=None
    )
    async with pg_session.begin():
        await enqueue_scan_job(
            pg_session,
            scan_uuid=uuid.uuid4(),
            url="https://example.com/pg-lease",
            max_pages=1,
            personas=None,
            repo_url=None,
            idempotency_key=f"auto:{fp}-{uuid.uuid4().hex[:8]}",
            fingerprint=fp,
        )

    async with pg_session.begin():
        c1 = await claim_next_job(pg_session, worker_id="lease-w1", lease_seconds=1)
        assert c1 is not None
        job = await pg_session.get(ScanJob, c1.job_id)
        assert job is not None
        job.status = JobStatus.RUNNING.value
        job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=5)

    async with pg_session.begin():
        c2 = await claim_next_job(pg_session, worker_id="lease-w2", lease_seconds=60)
        assert c2 is not None
        assert c2.fencing_token > c1.fencing_token

    async with pg_session.begin():
        assert (
            await complete_job(
                pg_session,
                job_id=c1.job_id,
                fencing_token=c1.fencing_token,
                worker_id="lease-w1",
            )
            is False
        )
        assert (
            await complete_job(
                pg_session,
                job_id=c2.job_id,
                fencing_token=c2.fencing_token,
                worker_id="lease-w2",
            )
            is True
        )
