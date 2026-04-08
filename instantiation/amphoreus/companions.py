"""Concrete companion builders for the Amphoreus instance."""

from __future__ import annotations

from pathlib import Path

from Phone.facade import PhoneFacade
from agents.modes.react.react_mode import ReActMode
from agents.roles.companion.agent import CompanionAgent
from agents.roles.companion.profile import CompanionProfile
from agents.tools.builtin.phone_tool import PhoneChatTool
from agents.tools.registry.registry import ToolRegistry
from world.core.manager import WorldManager

from instantiation.amphoreus import INSTANCE_ID
from instantiation.amphoreus.prompts import (
    CYRENE_SOUL_PROMPT_PATH,
    build_cyrene_system_prompt,
)
from instantiation.amphoreus.tools import TravelToPlaceTool
from instantiation.llm import build_llm_client


def build_cyrene_profile(
    persona_path: str | Path | None = None,
    enabled_tools: list[str] | None = None,
) -> CompanionProfile:
    """Create the current concrete profile for Cyrene."""

    resolved_path = Path(persona_path or CYRENE_SOUL_PROMPT_PATH).resolve()
    return CompanionProfile(
        id="cyrene",
        companion_name="昔涟",
        persona_path=str(resolved_path),
        default_mode="react",
        enabled_tools=list(enabled_tools or []),
        metadata={"world_instance": INSTANCE_ID},
    )


def build_cyrene_agent(
    *,
    llm_client=None,
    system_prompt: str | None = None,
    phone_facade: PhoneFacade | None = None,
    phone_store_path: str | None = None,
    world_manager: WorldManager | None = None,
    enable_phone_tool: bool = True,
    enable_travel_tool: bool = True,
) -> CompanionAgent:
    """Instantiate the runnable Cyrene companion for the Amphoreus instance."""

    tool_registry = ToolRegistry()
    enabled_tools: list[str] = []

    if enable_phone_tool:
        active_phone_facade = _build_phone_facade(
            phone_facade=phone_facade,
            phone_store_path=phone_store_path,
        )
        phone_tool = PhoneChatTool(
            phone_facade=active_phone_facade,
            companion_id="cyrene",
            user_id="user",
            title="昔涟",
        )
        tool_registry.register(phone_tool)
        enabled_tools.append(phone_tool.name)

    if enable_travel_tool and world_manager is not None:
        travel_tool = TravelToPlaceTool(
            world_manager=world_manager,
            actor_id="cyrene",
        )
        tool_registry.register(travel_tool)
        enabled_tools.append(travel_tool.name)

    active_llm_client = llm_client or build_llm_client()
    react_mode = ReActMode(
        name="react",
        llm_client=active_llm_client,
        tool_registry=tool_registry,
        system_prompt=system_prompt or build_cyrene_system_prompt(),
        max_steps=3,
    )
    return CompanionAgent(
        name="cyrene",
        profile=build_cyrene_profile(enabled_tools=enabled_tools),
        tool_registry=tool_registry,
        default_mode=react_mode,
    )


def _build_phone_facade(
    *,
    phone_facade: PhoneFacade | None,
    phone_store_path: str | None,
) -> PhoneFacade:
    if phone_facade is not None:
        return phone_facade
    if phone_store_path is not None:
        return PhoneFacade.from_store_path(phone_store_path)
    return PhoneFacade()


__all__ = [
    "build_cyrene_profile",
    "build_cyrene_agent",
]
