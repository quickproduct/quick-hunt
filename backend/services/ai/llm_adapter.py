"""LLM adapters — Groq (text) and Ollama (local), with singleton factory.

Groq uses the OpenAI-compatible API, so the openai SDK is used with a custom base_url.
NOTE: Groq does NOT provide an embeddings endpoint. When groq is the text provider,
embeddings fall back to Ollama (nomic-embed-text). If Ollama is unavailable, embedding
tasks are skipped and relevance scoring is disabled.
"""
import threading
from abc import ABC, abstractmethod
from typing import Optional

import structlog

from services.api.core.config import get_settings

logger = structlog.get_logger(__name__)

_adapter_lock = threading.Lock()
_adapter_instance: Optional["BaseLLMAdapter"] = None
_embedding_adapter_instance: Optional["BaseLLMAdapter"] = None


class BaseLLMAdapter(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 500,
    ) -> str:
        """Generate text completion."""
        ...

    @abstractmethod
    async def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding vector for text. Returns [] if not supported."""
        ...


class GroqAdapter(BaseLLMAdapter):
    """Groq cloud LLM adapter — uses OpenAI-compatible API.

    Supported models (as of 2024):
      - llama-3.3-70b-versatile  (recommended)
      - mixtral-8x7b-32768
      - gemma2-9b-it
      - llama-3.1-8b-instant     (fastest)

    Groq does NOT support embeddings — generate_embedding() always returns [].
    Use OllamaAdapter or a separate embedding provider for vectors.
    """

    GROQ_BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(self) -> None:
        from openai import AsyncOpenAI

        settings = get_settings()
        self._client = AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url=self.GROQ_BASE_URL,
        )
        self._model = settings.groq_model
        logger.info("llm_adapter_init", provider="groq", model=self._model)

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 500,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Instrument with Langfuse generation span (direct SDK — not LangChain).
        # langfuse v4 uses start_observation() instead of lf.generation().
        from services.ai.observability import get_langfuse
        lf = get_langfuse()
        span = None
        if lf:
            try:
                span = lf.start_observation(
                    name="groq_generate_text",
                    as_type="GENERATION",
                    model=self._model,
                    model_parameters={"max_tokens": max_tokens, "temperature": 0.7},
                    input=messages,
                )
            except Exception:
                span = None

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7,
            )
            text = response.choices[0].message.content or ""
            if span:
                try:
                    usage = response.usage
                    span.update(output=text)
                    span.end(
                        usage_details={
                            "input": usage.prompt_tokens if usage else 0,
                            "output": usage.completion_tokens if usage else 0,
                            "total": usage.total_tokens if usage else 0,
                        },
                    )
                except Exception:
                    pass
            return text
        except Exception as exc:
            if span:
                try:
                    span.end(level="ERROR", status_message=str(exc))
                except Exception:
                    pass
            raise

    async def generate_embedding(self, text: str) -> list[float]:
        """Groq has no embeddings API — returns empty list.

        The embedding task will fall back to OllamaEmbeddingAdapter if configured.
        """
        logger.debug("groq_no_embeddings_fallback_needed")
        return []


class OllamaAdapter(BaseLLMAdapter):
    """Ollama local LLM adapter — used as text provider OR embedding backend."""

    def __init__(self) -> None:
        import httpx

        settings = get_settings()
        self._host = settings.ollama_host
        self._model = settings.ollama_model
        self._embedding_model = settings.ollama_embedding_model
        self._client = httpx.AsyncClient(base_url=self._host, timeout=120)
        logger.info("llm_adapter_init", provider="ollama", model=self._model, host=self._host)

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 500,
    ) -> str:
        payload: dict = {
            "model": self._model,
            "prompt": prompt,
            "options": {"num_predict": max_tokens},
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt

        resp = await self._client.post("/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json().get("response", "")

    async def generate_embedding(self, text: str) -> list[float]:
        text = text[:8000]
        resp = await self._client.post(
            "/api/embeddings",
            json={"model": self._embedding_model, "prompt": text},
        )
        resp.raise_for_status()
        return resp.json().get("embedding", [])


class OllamaEmbeddingAdapter:
    """Lightweight embedding-only adapter for Ollama.

    Used when the text provider is Groq (which has no embeddings endpoint).
    Includes retry with exponential back-off for transient connection errors.
    """

    # Retry budget is sized to absorb an Ollama cold start: when Ollama is
    # KEDA-scaled to zero (see k8s/infrastructure/ollama.yaml), the first
    # embedding after idle must wait for pod scheduling + model load (~20–35 s).
    # Total wait ≈ 2+5+10+20 = 37 s before giving up. Embeddings are best-effort
    # and run on their own (concurrency=1) queue, so this never blocks the user
    # path or the scoring/cover pipeline.
    _MAX_RETRIES = 5
    _RETRY_DELAYS = (2, 5, 10, 20)  # seconds (len == _MAX_RETRIES - 1)

    def __init__(self) -> None:
        import httpx

        settings = get_settings()
        self._host = settings.ollama_host
        self._model = settings.ollama_embedding_model
        self._client = httpx.AsyncClient(base_url=self._host, timeout=60)
        logger.info("embedding_adapter_init", provider="ollama", model=self._model)

    async def generate_embedding(self, text: str) -> list[float]:
        import asyncio

        text = text[:8000]
        for attempt in range(self._MAX_RETRIES):
            try:
                resp = await self._client.post(
                    "/api/embeddings",
                    json={"model": self._model, "prompt": text},
                )
                resp.raise_for_status()
                return resp.json().get("embedding", [])
            except Exception as exc:
                is_last = attempt == self._MAX_RETRIES - 1
                if is_last:
                    logger.warning(
                        "embedding_failed_all_retries",
                        error=str(exc),
                        model=self._model,
                        attempts=self._MAX_RETRIES,
                    )
                    return []
                logger.debug(
                    "embedding_retry",
                    error=str(exc),
                    model=self._model,
                    attempt=attempt + 1,
                )
                await asyncio.sleep(self._RETRY_DELAYS[attempt])
        return []  # unreachable, but satisfies type checkers


def get_llm_adapter() -> BaseLLMAdapter:
    """Singleton — text generation adapter (Groq or Ollama)."""
    global _adapter_instance
    if _adapter_instance is None:
        with _adapter_lock:
            if _adapter_instance is None:
                settings = get_settings()
                if settings.llm_provider == "groq":
                    _adapter_instance = GroqAdapter()
                else:
                    _adapter_instance = OllamaAdapter()
    return _adapter_instance


def get_embedding_adapter() -> "OllamaEmbeddingAdapter | BaseLLMAdapter":
    """Singleton — embedding adapter.

    - If provider is ollama: reuse the OllamaAdapter (supports both text + embeddings).
    - If provider is groq: use OllamaEmbeddingAdapter as embedding-only backend.
    """
    global _embedding_adapter_instance
    if _embedding_adapter_instance is None:
        with _adapter_lock:
            if _embedding_adapter_instance is None:
                settings = get_settings()
                if settings.llm_provider == "groq":
                    _embedding_adapter_instance = OllamaEmbeddingAdapter()
                else:
                    # OllamaAdapter handles both text and embeddings
                    _embedding_adapter_instance = get_llm_adapter()
    return _embedding_adapter_instance
