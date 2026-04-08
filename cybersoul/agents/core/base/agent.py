"""Base agent shell that owns history and delegates reasoning to modes."""

from __future__ import annotations

from typing import Any, Optional

from agents.core.base.mode import BaseMode
from agents.core.messaging.event import AgentEvent
from agents.core.messaging.message import Message
from agents.core.messaging.mode_result import ModeResult


class BaseAgent:
    """Minimal agent shell shared by concrete companion-style agents."""

    def __init__(
        self,
        name: str,
        default_mode: Optional[BaseMode] = None,
    ):
        self.name = name
        self.default_mode = default_mode
        self._history: list[Message] = []

    async def handle_event(
        self,
        event: AgentEvent,
        mode: Optional[BaseMode] = None,
        **kwargs: Any,
    ) -> ModeResult:
        selected_mode = mode or self.default_mode
        if selected_mode is None:
            raise ValueError("no mode provided and no default_mode configured")

        return await selected_mode.run(
            event=event,
            history=self.get_history(),
            **kwargs,
        )

    def set_default_mode(self, mode: BaseMode) -> None:
        self.default_mode = mode

    def add_message(self, message: Message) -> None:
        self._history.append(message)

    def add_messages(self, messages: list[Message]) -> None:
        self._history.extend(messages)

    def get_history(self) -> list[Message]:
        return self._history.copy()

    def clear_history(self) -> None:
        self._history.clear()
