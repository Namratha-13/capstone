"""
Configuration — loads settings from environment variables.
"""

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    # ── Kafka ──────────────────────────────────
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_raw_traces: str = "raw-traces"

    # ── PostgreSQL ─────────────────────────────
    postgres_dsn: str = ""

    # ── Server ─────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8001

    @classmethod
    def from_env(cls) -> "Settings":
        pg_host = os.getenv("POSTGRES_HOST", "localhost")
        pg_port = os.getenv("POSTGRES_PORT", "5432")
        pg_db = os.getenv("POSTGRES_DB", "observeai")
        pg_user = os.getenv("POSTGRES_USER", "observeai")
        pg_pass = os.getenv("POSTGRES_PASSWORD", "localdev123")
        dsn = f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"

        return cls(
            kafka_bootstrap_servers=os.getenv(
                "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
            ),
            kafka_topic_raw_traces=os.getenv(
                "KAFKA_TOPIC_RAW_TRACES", "raw-traces"
            ),
            postgres_dsn=dsn,
            host=os.getenv("INGEST_API_HOST", "0.0.0.0"),
            port=int(os.getenv("INGEST_API_PORT", "8001")),
        )


# Singleton
settings = Settings.from_env()
