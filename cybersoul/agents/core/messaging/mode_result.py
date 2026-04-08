"""Structured outputs produced by modes and consumed by runtime."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from agents.core.messaging.message import Message


class FinishReason(str, Enum):
    """Why a mode finished its current execution."""

    COMPLETED = "completed"
    NOOP = "noop"
    WAITING = "waiting"
    INTERRUPTED = "interrupted"
    HANDOFF = "handoff"
    ERROR = "error"


class ModeEffectType(str, Enum):
    """High-level side effects requested by a mode."""

    PATCH_STATE = "patch_state"
    EMIT_EVENT = "emit_event"
    EXECUTE_COMMAND = "execute_command"
    WRITE_MEMORY = "write_memory"
    SCHEDULE = "schedule"
    TRACE = "trace"


class ModeEffect(BaseModel):
    """A runtime effect emitted by a mode."""

    model_config = ConfigDict(use_enum_values=False)

    type: ModeEffectType
    target: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModeResult(BaseModel):
    """Canonical output returned by a mode."""

    model_config = ConfigDict(use_enum_values=False)

    finish_reason: FinishReason = FinishReason.COMPLETED
    messages: list[Message] = Field(default_factory=list)
    effects: list[ModeEffect] = Field(default_factory=list)
    summary: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def has_messages(self) -> bool:
        return bool(self.messages)

    @property
    def has_effects(self) -> bool:
        return bool(self.effects)

    @property
    def is_noop(self) -> bool:
        return (
            self.finish_reason is FinishReason.NOOP
            and not self.messages
            and not self.effects
        )

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "finish_reason": self.finish_reason.value,
            "messages": [message.model_dump(mode="json") for message in self.messages],
            "effects": [effect.model_dump(mode="json") for effect in self.effects],
        }

        if self.summary is not None:
            payload["summary"] = self.summary
        if self.metadata:
            payload["metadata"] = self.metadata

        return payload

    @classmethod
    def noop(cls, summary: Optional[str] = None, **kwargs: Any) -> "ModeResult":
        return cls(finish_reason=FinishReason.NOOP, summary=summary, **kwargs)

    @classmethod
    def waiting(cls, summary: Optional[str] = None, **kwargs: Any) -> "ModeResult":
        return cls(finish_reason=FinishReason.WAITING, summary=summary, **kwargs)
