"""
API-key authentication.

Validates the `Authorization: Bearer obs_xxx` header against the
PostgreSQL `api_keys` table. Returns tenant_id and project_id on success.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional, Tuple

import asyncpg
from fastapi import Depends, HTTPException, Request, status

from .config import settings

logger = logging.getLogger("observeai.auth")

# ── Connection pool (initialized at startup) ─────────────
_pool: Optional[asyncpg.Pool] = None


async def init_pg_pool() -> None:
    """Create the asyncpg connection pool."""
    global _pool
    _pool = await asyncpg.create_pool(dsn=settings.postgres_dsn, min_size=2, max_size=10)
    logger.info("PostgreSQL connection pool initialized")


async def close_pg_pool() -> None:
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        logger.info("PostgreSQL connection pool closed")


def _hash_key(raw_key: str) -> str:
    """SHA-256 hash used to look up keys in the DB."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def get_pg_pool() -> asyncpg.Pool:
    """Dependency that returns the pool (or raises if not ready)."""
    if _pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not ready",
        )
    return _pool


async def validate_api_key(
    request: Request,
    pool: asyncpg.Pool = Depends(get_pg_pool),
) -> dict:
    """
    FastAPI dependency that extracts and validates the API key.

    Returns dict with tenant_id, project_id, key_id.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header. Expected: Bearer obs_xxx",
        )

    raw_key = auth_header[7:].strip()
    if not raw_key.startswith("obs_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format. Keys must start with obs_",
        )

    key_hash = _hash_key(raw_key)

    row = await pool.fetchrow(
        """
        SELECT id, tenant_id, project_id, is_active
        FROM api_keys
        WHERE key_hash = $1
        """,
        key_hash,
    )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    if not row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key is deactivated",
        )

    # Update last_used_at in the background (fire-and-forget)
    await pool.execute(
        "UPDATE api_keys SET last_used_at = NOW() WHERE id = $1",
        row["id"],
    )

    return {
        "key_id": str(row["id"]),
        "tenant_id": str(row["tenant_id"]),
        "project_id": str(row["project_id"]),
    }


async def get_model_pricing(pool: asyncpg.Pool, model_id: str) -> Tuple[float, float]:
    """
    Look up per-1k-token pricing for a model.
    Returns (input_cost_per_1k, output_cost_per_1k). Defaults to (0, 0).
    """
    row = await pool.fetchrow(
        "SELECT input_cost_per_1k, output_cost_per_1k FROM model_pricing WHERE model_id = $1",
        model_id,
    )
    if row is None:
        return (0.0, 0.0)
    return (row["input_cost_per_1k"], row["output_cost_per_1k"])
