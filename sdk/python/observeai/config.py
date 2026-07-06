"""
SDK configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ObserveAIConfig:
    """Global SDK configuration."""

    api_key: str = ""
    endpoint: str = "http://localhost:8001"
    enabled: bool = True
    flush_interval_seconds: float = 1.0
    max_batch_size: int = 10
    timeout_seconds: float = 5.0

    def validate(self) -> None:
        if not self.api_key:
            raise ValueError("ObserveAI api_key is required")
        if not self.api_key.startswith("obs_"):
            raise ValueError("ObserveAI api_key must start with 'obs_'")
        if not self.endpoint:
            raise ValueError("ObserveAI endpoint is required")


# Global config singleton
_config: Optional[ObserveAIConfig] = None


def get_config() -> ObserveAIConfig:
    if _config is None:
        raise RuntimeError("ObserveAI SDK not initialized. Call observeai.init() first.")
    return _config


def set_config(config: ObserveAIConfig) -> None:
    global _config
    _config = config
