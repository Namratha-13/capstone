"""
ClickHouse client wrapper using clickhouse-connect.
Provides robust batch writing with retry logic.
"""

import logging
import time
from typing import List, Dict, Any
import clickhouse_connect
from config import settings

logger = logging.getLogger("observeai.clickhouse")

class ClickHouseClient:
    def __init__(self):
        self.client = None

    def connect(self) -> None:
        """Establish connection to ClickHouse server."""
        try:
            logger.info(
                "Connecting to ClickHouse at %s:%s (DB: %s)",
                settings.clickhouse_host,
                settings.clickhouse_port,
                settings.clickhouse_db,
            )
            self.client = clickhouse_connect.get_client(
                host=settings.clickhouse_host,
                port=settings.clickhouse_port,
                username=settings.clickhouse_user,
                password=settings.clickhouse_password,
                database=settings.clickhouse_db,
            )
            logger.info("Successfully connected to ClickHouse")
        except Exception as e:
            logger.error("Failed to connect to ClickHouse: %s", e)
            self.client = None
            raise

    def close(self) -> None:
        """Close ClickHouse connection client."""
        if self.client:
            try:
                self.client.close()
                logger.info("Closed ClickHouse connection")
            except Exception as e:
                logger.error("Error closing ClickHouse connection: %s", e)
            finally:
                self.client = None

    def ensure_connected(self) -> None:
        """Helper to verify connection or reconnect if down."""
        if self.client is None:
            self.connect()
        else:
            try:
                # Ping ClickHouse to verify connection
                self.client.command("SELECT 1")
            except Exception:
                logger.warning("ClickHouse connection ping failed, attempting reconnect...")
                self.connect()

    def insert_batch(self, table: str, rows: List[List[Any]], columns: List[str]) -> bool:
        """
        Insert a batch of rows into the specified ClickHouse table.
        Retries up to 3 times with exponential backoff on failure.
        """
        if not rows:
            return True

        self.ensure_connected()
        
        max_retries = 3
        backoff = 1.0

        for attempt in range(1, max_retries + 1):
            try:
                self.client.insert(table, rows, column_names=columns)
                logger.info("Inserted %d rows into ClickHouse table %s", len(rows), table)
                return True
            except Exception as e:
                logger.error(
                    "Insert to ClickHouse failed (Attempt %d/%d): %s",
                    attempt,
                    max_retries,
                    e,
                )
                if attempt == max_retries:
                    raise
                time.sleep(backoff)
                backoff *= 2.0
                # Force reconnect on retry
                try:
                    self.connect()
                except Exception:
                    pass

        return False
