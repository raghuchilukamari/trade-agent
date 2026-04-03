"""
Centralized application settings loaded from environment variables.
Dual-GPU and threading configs tuned for Raghu's workstation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────
    app_name: str = "trading-agent"
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # ── Polygon ──────────────────────────────────────
    polygon_api_key: str = ""

    # ── Massive API ──────────────────────────────────
    massive_api_key: str = ""

    # ── Ollama ───────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:9b"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_num_gpu: int = 2
    ollama_num_threads: int = 16
    ollama_context_length: int = 32768
    ollama_timeout: int = 120

    # ── PostgreSQL ───────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "trading_agent"
    postgres_password: str = ""
    postgres_db: str = "trading_agent"
    postgres_pool_size: int = 20
    postgres_max_overflow: int = 10

    # ── Data Paths ───────────────────────────────────
    flow_data_dir: str = "/media/SHARED/trade-data/formatted"
    summary_output_dir: str = "/media/SHARED/trade-data/summaries/docx"
    prior_summaries_dir: str = "/media/SHARED/trade-data/summaries"

    # ── Worker Config ────────────────────────────────
    daily_pipeline_cron: str = "0 7 * * 1-5"
    max_concurrent_agents: int = 4
    agent_timeout_seconds: int = 300

    # ── UI / CORS ────────────────────────────────────
    dashboard_url: str = "http://localhost:3000"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── WebSocket ────────────────────────────────────
    ws_heartbeat_interval: int = 30

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def flow_data_path(self) -> Path:
        return Path(self.flow_data_dir)

    @property
    def summary_output_path(self) -> Path:
        return Path(self.summary_output_dir)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v


settings = Settings()
