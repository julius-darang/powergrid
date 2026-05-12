"""asyncpg pool — single global instance, opened in FastAPI lifespan."""
from __future__ import annotations
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg

DEFAULT_DSN = 'postgresql://powergrid:powergrid@localhost:5432/powergrid'

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    """Create the global pool. Idempotent."""
    global _pool
    if _pool is None:
        dsn = os.environ.get('DATABASE_URL', DEFAULT_DSN)
        # Modest pool — single-process dev server, low concurrency.
        _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=8)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """FastAPI dependency. Pool must be initialised via lifespan first."""
    if _pool is None:
        raise RuntimeError('asyncpg pool not initialised — check app lifespan')
    return _pool


@asynccontextmanager
async def acquire() -> AsyncIterator[asyncpg.Connection]:
    pool = get_pool()
    async with pool.acquire() as conn:
        yield conn
