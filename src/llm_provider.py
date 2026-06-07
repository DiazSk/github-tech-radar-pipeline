"""Provider-agnostic LLM factory.

The whole pipeline is decoupled from any specific LLM vendor. Swap providers
by setting LLM_PROVIDER (ollama | openai | anthropic) in the environment.
Locally this defaults to Ollama (free, runs on your GPU); in CI you can flip
to a cloud model with a single env var plus the matching API key.
"""
from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from . import config


def get_llm() -> BaseChatModel:
    """Return a chat model configured from environment variables."""
    provider = config.LLM_PROVIDER

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=config.OLLAMA_MODEL,
            base_url=config.OLLAMA_BASE_URL,
            temperature=0,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=config.OPENAI_MODEL, temperature=0)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=config.ANTHROPIC_MODEL, temperature=0)

    raise ValueError(
        f"Unknown LLM_PROVIDER={provider!r}. Use one of: ollama, openai, anthropic."
    )
