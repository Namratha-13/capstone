"""
ObserveAI Python SDK — auto-instrument LLM calls.

Usage:
    import observeai
    observeai.init(api_key="obs_xxx", endpoint="http://localhost:8001")

    # All subsequent OpenAI / Anthropic calls are auto-instrumented.
    from openai import OpenAI
    client = OpenAI()
    response = client.chat.completions.create(model="gpt-4o", messages=[...])
"""

from __future__ import annotations

from .client import get_client
from .config import ObserveAIConfig, set_config
from .interceptors.anthropic_interceptor import patch_anthropic, unpatch_anthropic
from .interceptors.openai_interceptor import patch_openai, unpatch_openai
from .models import TraceEvent

__version__ = "0.1.0"


def init(
    api_key: str,
    endpoint: str = "http://localhost:8001",
    enabled: bool = True,
    flush_interval_seconds: float = 1.0,
    max_batch_size: int = 10,
    timeout_seconds: float = 5.0,
) -> None:
    """
    Initialize the ObserveAI SDK.

    This patches OpenAI and Anthropic SDKs so all LLM calls are
    automatically captured and sent to the ObserveAI Ingest API.

    Args:
        api_key: Your ObserveAI API key (starts with obs_).
        endpoint: The ObserveAI Ingest API URL.
        enabled: Set to False to disable tracing.
        flush_interval_seconds: How often to flush batched events.
        max_batch_size: Max events per batch.
        timeout_seconds: HTTP timeout for sending events.
    """
    config = ObserveAIConfig(
        api_key=api_key,
        endpoint=endpoint,
        enabled=enabled,
        flush_interval_seconds=flush_interval_seconds,
        max_batch_size=max_batch_size,
        timeout_seconds=timeout_seconds,
    )
    config.validate()
    set_config(config)

    # Start background client
    client = get_client()
    client.start()

    # Install interceptors
    if enabled:
        patch_openai()
        patch_anthropic()


def shutdown() -> None:
    """Flush pending events and remove interceptors."""
    get_client().shutdown()
    unpatch_openai()
    unpatch_anthropic()


def capture(event: TraceEvent) -> None:
    """Manually capture a trace event (for non-intercepted calls)."""
    get_client().capture(event)
