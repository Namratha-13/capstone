"""
Pydantic models for trace event validation.
Matches the ClickHouse `observeai.traces` schema from Phase 1.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class TraceEventRequest(BaseModel):
    """Payload the SDK sends to POST /v1/traces."""

    model: str = Field(..., min_length=1, max_length=100, examples=["gpt-4o"])
    prompt: str = Field(..., min_length=1)
    response: str = Field(..., min_length=0)
    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)
    latency_ms: int = Field(..., ge=0)
    status: str = Field(default="success", pattern=r"^(success|error)$")
    error_message: Optional[str] = Field(default=None, max_length=2000)
    session_id: Optional[str] = Field(default=None)


class TraceEventEnriched(BaseModel):
    """
    Enriched event published to Kafka `raw-traces` topic.
    Adds tenant/project context and cost calculation.
    """

    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    project_id: str
    session_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    model: str
    prompt: str
    response: str
    input_tokens: int
    output_tokens: int
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int
    status: str
    error_message: Optional[str] = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def model_post_init(self, __context) -> None:
        if self.total_tokens == 0:
            object.__setattr__(
                self, "total_tokens", self.input_tokens + self.output_tokens
            )


class TraceEventResponse(BaseModel):
    """Response returned to the SDK after successful ingestion."""

    trace_id: str
    status: str = "accepted"
    message: str = "Trace event accepted for processing"
