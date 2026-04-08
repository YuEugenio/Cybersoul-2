"""LLM client builders for runnable Cybersoul instances."""

from __future__ import annotations

from agents.core.llm.client import OpenAICompatibleLLMClient
from agents.core.llm.config import LLMConfig

from instantiation.settings import RuntimeLLMSettings


def build_llm_config(settings: RuntimeLLMSettings | None = None) -> LLMConfig:
    """Create the project LLMConfig from environment-backed runtime settings."""

    active_settings = settings or RuntimeLLMSettings.from_env()
    return LLMConfig(
        api_key=active_settings.api_key,
        base_url=active_settings.base_url,
        model=active_settings.model_id,
        timeout_seconds=active_settings.timeout_seconds,
    )


def build_llm_client(
    settings: RuntimeLLMSettings | None = None,
) -> OpenAICompatibleLLMClient:
    """Create the default OpenAI-compatible LLM client for Cybersoul."""

    return OpenAICompatibleLLMClient(config=build_llm_config(settings=settings))
