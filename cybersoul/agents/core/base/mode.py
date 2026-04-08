"""Base abstractions for agent reasoning modes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from agents.core.llm.client import OpenAICompatibleLLMClient
from agents.core.llm.schemas import LLMChunk, LLMRequest, LLMResponse
from agents.core.messaging.event import AgentEvent
from agents.core.messaging.message import Message
from agents.core.messaging.mode_result import ModeResult


class BaseMode(ABC):
    """Minimal async template shared by all reasoning modes."""

    def __init__(
        self,
        name: str,
        llm_client: OpenAICompatibleLLMClient,
    ):
        self.name = name
        self.llm_client = llm_client

    async def run(
        self,
        event: AgentEvent,
        history: list[Message],
        **kwargs: Any,
    ) -> ModeResult:
        return await self._run(event=event, history=history, **kwargs)

    @abstractmethod
    async def _run(
        self,
        event: AgentEvent,
        history: list[Message],
        **kwargs: Any,
    ) -> ModeResult:
        """Execute the concrete reasoning logic of the mode."""

    async def _complete(self, request: LLMRequest) -> LLMResponse:
        return await self.llm_client.complete(request)

    async def _stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        async for chunk in self.llm_client.stream(request):
            yield chunk
