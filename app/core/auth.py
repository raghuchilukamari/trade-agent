"""
Authentication & secrets management.
Mirrors app/core/auth.py from the architecture diagram.
Loads secrets from environment / vault.
"""

from __future__ import annotations

import os
from pathlib import Path

import structlog

from config.settings import settings

logger = structlog.get_logger(__name__)

VAULT_PATH = Path("/opt/spass/vault/secrets")


def get_auth_lifespan_initializer(name: str) -> dict[str, str]:
    """
    Load secrets from vault path or fall back to environment variables.
    Called during app lifespan startup.
    """
    secrets = {}

    # Try vault first (production)
    if VAULT_PATH.exists():
        for secret_file in VAULT_PATH.iterdir():
            if secret_file.is_file():
                secrets[secret_file.name] = secret_file.read_text().strip()
        logger.info("secrets_loaded_from_vault", count=len(secrets))
    else:
        # Fall back to env vars (development)
        secrets = {
            "polygon_api_key": settings.polygon_api_key,
            "postgres_password": settings.postgres_password,
        }
        logger.info("secrets_loaded_from_env", count=len(secrets))

    return secrets


def validate_api_key(api_key: str | None) -> bool:
    """Validate an incoming API key for protected endpoints."""
    if settings.app_env == "development":
        return True
    expected = os.getenv("TRADING_AGENT_API_KEY", "")
    return api_key == expected if expected else True
