"""Runtime event contracts shared across the agent stack."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agents.core.messaging.message import Message


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _event_id() -> str:
    return f"evt_{uuid4().hex}"


class EventType(str, Enum):
    """High-level runtime event types."""

    PERCEPTION = "perception"
    MESSAGE = "message"
    TIMER = "timer"
    STATE = "state"
    COMMAND = "command"
    TOOL_RESULT = "tool_result"
    SYSTEM = "system"


class EventSource(str, Enum):
    """Where an event originates from."""

    GUI_AGENT = "gui_agent"
    WORLD = "world"
    SCHEDULER = "scheduler"
    TOOL = "tool"
    RUNTIME = "runtime"
    SYSTEM = "system"
    API = "api"


class EventPriority(int, Enum):
    """Coarse runtime priority for scheduling and interruption."""

    LOW = 10
    NORMAL = 50
    HIGH = 80
    CRITICAL = 100


class AgentEvent(BaseModel):
    """Canonical runtime event object."""

    model_config = ConfigDict(use_enum_values=False)

    id: str = Field(default_factory=_event_id)
    type: EventType
    source: EventSource
    message: Optional[Message] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    priority: EventPriority = EventPriority.NORMAL
    occurred_at: datetime = Field(default_factory=_utc_now)
    created_at: datetime = Field(default_factory=_utc_now)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "type": self.type.value,
            "source": self.source.value,
            "payload": self.payload,
            "metadata": self.metadata,
            "priority": self.priority.value,
            "occurred_at": self.occurred_at.isoformat(),
            "created_at": self.created_at.isoformat(),
        }

        if self.message is not None:
            payload["message"] = self.message.model_dump(mode="json")
        if self.correlation_id is not None:
            payload["correlation_id"] = self.correlation_id
        if self.causation_id is not None:
            payload["causation_id"] = self.causation_id

        return payload

    @classmethod
    def perception(
        cls,
        *,
        source: EventSource = EventSource.GUI_AGENT,
        payload: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        priority: EventPriority = EventPriority.NORMAL,
        occurred_at: Optional[datetime] = None,
    ) -> "AgentEvent":
        return cls(
            type=EventType.PERCEPTION,
            source=source,
            payload=payload or {},
            metadata=metadata or {},
            correlation_id=correlation_id,
            causation_id=causation_id,
            priority=priority,
            occurred_at=occurred_at or _utc_now(),
        )

    @classmethod
    def semantic_message(
        cls,
        *,
        message: Message,
        source: EventSource = EventSource.RUNTIME,
        payload: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
        priority: EventPriority = EventPriority.NORMAL,
        occurred_at: Optional[datetime] = None,
    ) -> "AgentEvent":
        return cls(
            type=EventType.MESSAGE,
            source=source,
            message=message,
            payload=payload or {},
            metadata=metadata or {},
            correlation_id=correlation_id,
            causation_id=causation_id,
            priority=priority,
            occurred_at=occurred_at or _utc_now(),
        )

    @property
    def is_semantic(self) -> bool:
        return self.message is not None
