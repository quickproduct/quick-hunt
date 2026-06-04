"""LangChain Groq client factory.

Returns a ChatGroq LLM instance using the existing GROQ_API_KEY and GROQ_MODEL
settings so all AI calls share the same model configuration.

Pass a list of LangChain callbacks (e.g. a LangfuseCallbackHandler) to
get_langchain_llm / get_structured_llm to instrument each invocation.

Usage:
    from services.ai.observability import get_callback_handler

    handler = get_callback_handler("job_scoring", session_id=job_id)
    callbacks = [handler] if handler else []

    llm = get_structured_llm(JobRelevanceScore, callbacks=callbacks)
    result: JobRelevanceScore = await llm.ainvoke(prompt)
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from services.api.core.config import get_settings


def get_langchain_llm(
    max_tokens: int = 500,
    callbacks: list[Any] | None = None,
    model: str | None = None,
):
    """Return a ChatGroq instance wired to the configured Groq model.

    Args:
        max_tokens: Maximum tokens to generate.
        callbacks:  Optional LangChain callbacks (e.g. LangfuseCallbackHandler).
        model:      Optional model override (e.g. a smaller/faster scoring model).
                    Defaults to settings.groq_model.
    """
    from langchain_groq import ChatGroq

    settings = get_settings()
    return ChatGroq(
        api_key=settings.groq_api_key,
        model=model or settings.groq_model,
        max_tokens=max_tokens,
        temperature=0.3,
        request_timeout=30,
        # Automatically retry on 429 rate-limit errors using the Retry-After
        # header. Groq TPM limit (~12 000) is hit when many workflow tasks run
        # concurrently; 3 retries cover the 3-4 s wait Groq reports and turn
        # failures into successful (but slightly slower) calls instead of
        # falling back to template outputs.
        max_retries=5,
        callbacks=callbacks or [],
    )


def get_structured_llm(
    output_schema: type[BaseModel],
    max_tokens: int = 500,
    callbacks: list[Any] | None = None,
    model: str | None = None,
):
    """Return a ChatGroq LLM bound to produce structured output matching output_schema.

    Args:
        output_schema: Pydantic model class for structured output.
        max_tokens:    Maximum tokens to generate.
        callbacks:     Optional LangChain callbacks for observability.
        model:         Optional model override (defaults to settings.groq_model).
    """
    return get_langchain_llm(
        max_tokens=max_tokens, callbacks=callbacks, model=model
    ).with_structured_output(output_schema)
