"""
Unit tests for the ObserveAI Python SDK.

Tests the SDK initialization, interceptors, and client with mocked HTTP calls.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ── Test SDK initialization ──────────────────────────────

class TestInit:
    def test_init_validates_api_key(self):
        import observeai
        with pytest.raises(ValueError, match="obs_"):
            observeai.init(api_key="bad_key")

    def test_init_validates_empty_key(self):
        import observeai
        with pytest.raises(ValueError, match="required"):
            observeai.init(api_key="")

    def test_init_succeeds_with_valid_key(self):
        import observeai
        from observeai.config import get_config

        observeai.init(api_key="obs_test123", endpoint="http://test:8001")
        config = get_config()
        assert config.api_key == "obs_test123"
        assert config.endpoint == "http://test:8001"
        observeai.shutdown()

    def test_init_sets_custom_options(self):
        import observeai
        from observeai.config import get_config

        observeai.init(
            api_key="obs_test123",
            flush_interval_seconds=2.0,
            max_batch_size=20,
            timeout_seconds=10.0,
        )
        config = get_config()
        assert config.flush_interval_seconds == 2.0
        assert config.max_batch_size == 20
        assert config.timeout_seconds == 10.0
        observeai.shutdown()


# ── Test TraceEvent model ─────────────────────────────────

class TestTraceEvent:
    def test_to_dict_minimal(self):
        from observeai.models import TraceEvent

        event = TraceEvent(
            model="gpt-4o",
            prompt="hello",
            response="world",
            input_tokens=5,
            output_tokens=3,
            latency_ms=100,
        )
        d = event.to_dict()
        assert d["model"] == "gpt-4o"
        assert d["status"] == "success"
        assert "error_message" not in d
        assert "session_id" not in d

    def test_to_dict_with_error(self):
        from observeai.models import TraceEvent

        event = TraceEvent(
            model="gpt-4o",
            prompt="hello",
            response="",
            input_tokens=0,
            output_tokens=0,
            latency_ms=50,
            status="error",
            error_message="Rate limited",
        )
        d = event.to_dict()
        assert d["status"] == "error"
        assert d["error_message"] == "Rate limited"


# ── Test Client ───────────────────────────────────────────

class TestClient:
    def test_capture_enqueues_event(self):
        import observeai
        from observeai.client import get_client
        from observeai.models import TraceEvent

        observeai.init(api_key="obs_test123", enabled=False)

        client = get_client()
        event = TraceEvent(
            model="gpt-4o",
            prompt="test",
            response="response",
            input_tokens=10,
            output_tokens=5,
            latency_ms=100,
        )

        # When disabled, capture should be a no-op
        client.capture(event)
        observeai.shutdown()


# ── Test OpenAI interceptor ───────────────────────────────

class TestOpenAIInterceptor:
    def test_patch_and_unpatch(self):
        """Test that patching and unpatching works without openai installed."""
        from observeai.interceptors.openai_interceptor import (
            patch_openai,
            unpatch_openai,
        )

        # Should not raise even if openai is not installed
        patch_openai()
        unpatch_openai()

    def test_format_messages(self):
        from observeai.interceptors.openai_interceptor import _format_messages

        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ]
        result = _format_messages(messages)
        assert "[system] You are helpful" in result
        assert "[user] Hello" in result

    def test_format_messages_empty(self):
        from observeai.interceptors.openai_interceptor import _format_messages
        assert _format_messages([]) == ""
        assert _format_messages(None) == ""


# ── Test Anthropic interceptor ────────────────────────────

class TestAnthropicInterceptor:
    def test_patch_and_unpatch(self):
        """Test that patching and unpatching works without anthropic installed."""
        from observeai.interceptors.anthropic_interceptor import (
            patch_anthropic,
            unpatch_anthropic,
        )

        # Should not raise even if anthropic is not installed
        patch_anthropic()
        unpatch_anthropic()

    def test_format_messages_with_system(self):
        from observeai.interceptors.anthropic_interceptor import _format_messages

        messages = [{"role": "user", "content": "Hello"}]
        result = _format_messages(messages, system="Be concise")
        assert "[system] Be concise" in result
        assert "[user] Hello" in result

    def test_format_messages_structured_content(self):
        from observeai.interceptors.anthropic_interceptor import _format_messages

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is this?"},
                ],
            }
        ]
        result = _format_messages(messages)
        assert "What is this?" in result
