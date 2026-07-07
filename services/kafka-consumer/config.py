"""
Configuration settings for the Kafka consumer.
Loads environment variables, matching patterns in ingest-api.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    # ── Kafka ──────────────────────────────────
    kafka_bootstrap_servers: str
    kafka_topic_raw_traces: str
    kafka_consumer_group: str

    # ── ClickHouse ─────────────────────────────
    clickhouse_host: str
    clickhouse_port: int
    clickhouse_db: str
    clickhouse_user: str
    clickhouse_password: str

    # ── Batching ───────────────────────────────
    batch_size_threshold: int
    batch_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            kafka_bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            kafka_topic_raw_traces=os.getenv("KAFKA_TOPIC_RAW_TRACES", "raw-traces"),
            kafka_consumer_group=os.getenv("KAFKA_CONSUMER_GROUP", "observeai-consumer-group"),
            clickhouse_host=os.getenv("CLICKHOUSE_HOST", "localhost"),
            clickhouse_port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            clickhouse_db=os.getenv("CLICKHOUSE_DB", "observeai"),
            clickhouse_user=os.getenv("CLICKHOUSE_USER", "default"),
            clickhouse_password=os.getenv("CLICKHOUSE_PASSWORD", ""),
            batch_size_threshold=int(os.getenv("BATCH_SIZE_THRESHOLD", "500")),
            batch_timeout_seconds=float(os.getenv("BATCH_TIMEOUT_SECONDS", "2.0")),
        )

settings = Settings.from_env()
