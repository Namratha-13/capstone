"""
ObserveAI Stream Processor Consumer.
Consumes enriched trace events from Kafka and writes them to ClickHouse in batches.
"""

import asyncio
import json
import logging
import signal
import sys
import uuid
from datetime import datetime
from typing import List, Dict, Any
from aiokafka import AIOKafkaConsumer

from config import settings
from clickhouse_client import ClickHouseClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s  %(message)s",
)
logger = logging.getLogger("observeai.kafka_consumer")

# ClickHouse trace table column order matching db/clickhouse/init.sql
CLICKHOUSE_COLUMNS = [
    "trace_id",
    "tenant_id",
    "project_id",
    "session_id",
    "model",
    "prompt",
    "response",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cost_usd",
    "latency_ms",
    "status",
    "error_message",
    "created_at",
]

class KafkaConsumerApp:
    def __init__(self):
        self.ch_client = ClickHouseClient()
        self.consumer = None
        self.buffer: List[List[Any]] = []
        self.buffer_lock = asyncio.Lock()
        self.is_running = True
        self.flush_task = None

    def setup_signal_handlers(self):
        """Register SIGINT and SIGTERM handlers to trigger graceful shutdown."""
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))
        except NotImplementedError:
            # Signal handlers via loop.add_signal_handler are not implemented on Windows
            pass

    def prepare_row(self, event: Dict[str, Any]) -> List[Any]:
        """Format and validate trace event dict into a ClickHouse table row list."""
        trace_id = event.get("trace_id") or str(uuid.uuid4())
        tenant_id = event.get("tenant_id") or str(uuid.uuid4())
        project_id = event.get("project_id") or str(uuid.uuid4())
        
        # ClickHouse session_id and error_message are non-nullable. 
        # Fall back to empty/zero-value fields if not set.
        session_id = event.get("session_id") or "00000000-0000-0000-0000-000000000000"
        error_message = event.get("error_message") or ""

        # Parse created_at ISO 8601 string to a datetime object
        created_at_str = event.get("created_at")
        if created_at_str:
            try:
                # Replace 'Z' with +00:00 offset for standard Python fromisoformat compatibility
                if created_at_str.endswith("Z"):
                    created_at_str = created_at_str[:-1] + "+00:00"
                created_at = datetime.fromisoformat(created_at_str)
            except ValueError:
                logger.warning("Failed to parse created_at string: %s, using current time", created_at_str)
                created_at = datetime.utcnow()
        else:
            created_at = datetime.utcnow()

        return [
            trace_id,
            tenant_id,
            project_id,
            session_id,
            str(event.get("model", "unknown")),
            str(event.get("prompt", "")),
            str(event.get("response", "")),
            int(event.get("input_tokens", 0)),
            int(event.get("output_tokens", 0)),
            int(event.get("total_tokens", 0)),
            float(event.get("cost_usd", 0.0)),
            int(event.get("latency_ms", 0)),
            str(event.get("status", "success")),
            str(error_message),
            created_at,
        ]

    async def flush_buffer(self) -> None:
        """Write trace events in the buffer into ClickHouse."""
        async with self.buffer_lock:
            if not self.buffer:
                return
            rows_to_insert = list(self.buffer)
            self.buffer.clear()

        logger.info("Flushing %d traces to ClickHouse...", len(rows_to_insert))
        try:
            self.ch_client.insert_batch("traces", rows_to_insert, CLICKHOUSE_COLUMNS)
        except Exception as e:
            logger.error("Failed to insert batch into ClickHouse: %s. Restoring buffer.", e)
            # Put the rows back at the front of the buffer so we don't lose data
            async with self.buffer_lock:
                self.buffer = rows_to_insert + self.buffer

    async def flush_periodically_loop(self):
        """Task that runs continuously to flush the buffer at regular intervals."""
        while self.is_running:
            try:
                await asyncio.sleep(settings.batch_timeout_seconds)
                if self.buffer:
                    await self.flush_buffer()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Exception in periodic flush task: %s", e)

    async def run(self):
        """Initialize connections and start consumption loop."""
        logger.info("Initializing ObserveAI Kafka Consumer...")
        self.setup_signal_handlers()

        # Connect to ClickHouse
        self.ch_client.connect()

        # Start Kafka Consumer
        self.consumer = AIOKafkaConsumer(
            settings.kafka_topic_raw_traces,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.kafka_consumer_group,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="earliest",
            enable_auto_commit=True,
        )

        logger.info("Connecting to Kafka bootstrap servers: %s", settings.kafka_bootstrap_servers)
        await self.consumer.start()
        logger.info("Successfully subscribed to Kafka topic: %s", settings.kafka_topic_raw_traces)

        # Start background timer flusher
        self.flush_task = asyncio.create_task(self.flush_periodically_loop())

        try:
            async for msg in self.consumer:
                if not self.is_running:
                    break

                try:
                    event = msg.value
                    if not isinstance(event, dict):
                        logger.warning("Ignored non-dict event payload: %s", event)
                        continue

                    row = self.prepare_row(event)
                    
                    async with self.buffer_lock:
                        self.buffer.append(row)
                        current_size = len(self.buffer)

                    # Trigger flush immediately if batch size threshold is met
                    if current_size >= settings.batch_size_threshold:
                        logger.info("Buffer threshold reached (%d/%d), flushing immediately", current_size, settings.batch_size_threshold)
                        await self.flush_buffer()

                except Exception as e:
                    logger.error("Error processing consumed record: %s", e)

        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Safely flush buffers and release consumer/client resources."""
        if not self.is_running:
            return

        self.is_running = False
        logger.info("Shutdown initiated. Cleaning up resources...")

        # Cancel periodic flush task
        if self.flush_task:
            self.flush_task.cancel()
            try:
                await self.flush_task
            except asyncio.CancelledError:
                pass

        # Stop consuming from Kafka
        if self.consumer:
            logger.info("Stopping Kafka consumer...")
            await self.consumer.stop()

        # Flush any remaining items in the buffer
        if self.buffer:
            logger.info("Flushing final %d traces to ClickHouse...", len(self.buffer))
            await self.flush_buffer()

        # Disconnect ClickHouse
        self.ch_client.close()
        logger.info("Shutdown finalized.")

def main():
    app = KafkaConsumerApp()
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logger.info("Terminated via keyboard interrupt.")
    except Exception as e:
        logger.critical("Unhandled critical failure: %s", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
