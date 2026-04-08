"""Instance-specific tools for Amphoreus world actions and scene activities."""

from __future__ import annotations

import random
from datetime import timedelta
from typing import Any, Callable

from agents.tools.base.tool import BaseTool, ToolResult
from world.core.manager import WorldManager
from world.core.state import ActivityBlock, ActorState

from instantiation.amphoreus.world_graph import (
    TRANSIT_PLACE_ID,
    estimate_travel_minutes,
    list_supported_place_ids,
    place_display_name,
)


class TravelToPlaceTool(BaseTool):
    """Move an actor into an explicit travel activity toward a destination."""

    def __init__(
        self,
        *,
        world_manager: WorldManager,
        actor_id: str = "cyrene",
        estimator: Callable[[str, str], int] | None = None,
    ) -> None:
        super().__init__(
            name="travel_to_place",
            description=(
                "Leave the current scene and begin traveling toward another known "
                "place in Amphoreus. Use this when you decide to actually go "
                "somewhere, not when you are only thinking about it."
            ),
            parameters_schema={
                "type": "object",
                "properties": {
                    "destination_place_id": {
                        "type": "string",
                        "enum": list(list_supported_place_ids()),
                    },
                },
                "required": ["destination_place_id"],
            },
        )
        self.world_manager = world_manager
        self.actor_id = actor_id
        self.estimator = estimator or estimate_travel_minutes

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        destination_place_id = self._require(arguments, "destination_place_id")
        actor_state = self.world_manager.get_actor_state(self.actor_id)
        if actor_state is None:
            raise ValueError("actor state is unavailable for travel")

        current_activity = actor_state.current_activity_block
        if current_activity is not None and current_activity.activity_type == "travel":
            current_destination = str(
                current_activity.payload.get("destination_place_id", "")
            ).strip()
            if current_destination:
                return ToolResult(
                    content=(
                        "你已经在赶路中了。"
                        f" 当前目的地是{place_display_name(current_destination)}，"
                        "不需要再次出发。"
                    ),
                    data={
                        "status": "already_travelling",
                        "destination_place_id": current_destination,
                    },
                )
            raise ValueError("actor is already travelling")

        origin_place_id = actor_state.current_place_id
        if origin_place_id == TRANSIT_PLACE_ID:
            raise ValueError("actor is already between scenes")
        if destination_place_id == origin_place_id:
            return ToolResult(
                content=(
                    "你已经在"
                    + place_display_name(destination_place_id)
                    + "了，不需要再次赶路。"
                ),
                data={
                    "status": "already_there",
                    "destination_place_id": destination_place_id,
                },
            )

        current_time = self.world_manager.state.current_time
        travel_minutes = self.estimator(origin_place_id, destination_place_id)
        arrival_time = current_time + timedelta(minutes=travel_minutes)
        next_state = ActorState(
            actor_id=self.actor_id,
            current_place_id=TRANSIT_PLACE_ID,
            current_activity_block=ActivityBlock(
                activity_type="travel",
                started_at=current_time,
                planned_until=arrival_time,
                payload={
                    "from_place_id": origin_place_id,
                    "destination_place_id": destination_place_id,
                    "travel_minutes": travel_minutes,
                },
            ),
        )
        self.world_manager.set_actor_state(next_state)

        return ToolResult(
            content=(
                f"已离开{place_display_name(origin_place_id)}，开始前往"
                f"{place_display_name(destination_place_id)}。"
                f" 预计耗时约 {travel_minutes} 分钟，抵达时间为 {arrival_time.isoformat()}。"
                " 在抵达之前，当地驻场 NPC 不会被激活。"
            ),
            data={
                "status": "travelling",
                "from_place_id": origin_place_id,
                "destination_place_id": destination_place_id,
                "travel_minutes": travel_minutes,
                "arrival_time": arrival_time.isoformat(),
                "current_place_id": TRANSIT_PLACE_ID,
            },
            metadata={
                "scene_transition": "departed_scene",
            },
        )

    def _require(self, arguments: dict[str, Any], key: str) -> str:
        value = str(arguments.get(key, "")).strip()
        if not value:
            raise ValueError("missing required argument: " + key)
        return value


class TribbieDivinationTool(BaseTool):
    """Generate a lightweight divination result for Tribbie scene turns."""

    _DEFAULT_OUTCOMES: tuple[dict[str, str], ...] = (
        {
            "omen": "吉",
            "image": "灯火顺风而上",
            "guidance": "现在适合轻一点地靠近，把想说的话先说出一半。",
        },
        {
            "omen": "凶",
            "image": "钟声被风折回",
            "guidance": "眼下不宜急着往前推，先把真正害怕的事说清楚。",
        },
        {
            "omen": "未明",
            "image": "星盘停在两道缝隙之间",
            "guidance": "答案还没有完全落下，再等一小会儿会比立刻判断更好。",
        },
    )

    def __init__(
        self,
        *,
        chooser: Callable[[tuple[dict[str, str], ...]], dict[str, str]] | None = None,
    ) -> None:
        super().__init__(
            name="tribbie_divination",
            description=(
                "Perform a small divination in Tribbie's observatory scene and "
                "return a concrete omen result that can be discussed in-scene."
            ),
            parameters_schema={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "focus": {"type": "string"},
                },
            },
        )
        self.chooser = chooser or (lambda outcomes: random.choice(list(outcomes)))

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        outcome = self.chooser(self._DEFAULT_OUTCOMES)
        question = str(arguments.get("question", "")).strip()
        focus = str(arguments.get("focus", "")).strip()

        prompt_bits: list[str] = []
        if question:
            prompt_bits.append("question=" + question)
        if focus:
            prompt_bits.append("focus=" + focus)

        content_lines = [
            "占兆结果:",
            f"- omen: {outcome['omen']}",
            f"- image: {outcome['image']}",
            f"- guidance: {outcome['guidance']}",
        ]
        if prompt_bits:
            content_lines.append("- requested_with: " + ", ".join(prompt_bits))

        return ToolResult(
            content="\n".join(content_lines),
            data={
                "omen": outcome["omen"],
                "image": outcome["image"],
                "guidance": outcome["guidance"],
                "question": question or None,
                "focus": focus or None,
            },
        )


__all__ = [
    "TravelToPlaceTool",
    "TribbieDivinationTool",
]
