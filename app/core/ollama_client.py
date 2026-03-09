"""
Ollama LLM client — dual-GPU inference with async support.

Provides both chat completion and embedding generation.
Configured for Raghu's dual-GPU workstation.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings

logger = structlog.get_logger(__name__)


class OllamaManager:
    """Manages Ollama connections for chat + embeddings across dual GPUs."""

    def __init__(self):
        self._client: httpx.AsyncClient | None = None
        self._available: bool = False
        self._model_loaded: bool = False

    async def initialize(self) -> None:
        """Verify Ollama is running and model is available."""
        logger.info("initializing_ollama", base_url=settings.ollama_base_url)

        self._client = httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=httpx.Timeout(settings.ollama_timeout, connect=10.0),
        )

        try:
            resp = await self._client.get("/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            self._available = True

            if settings.ollama_model in models or any(
                settings.ollama_model in m for m in models
            ):
                self._model_loaded = True
                logger.info("ollama_ready", model=settings.ollama_model, models=models)
            else:
                logger.warning(
                    "model_not_found",
                    requested=settings.ollama_model,
                    available=models,
                    hint=f"Run: ollama pull {settings.ollama_model}",
                )
        except httpx.ConnectError:
            logger.warning("ollama_not_running", url=settings.ollama_base_url)
        except Exception as e:
            logger.error("ollama_init_error", error=str(e))

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
        logger.info("ollama_shutdown")

    @property
    def is_available(self) -> bool:
        return self._available and self._model_loaded

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        system: str | None = None,
        json_mode: bool = False,
    ) -> str:
        """
        Send a chat completion request to Ollama.

        Args:
            messages: List of {"role": "user"|"assistant"|"system", "content": "..."}
            model: Override model (defaults to settings)
            temperature: Sampling temperature
            max_tokens: Max output tokens
            system: System prompt (prepended to messages)
            json_mode: If True, request JSON output format
        """
        if not self._client:
            raise RuntimeError("Ollama not initialized")

        target_model = model or settings.ollama_model

        if system:
            messages = [{"role": "system", "content": system}] + messages

        payload: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_gpu": settings.ollama_num_gpu,
                "num_thread": settings.ollama_num_threads,
                "num_ctx": settings.ollama_context_length,
            },
        }

        if json_mode:
            payload["format"] = "json"

        resp = await self._client.post("/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

        return data.get("message", {}).get("content", "")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    async def embed(self, text: str, model: str | None = None) -> list[float]:
        """
        Generate embeddings using Ollama.
        Uses nomic-embed-text by default (768 dimensions).
        """
        if not self._client:
            raise RuntimeError("Ollama not initialized")

        target_model = model or settings.ollama_embed_model

        resp = await self._client.post(
            "/api/embeddings",
            json={"model": target_model, "prompt": text},
        )
        resp.raise_for_status()
        return resp.json().get("embedding", [])

    async def embed_batch(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        """Batch embed multiple texts concurrently."""
        tasks = [self.embed(t, model) for t in texts]
        return await asyncio.gather(*tasks)

    async def generate_structured(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate a structured JSON response from Ollama.
        Useful for agent tool outputs.
        """
        import json

        raw = await self.chat(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            system=system,
            json_mode=True,
            temperature=0.05,
        )

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("json_parse_failed", raw_length=len(raw))
            # Try to extract JSON from markdown fences
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
                return json.loads(raw)
            raise


# Singleton
ollama_manager = OllamaManager()
