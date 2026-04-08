"""Configuration models for the LLM layer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LLMConfig(BaseModel):
    """Minimal configuration required by the current LLM integration."""

    model_config = ConfigDict(str_strip_whitespace=True)

    api_key: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    timeout_seconds: float = Field(default=60.0, gt=0)
    stream: bool = False
