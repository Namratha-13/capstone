"""
Anthropic interceptor — wraps `anthropic.messages.create` to auto-capture traces.

Works by monkey-patching the `create` method on `Messages` so that
every call is transparently instrumented without changing user code.
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any

from ..client import get_client
from ..models import TraceEvent

logger = logging.getLogger("observeai.interceptors.anthropic")

_original_create = None
_patched = False


def patch_anthropic() -> None:
    """Monkey-patch the Anthropic SDK to intercept message creation."""
    global _original_create, _patched

    if _patched:
        return

    try:
        from anthropic.resources.messages import Messages
    except ImportError:
        logger.debug("anthropic package not installed, skipping Anthropic interceptor")
        return

    _original_create = Messages.create

    @functools.wraps(_original_create)
    def wrapped_create(self: Any, *args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()

        try:
            result = _original_create(self, *args, **kwargs)

            # Extract response content
            response_text = ""
            if hasattr(result, "content") and result.content:
                # Anthropic returns a list of content blocks
                text_blocks = [
                    block.text
                    for block in result.content
                    if hasattr(block, "text")
                ]
                response_text = "\n".join(text_blocks)

            # Extract token usage
            input_tokens = 0
            output_tokens = 0
            if hasattr(result, "usage") and result.usage:
                input_tokens = getattr(result.usage, "input_tokens", 0) or 0
                output_tokens = getattr(result.usage, "output_tokens", 0) or 0

            latency_ms = int((time.perf_counter() - start) * 1000)

            # Build prompt string from messages
            messages = kwargs.get("messages", [])
            system = kwargs.get("system", "")
            prompt_str = _format_messages(messages, system)

            event = TraceEvent(
                model=kwargs.get("model", "unknown"),
                prompt=prompt_str,
                response=response_text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                status="success",
            )
            get_client().capture(event)
            return result

        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            messages = kwargs.get("messages", [])
            system = kwargs.get("system", "")
            prompt_str = _format_messages(messages, system)

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

    Messages.create = wrapped_create
    _patched = True
    logger.info("Anthropic messages interceptor installed")


def unpatch_anthropic() -> None:
    """Restore the original Anthropic create method."""
    global _original_create, _patched

    if not _patched or _original_create is None:
        return

    try:
        from anthropic.resources.messages import Messages
        Messages.create = _original_create
        _patched = False
        logger.info("Anthropic interceptor removed")
    except ImportError:
        pass


def _format_messages(messages: Any, system: str = "") -> str:
    """Convert Anthropic messages list to a readable prompt string."""
    parts = []
    if system:
        parts.append(f"[system] {system}")
    if not messages:
        return "\n".join(parts)
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                # Anthropic supports structured content blocks
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                content = "\n".join(text_parts)
            parts.append(f"[{role}] {content}")
        else:
            parts.append(str(msg))
    return "\n".join(parts)
