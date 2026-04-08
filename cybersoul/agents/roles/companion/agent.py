"""Concrete companion agent assembled from the current core building blocks."""

from __future__ import annotations

from typing import Iterable

from agents.core.base.agent import BaseAgent
from agents.core.base.mode import BaseMode
from agents.roles.companion.profile import CompanionProfile
from agents.tools.base.tool import BaseTool
from agents.tools.registry.registry import ToolRegistry


class CompanionAgent(BaseAgent):
    """A concrete companion agent with profile and tool ownership."""

    def __init__(
        self,
        name: str,
        profile: CompanionProfile,
        tool_registry: ToolRegistry,
        default_mode: BaseMode | None = None,
    ):
        super().__init__(name=name, default_mode=default_mode)
        self.profile = profile
        self.tool_registry = tool_registry

    def register_tool(self, tool: BaseTool) -> None:
        self.tool_registry.register(tool)

    def register_tools(self, tools: Iterable[BaseTool]) -> None:
        for tool in tools:
            self.register_tool(tool)

    def list_tools(self) -> list[BaseTool]:
        return self.tool_registry.list_tools()

    def get_profile(self) -> CompanionProfile:
        return self.profile

    def get_profile_payload(self) -> dict:
        return self.profile.to_payload()
