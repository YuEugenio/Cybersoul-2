"""Minimal manager around the world clock and world state."""

from __future__ import annotations

from datetime import datetime

from world.core.clock import WorldClock
from world.core.state import ActorState, WorldState


class WorldManager:
    """Own the minimal world clock and durable world state."""

    def __init__(
        self,
        clock: WorldClock | None = None,
        initial_state: WorldState | None = None,
    ) -> None:
        self.clock = clock or WorldClock()
        self._state = initial_state or WorldState(current_time=self.clock.now())

    @property
    def state(self) -> WorldState:
        return self._state

    def now(self) -> datetime:
        """Refresh and return the current world time."""

        self._state.current_time = self.clock.now()
        return self._state.current_time

    def set_current_time(self, current_time: datetime) -> datetime:
        """Override the current world time with a normalized aware datetime."""

        self._state.current_time = self.clock.ensure_aware(current_time)
        return self._state.current_time

    def get_actor_state(self, actor_id: str) -> ActorState | None:
        return self._state.get_actor_state(actor_id)

    def set_actor_state(self, actor_state: ActorState) -> ActorState:
        return self._state.upsert_actor_state(actor_state)

    def snapshot(self) -> WorldState:
        """Return a detached snapshot of the current world state."""

        self.now()
        return self._state.model_copy(deep=True)
