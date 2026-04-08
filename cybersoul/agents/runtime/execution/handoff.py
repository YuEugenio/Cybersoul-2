"""Structured handoff artifacts left behind after each runtime turn."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agents.context import ContextPacket
from agents.core.messaging.mode_result import ModeResult
from world.core.state import ActorState, WorldState


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class RuntimeHandoffSummary:
    """A compact structured summary that helps the next turn get oriented fast."""

    actor_id: str
    profile_name: str
    summary_text: str
    created_at: datetime = field(default_factory=_utc_now)
    current_time: datetime | None = None
    current_place_id: str | None = None
    current_activity_type: str | None = None
    finish_reason: str | None = None
    latest_assistant_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_turn(
        cls,
        *,
        actor_id: str,
        profile_name: str,
        world_state: WorldState | None,
        actor_state: ActorState | None,
        result: ModeResult,
    ) -> "RuntimeHandoffSummary":
        latest_assistant_message = None
        for message in reversed(result.messages):
            if message.role.value == "assistant" and message.content.strip():
                latest_assistant_message = message.content.strip()
                break

        current_activity_type = None
        if actor_state is not None and actor_state.current_activity_block is not None:
            current_activity_type = actor_state.current_activity_block.activity_type

        summary_parts = [
            f"actor_id: {actor_id}",
            f"profile: {profile_name}",
        ]
        if world_state is not None:
            summary_parts.append(f"world_time: {world_state.current_time.isoformat()}")
        if actor_state is not None:
            summary_parts.append(f"current_place_id: {actor_state.current_place_id}")
        if current_activity_type is not None:
            summary_parts.append(f"current_activity_type: {current_activity_type}")
        summary_parts.append(f"finish_reason: {result.finish_reason.value}")
        if result.summary:
            summary_parts.append("mode_summary: " + result.summary)
        if latest_assistant_message:
            summary_parts.append("latest_assistant_message: " + latest_assistant_message)

        return cls(
            actor_id=actor_id,
            profile_name=profile_name,
            summary_text="\n".join(summary_parts),
            current_time=world_state.current_time if world_state is not None else None,
            current_place_id=actor_state.current_place_id if actor_state is not None else None,
            current_activity_type=current_activity_type,
            finish_reason=result.finish_reason.value,
            latest_assistant_message=latest_assistant_message,
            metadata={
                "mode_summary": result.summary,
            },
        )

    def to_packet(self) -> ContextPacket:
        """Expose the handoff summary as a context packet for the next turn."""

        return ContextPacket(
            kind="handoff",
            section="context",
            content="recent_runtime_handoff:\n" + self.summary_text,
            timestamp=self.created_at,
            relevance_score=0.82,
            metadata={
                "actor_id": self.actor_id,
                "profile_name": self.profile_name,
                **self.metadata,
            },
        )

    def to_payload(self) -> dict[str, Any]:
        """Serialize the summary for metadata or future persistence."""

        payload: dict[str, Any] = {
            "actor_id": self.actor_id,
            "profile_name": self.profile_name,
            "summary_text": self.summary_text,
            "created_at": self.created_at.isoformat(),
        }
        if self.current_time is not None:
            payload["current_time"] = self.current_time.isoformat()
        if self.current_place_id is not None:
            payload["current_place_id"] = self.current_place_id
        if self.current_activity_type is not None:
            payload["current_activity_type"] = self.current_activity_type
        if self.finish_reason is not None:
            payload["finish_reason"] = self.finish_reason
        if self.latest_assistant_message is not None:
            payload["latest_assistant_message"] = self.latest_assistant_message
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload
