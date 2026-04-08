"""Minimal tool abstractions for the agents tool system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agents.core.llm.schemas import LLMToolSpec


class ToolResult(BaseModel):
    """Standardized result returned by tools."""

    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseTool(ABC):
    """Minimal async tool contract."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters_schema: dict[str, Any] | None = None,
    ):
        self.name = name
        self.description = description
        self.parameters_schema = parameters_schema or {
            "type": "object",
            "properties": {},
        }

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Execute the tool with structured arguments."""

    def to_llm_spec(self) -> LLMToolSpec:
        return LLMToolSpec(
            name=self.name,
            description=self.description,
            parameters_schema=self.parameters_schema,
        )
