"""
Async Kafka producer — publishes enriched trace events to the `raw-traces` topic.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from aiokafka import AIOKafkaProducer

from .config import settings

logger = logging.getLogger("observeai.kafka")

_producer: Optional[AIOKafkaProducer] = None


async def start_producer() -> None:
    """Initialize and start the Kafka producer."""
    global _producer
    _producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
        acks="all",
        max_request_size=1_048_576,  # 1 MB
        linger_ms=5,
        compression_type="gzip",
    )
    await _producer.start()
    logger.info(
        "Kafka producer started → %s", settings.kafka_bootstrap_servers
    )


async def stop_producer() -> None:
    """Flush and stop the Kafka producer."""
    global _producer
    if _producer:
        await _producer.stop()
        logger.info("Kafka producer stopped")


async def publish_trace(event: dict) -> None:
    """
    Publish an enriched trace event to the raw-traces topic.
    Uses tenant_id as partition key for ordering.
    """
    if _producer is None:
        raise RuntimeError("Kafka producer not initialized")

    await _producer.send_and_wait(
        topic=settings.kafka_topic_raw_traces,
        key=event.get("tenant_id", "unknown"),
        value=event,
    )
    logger.debug("Published trace %s to %s", event.get("trace_id"), settings.kafka_topic_raw_traces)
