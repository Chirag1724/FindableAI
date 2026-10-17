"""Shared helpers for disposable PostgreSQL + pgvector integration tests."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.models.database import Base

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def integration_enabled() -> bool:
    return os.environ.get("FINDABLE_PG_INTEGRATION", "").lower() in ("1", "true", "yes")


def allow_remote() -> bool:
    return os.environ.get("FINDABLE_PG_ALLOW_REMOTE", "").lower() in ("1", "true", "yes")


def normalize_async_url(url: str) -> str:
    u = (url or "").strip()
    if u.startswith("postgres://"):
        u = "postgresql+asyncpg://" + u[len("postgres://") :]
    elif u.startswith("postgresql://") and "+asyncpg" not in u:
        u = "postgresql+asyncpg://" + u[len("postgresql://") :]
    return u


def resolve_pg_url() -> str:
    raw = os.environ.get("FINDABLE_PG_DATABASE_URL") or settings.DATABASE_URL
    return normalize_async_url(raw)


def assert_disposable_url(url: str) -> None:
    if "sqlite" in url:
        pytest.fail("PostgreSQL integration tests refuse sqlite DATABASE_URL")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in _LOOPBACK_HOSTS and not allow_remote():
        pytest.fail(
            f"Refusing PostgreSQL integration against non-loopback host {host!r}. "
            "Use 127.0.0.1/localhost disposable Postgres, or set "
            "FINDABLE_PG_ALLOW_REMOTE=1 only for an explicitly disposable remote."
        )
    db_name = (parsed.path or "").lstrip("/")
    blocked = {"prod", "production", "live"}
    if db_name.lower() in blocked and not allow_remote():
        pytest.fail(
            f"Refusing database name {db_name!r} without FINDABLE_PG_ALLOW_REMOTE=1"
        )


def admin_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path="/postgres"))


def db_name(url: str) -> str:
    name = (urlparse(url).path or "").lstrip("/")
    if not name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        pytest.fail(f"Unsafe or missing PostgreSQL database name in URL: {name!r}")
    return name


async def ensure_database_exists(url: str) -> None:
    db = db_name(url)
    admin = create_async_engine(admin_url(url), isolation_level="AUTOCOMMIT", pool_pre_ping=True)
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


async def reset_public_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


async def create_all_with_vector(engine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)


def run_alembic_upgrade(url: str, revision: str = "head") -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    exe = Path(sys.executable)
    candidates = [
        [str(exe), "-P", "-m", "alembic", "upgrade", revision],
        [str(exe.parent / "alembic.exe"), "upgrade", revision],
        [str(exe.parent / "Scripts" / "alembic.exe"), "upgrade", revision],
        [str(exe.parent / "alembic"), "upgrade", revision],
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


def run_alembic_downgrade(url: str, revision: str = "base") -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    exe = Path(sys.executable)
    candidates = [
        [str(exe), "-P", "-m", "alembic", "downgrade", revision],
        [str(exe.parent / "alembic.exe"), "downgrade", revision],
        [str(exe.parent / "Scripts" / "alembic.exe"), "downgrade", revision],
        [str(exe.parent / "alembic"), "downgrade", revision],
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
    raise RuntimeError(f"alembic downgrade failed\n{last_err}")


PG_SKIP_REASON = (
    "Set FINDABLE_PG_INTEGRATION=1 with a disposable PostgreSQL+pgvector URL "
    "(prefer FINDABLE_PG_DATABASE_URL on loopback)"
)
