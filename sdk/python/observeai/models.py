"""
Trace event model used by the SDK.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TraceEvent:
    """Represents a single LLM call trace."""

    model: str
    prompt: str
    response: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    status: str = "success"
    error_message: Optional[str] = None
    session_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization (matches Ingest API schema)."""
        data = {
            "model": self.model,
            "prompt": self.prompt,
            "response": self.response,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": self.latency_ms,
            "status": self.status,
        }
        if self.error_message is not None:
            data["error_message"] = self.error_message
        if self.session_id is not None:
            data["session_id"] = self.session_id
        return data
