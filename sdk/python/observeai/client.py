"""
HTTP client that sends trace events to the ObserveAI Ingest API.

Uses a background thread with batching for non-blocking operation.
"""

from __future__ import annotations

import atexit
import logging
import queue
import threading
import time
from typing import Optional

import httpx

from .config import get_config
from .models import TraceEvent

logger = logging.getLogger("observeai.client")


class ObserveAIClient:
    """Async-safe HTTP client with background batching."""

    def __init__(self) -> None:
        self._queue: queue.Queue[TraceEvent] = queue.Queue(maxsize=1000)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._started = False

    def start(self) -> None:
        """Start the background flush thread."""
        if self._started:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._thread.start()
        self._started = True
        atexit.register(self.shutdown)
        logger.debug("ObserveAI client started")

    def capture(self, event: TraceEvent) -> None:
        """Enqueue a trace event for background sending."""
        config = get_config()
        if not config.enabled:
            return
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            logger.warning("ObserveAI event queue full, dropping trace")

    def shutdown(self) -> None:
        """Flush remaining events and stop the background thread."""
        if not self._started:
            return
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        self._started = False
        logger.debug("ObserveAI client shut down")

    def _flush_loop(self) -> None:
        """Background loop that batches and sends events."""
        while not self._stop_event.is_set():
            batch: list[TraceEvent] = []
            config = get_config()

            # Collect events up to max_batch_size or flush_interval
            deadline = time.monotonic() + config.flush_interval_seconds
            while len(batch) < config.max_batch_size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    event = self._queue.get(timeout=min(remaining, 0.1))
                    batch.append(event)
                except queue.Empty:
                    continue

            if batch:
                self._send_batch(batch)

        # Final flush on shutdown
        remaining_batch: list[TraceEvent] = []
        while not self._queue.empty():
            try:
                remaining_batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if remaining_batch:
            self._send_batch(remaining_batch)

    def _send_batch(self, batch: list[TraceEvent]) -> None:
        """Send a batch of events to the Ingest API."""
        config = get_config()
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }

        for event in batch:
            try:
                with httpx.Client(timeout=config.timeout_seconds) as http:
                    resp = http.post(
                        f"{config.endpoint}/v1/traces",
                        json=event.to_dict(),
                        headers=headers,
                    )
                    if resp.status_code == 202:
                        logger.debug(
                            "Trace sent: %s",
                            resp.json().get("trace_id", "unknown"),
                        )
                    else:
                        logger.warning(
                            "Ingest API returned %d: %s",
                            resp.status_code,
                            resp.text[:200],
                        )
            except Exception as exc:
                logger.error("Failed to send trace: %s", exc)


# Global client singleton
_client: Optional[ObserveAIClient] = None


def get_client() -> ObserveAIClient:
    global _client
    if _client is None:
        _client = ObserveAIClient()
    return _client
