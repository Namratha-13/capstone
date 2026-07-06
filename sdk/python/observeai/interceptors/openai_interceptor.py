"""
OpenAI interceptor — wraps `openai.chat.completions.create` to auto-capture traces.

Works by monkey-patching the `create` method on `ChatCompletions` so that
every call is transparently instrumented without changing user code.
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any

from ..client import get_client
from ..models import TraceEvent

logger = logging.getLogger("observeai.interceptors.openai")

_original_create = None
_original_async_create = None
_patched = False


def patch_openai() -> None:
    """Monkey-patch the OpenAI SDK to intercept chat completions."""
    global _original_create, _original_async_create, _patched

    if _patched:
        return

    try:
        from openai.resources.chat.completions import Completions, AsyncCompletions
    except ImportError:
        logger.debug("openai package not installed, skipping OpenAI interceptor")
        return

    _original_create = Completions.create

    @functools.wraps(_original_create)
    def wrapped_create(self: Any, *args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        error_msg = None
        status = "success"
        response_text = ""

        try:
            result = _original_create(self, *args, **kwargs)

            # Extract response content
            if hasattr(result, "choices") and result.choices:
                choice = result.choices[0]
                if hasattr(choice, "message") and hasattr(choice.message, "content"):
                    response_text = choice.message.content or ""

            # Extract token usage
            input_tokens = 0
            output_tokens = 0
            if hasattr(result, "usage") and result.usage:
                input_tokens = getattr(result.usage, "prompt_tokens", 0) or 0
                output_tokens = getattr(result.usage, "completion_tokens", 0) or 0

            latency_ms = int((time.perf_counter() - start) * 1000)

            # Build prompt string from messages
            messages = kwargs.get("messages", args[0] if args else [])
            prompt_str = _format_messages(messages)

            event = TraceEvent(
                model=kwargs.get("model", "unknown"),
                prompt=prompt_str,
                response=response_text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                status=status,
            )
            get_client().capture(event)
            return result

        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            messages = kwargs.get("messages", args[0] if args else [])
            prompt_str = _format_messages(messages)

            event = TraceEvent(
                model=kwargs.get("model", "unknown"),
                prompt=prompt_str,
                response="",
                input_tokens=0,
                output_tokens=0,
                latency_ms=latency_ms,
                status="error",
                error_message=str(exc)[:2000],
            )
            get_client().capture(event)
            raise

    Completions.create = wrapped_create
    _patched = True
    logger.info("OpenAI chat completions interceptor installed")


def unpatch_openai() -> None:
    """Restore the original OpenAI create method."""
    global _original_create, _patched

    if not _patched or _original_create is None:
        return

    try:
        from openai.resources.chat.completions import Completions
        Completions.create = _original_create
        _patched = False
        logger.info("OpenAI interceptor removed")
    except ImportError:
        pass


def _format_messages(messages: Any) -> str:
    """Convert OpenAI messages list to a readable prompt string."""
    if not messages:
        return ""
    if isinstance(messages, str):
        return messages
    parts = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            parts.append(f"[{role}] {content}")
        else:
            parts.append(str(msg))
    return "\n".join(parts)
