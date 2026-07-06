"""
ObserveAI Ingest API — FastAPI application.

POST /v1/traces  →  validate → enrich (cost) → publish to Kafka → 202 Accepted
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, status

from .auth import (
    close_pg_pool,
    get_model_pricing,
    get_pg_pool,
    init_pg_pool,
    validate_api_key,
)
from .config import settings
from .kafka_producer import publish_trace, start_producer, stop_producer
from .models import TraceEventEnriched, TraceEventRequest, TraceEventResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s  %(message)s",
)
logger = logging.getLogger("observeai.ingest")


# ── Lifespan ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    logger.info("Starting Ingest API …")
    await init_pg_pool()
    await start_producer()
    logger.info("Ingest API ready on %s:%s", settings.host, settings.port)
    yield
    await stop_producer()
    await close_pg_pool()
    logger.info("Ingest API shut down")


app = FastAPI(
    title="ObserveAI Ingest API",
    version="0.1.0",
    description="Receives LLM trace events, enriches them, publishes to Kafka.",
    lifespan=lifespan,
)


# ── Health ────────────────────────────────────────────────
@app.get("/healthz", tags=["infra"])
async def healthz():
    return {"status": "ok", "service": "ingest-api"}


# ── Ingest endpoint ──────────────────────────────────────
@app.post(
    "/v1/traces",
    response_model=TraceEventResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["traces"],
)
async def ingest_trace(
    body: TraceEventRequest,
    auth: dict = Depends(validate_api_key),
    pool: asyncpg.Pool = Depends(get_pg_pool),
):
    """
    Accept a trace event from the SDK.

    1. Validate API key (done by dependency)
    2. Calculate cost from model_pricing table
    3. Build enriched event
    4. Publish to Kafka raw-traces topic
    5. Return 202 with trace_id
    """
    # ── Cost calculation ───────────────────────────────
    input_cost_per_1k, output_cost_per_1k = await get_model_pricing(pool, body.model)
    cost_usd = (
        (body.input_tokens / 1000) * input_cost_per_1k
        + (body.output_tokens / 1000) * output_cost_per_1k
    )

    # ── Build enriched event ───────────────────────────
    enriched = TraceEventEnriched(
        tenant_id=auth["tenant_id"],
        project_id=auth["project_id"],
        session_id=body.session_id or None,
        model=body.model,
        prompt=body.prompt,
        response=body.response,
        input_tokens=body.input_tokens,
        output_tokens=body.output_tokens,
        total_tokens=body.input_tokens + body.output_tokens,
        cost_usd=round(cost_usd, 8),
        latency_ms=body.latency_ms,
        status=body.status,
        error_message=body.error_message,
    )

    # ── Publish to Kafka ───────────────────────────────
    try:
        await publish_trace(enriched.model_dump())
    except Exception as exc:
        logger.error("Kafka publish failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Event queue unavailable, please retry",
        ) from exc

    logger.info(
        "Trace %s ingested | model=%s cost=$%.6f",
        enriched.trace_id,
        enriched.model,
        enriched.cost_usd,
    )

    return TraceEventResponse(trace_id=enriched.trace_id)
