"""Minimal registry for tool discovery and execution."""

from __future__ import annotations

from agents.core.llm.schemas import LLMToolSpec
from agents.tools.base.tool import BaseTool, ToolResult


class ToolRegistry:
    """Stores tools and exposes a small execution surface for modes."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def to_llm_specs(self) -> list[LLMToolSpec]:
        return [tool.to_llm_spec() for tool in self.list_tools()]

    async def execute_tool(self, name: str, arguments: dict) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            raise ValueError(f"tool '{name}' is not registered")

        return await tool.execute(arguments)
