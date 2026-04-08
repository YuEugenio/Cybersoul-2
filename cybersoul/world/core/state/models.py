"""Minimal world state models focused on durable runtime facts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ActivityBlock(BaseModel):
    """A semantically meaningful block of ongoing activity."""

    model_config = ConfigDict(str_strip_whitespace=True)

    activity_type: str = Field(min_length=1)
    started_at: datetime
    planned_until: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_timeline(self) -> "ActivityBlock":
        if self.planned_until is not None and self.planned_until < self.started_at:
            raise ValueError("planned_until must not be earlier than started_at")
        return self

    @property
    def is_open_ended(self) -> bool:
        return self.planned_until is None


class ActorState(BaseModel):
    """Minimal durable state for an actor inside the world."""

    model_config = ConfigDict(str_strip_whitespace=True)

    actor_id: str = Field(min_length=1)
    current_place_id: str = Field(min_length=1)
    current_activity_block: ActivityBlock | None = None


class WorldState(BaseModel):
    """World runtime state composed only of current time and actor facts."""

    current_time: datetime
    actor_states: dict[str, ActorState] = Field(default_factory=dict)

    def get_actor_state(self, actor_id: str) -> ActorState | None:
        return self.actor_states.get(actor_id)

    def upsert_actor_state(self, actor_state: ActorState) -> ActorState:
        self.actor_states[actor_state.actor_id] = actor_state
        return actor_state
