"""
Unit tests for the Ingest API.

These tests mock PostgreSQL and Kafka so they run without infrastructure.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Patch external dependencies before importing app ──────

# Mock asyncpg pool
mock_pool = AsyncMock()

# Mock Kafka producer
mock_kafka_send = AsyncMock()


def _make_api_key():
    """Generate a test API key and its hash."""
    raw = "obs_test1234567890"
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


RAW_KEY, KEY_HASH = _make_api_key()
TENANT_ID = str(uuid.uuid4())
PROJECT_ID = str(uuid.uuid4())
KEY_ID = str(uuid.uuid4())


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_externals():
    """Patch PostgreSQL and Kafka for all tests."""
    with (
        patch("app.auth._pool", mock_pool),
        patch("app.kafka_producer._producer") as mock_producer,
    ):
        # Reset mocks
        mock_pool.reset_mock()

        # Configure fetchrow for API key validation
        async def mock_fetchrow(query, *args):
            if "api_keys" in query and args[0] == KEY_HASH:
                return {
                    "id": uuid.UUID(KEY_ID),
                    "tenant_id": uuid.UUID(TENANT_ID),
                    "project_id": uuid.UUID(PROJECT_ID),
                    "is_active": True,
                }
            if "model_pricing" in query:
                return {
                    "input_cost_per_1k": 0.005,
                    "output_cost_per_1k": 0.015,
                }
            return None

        mock_pool.fetchrow = AsyncMock(side_effect=mock_fetchrow)
        mock_pool.execute = AsyncMock()

        # Configure Kafka producer mock
        mock_producer.send_and_wait = AsyncMock()

        yield


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


VALID_PAYLOAD = {
    "model": "gpt-4o",
    "prompt": "Hello, world!",
    "response": "Hi there!",
    "input_tokens": 10,
    "output_tokens": 5,
    "latency_ms": 250,
    "status": "success",
}


# ── Tests ─────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_healthz_returns_ok(self, client):
        resp = client.get("/healthz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "ingest-api"


class TestAuthentication:
    def test_missing_auth_header_returns_401(self, client):
        resp = client.post("/v1/traces", json=VALID_PAYLOAD)
        assert resp.status_code == 401
        assert "Authorization" in resp.json()["detail"]

    def test_malformed_auth_header_returns_401(self, client):
        resp = client.post(
            "/v1/traces",
            json=VALID_PAYLOAD,
            headers={"Authorization": "Basic abc123"},
        )
        assert resp.status_code == 401

    def test_invalid_key_prefix_returns_401(self, client):
        resp = client.post(
            "/v1/traces",
            json=VALID_PAYLOAD,
            headers={"Authorization": "Bearer bad_key123"},
        )
        assert resp.status_code == 401
        assert "obs_" in resp.json()["detail"]

    def test_unknown_key_returns_401(self, client):
        resp = client.post(
            "/v1/traces",
            json=VALID_PAYLOAD,
            headers={"Authorization": "Bearer obs_unknownkey"},
        )
        assert resp.status_code == 401


class TestValidation:
    def test_missing_model_returns_422(self, client):
        payload = {**VALID_PAYLOAD}
        del payload["model"]
        resp = client.post(
            "/v1/traces",
            json=payload,
            headers={"Authorization": f"Bearer {RAW_KEY}"},
        )
        assert resp.status_code == 422

    def test_negative_tokens_returns_422(self, client):
        payload = {**VALID_PAYLOAD, "input_tokens": -1}
        resp = client.post(
            "/v1/traces",
            json=payload,
            headers={"Authorization": f"Bearer {RAW_KEY}"},
        )
        assert resp.status_code == 422

    def test_invalid_status_returns_422(self, client):
        payload = {**VALID_PAYLOAD, "status": "unknown"}
        resp = client.post(
            "/v1/traces",
            json=payload,
            headers={"Authorization": f"Bearer {RAW_KEY}"},
        )
        assert resp.status_code == 422


class TestIngestion:
    def test_valid_trace_returns_202(self, client):
        resp = client.post(
            "/v1/traces",
            json=VALID_PAYLOAD,
            headers={"Authorization": f"Bearer {RAW_KEY}"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"
        assert "trace_id" in data

    def test_response_contains_valid_uuid_trace_id(self, client):
        resp = client.post(
            "/v1/traces",
            json=VALID_PAYLOAD,
            headers={"Authorization": f"Bearer {RAW_KEY}"},
        )
        trace_id = resp.json()["trace_id"]
        # Should be a valid UUID
        uuid.UUID(trace_id)

    def test_error_trace_accepted(self, client):
        payload = {
            **VALID_PAYLOAD,
            "status": "error",
            "error_message": "Rate limit exceeded",
        }
        resp = client.post(
            "/v1/traces",
            json=payload,
            headers={"Authorization": f"Bearer {RAW_KEY}"},
        )
        assert resp.status_code == 202
