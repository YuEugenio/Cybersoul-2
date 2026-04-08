"""Agent-to-agent message envelope used by scene orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agents.core.messaging.message import Message, MessageRole


def _turn_id() -> str:
    return f"turn_{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentMessageEnvelope(BaseModel):
    """A lightweight internal A2A-style contract for scene-level turns."""

    model_config = ConfigDict(str_strip_whitespace=True)

    from_agent: str = Field(min_length=1)
    to_agent: str = Field(min_length=1)
    scene_id: str = Field(min_length=1)
    message_type: str = Field(default="scene_turn", min_length=1)
    intent: str = Field(default="scene_update", min_length=1)
    content: str = Field(min_length=1)
    tool_result: dict[str, Any] | None = None
    turn_id: str = Field(default_factory=_turn_id)
    causal_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)

    def to_message(self) -> Message:
        """Project the envelope into a semantic message for the receiver."""

        return Message(
            role=MessageRole.USER,
            content=self.content,
            created_at=self.created_at,
            metadata={
                "from_agent": self.from_agent,
                "to_agent": self.to_agent,
                "scene_id": self.scene_id,
                "message_type": self.message_type,
                "intent": self.intent,
                "turn_id": self.turn_id,
                "causal_ref": self.causal_ref,
                "tool_result": self.tool_result,
                "agent_envelope": self.model_dump(mode="json"),
                **self.metadata,
            },
        )
