"""Unified request and response contracts for the LLM layer."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from agents.core.messaging.message import Message


class LLMToolSpec(BaseModel):
    """Tool definition exposed to the model."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    parameters_schema: dict[str, Any] = Field(default_factory=dict)


class LLMToolCall(BaseModel):
    """Structured tool call returned by the model."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class LLMRequest(BaseModel):
    """Canonical non-provider-specific LLM request."""

    model_config = ConfigDict(use_enum_values=False)

    messages: list[Message] = Field(default_factory=list)
    tools: list[LLMToolSpec] = Field(default_factory=list)
    temperature: Optional[float] = Field(default=None, ge=0)
    max_tokens: Optional[int] = Field(default=None, gt=0)
    stream: Optional[bool] = None


class LLMUsage(BaseModel):
    """Token usage reported by the model provider."""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class LLMResponse(BaseModel):
    """Canonical non-streaming LLM response."""

    model_config = ConfigDict(use_enum_values=False)

    message: Optional[Message] = None
    tool_calls: list[LLMToolCall] = Field(default_factory=list)
    usage: Optional[LLMUsage] = None
    finish_reason: Optional[str] = None
    model: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMChunk(BaseModel):
    """Canonical streaming chunk returned by the LLM layer."""

    model_config = ConfigDict(use_enum_values=False)

    delta_text: str = ""
    tool_call_deltas: list[LLMToolCall] = Field(default_factory=list)
    finish_reason: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
