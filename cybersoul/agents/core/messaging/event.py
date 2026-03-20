"""Core runtime event contracts shared across the agent stack."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .message import Message


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _event_id() -> str:
    return f"evt_{uuid4().hex}"


class EventType(str, Enum):
    """Abstract event categories that can trigger runtime execution."""

    PERCEPTION = "perception"
    MESSAGE = "message"
    TIMER = "timer"
    STATE = "state"
    TOOL_RESULT = "tool_result"
    COMMAND = "command"
    SYSTEM = "system"


class EventSource(str, Enum):
    """High-level origins of runtime events."""

    GUI_AGENT = "gui_agent"
    WORLD = "world"
    SCHEDULER = "scheduler"
    TOOL = "tool"
    RUNTIME = "runtime"
    SYSTEM = "system"
    API = "api"


class AgentEvent(BaseModel):
    """Canonical runtime event object used to wake and drive agents."""

    model_config = ConfigDict(use_enum_values=False)

    id: str = Field(default_factory=_event_id)
    type: EventType
    source: EventSource
    message: Message | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    causation_id: str | None = None
    priority: int = Field(default=0)
    occurred_at: datetime = Field(default_factory=_utc_now)
    created_at: datetime = Field(default_factory=_utc_now)

    @model_validator(mode="after")
    def validate_event_shape(self) -> "AgentEvent":
        if self.message is None and not self.payload:
            raise ValueError("event requires at least one of message or payload")

        if self.type is EventType.MESSAGE and self.message is None:
            raise ValueError("message event requires a message")

        return self

    @property
    def has_message(self) -> bool:
        return self.message is not None

    @property
    def is_perception_only(self) -> bool:
        return self.type is EventType.PERCEPTION and self.message is None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "type": self.type.value,
            "source": self.source.value,
            "priority": self.priority,
            "occurred_at": self.occurred_at.isoformat(),
            "created_at": self.created_at.isoformat(),
        }

        if self.message is not None:
            payload["message"] = self.message.to_payload()
        if self.payload:
            payload["payload"] = self.payload
        if self.metadata:
            payload["metadata"] = self.metadata
        if self.correlation_id:
            payload["correlation_id"] = self.correlation_id
        if self.causation_id:
            payload["causation_id"] = self.causation_id

        return payload

    @classmethod
    def perception(
        cls,
        *,
        source: EventSource,
        payload: dict[str, Any],
        **kwargs: Any,
    ) -> "AgentEvent":
        return cls(type=EventType.PERCEPTION, source=source, payload=payload, **kwargs)

    @classmethod
    def semantic_message(
        cls,
        *,
        source: EventSource,
        message: Message,
        payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> "AgentEvent":
        return cls(
            type=EventType.MESSAGE,
            source=source,
            message=message,
            payload=payload or {},
            **kwargs,
        )

    def __str__(self) -> str:
        return f"[{self.type.value}:{self.source.value}] {self.message or self.payload}"
