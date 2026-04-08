"""Minimal ReAct mode adapted to the current Cybersoul core contracts."""

from __future__ import annotations

import time
from typing import Any

from agents.core.base.mode import BaseMode
from agents.core.llm.schemas import LLMRequest, LLMResponse, LLMToolCall
from agents.core.messaging.event import AgentEvent
from agents.core.messaging.message import Message, MessageRole
from agents.core.messaging.mode_result import FinishReason, ModeResult
from agents.tools.registry.registry import ToolRegistry


class ReActMode(BaseMode):
    """A minimal tool-using reasoning loop built on top of BaseMode."""

    _NOOP_SENTINELS = {"NOOP", "[NOOP]", "<NOOP>"}

    def __init__(
        self,
        name: str,
        llm_client,
        tool_registry: ToolRegistry,
        system_prompt: str,
        max_steps: int = 5,
    ):
        super().__init__(name=name, llm_client=llm_client)
        self.tool_registry = tool_registry
        self.system_prompt = system_prompt
        self.max_steps = max_steps

    async def _run(
        self,
        event: AgentEvent,
        history: list[Message],
        **kwargs: Any,
    ) -> ModeResult:
        working_messages = self._build_working_messages(history=history, event=event)
        tool_trace: list[dict[str, Any]] = []
        react_trace: list[dict[str, Any]] = []

        for step_index in range(1, self.max_steps + 1):
            step_trace = {
                "step_index": step_index,
                "request": self._serialize_request_trace(working_messages),
            }
            started_at = time.perf_counter()
            response = await self._complete(
                LLMRequest(
                    messages=working_messages,
                    tools=self.tool_registry.to_llm_specs(),
                )
            )
            step_trace["response"] = self._serialize_response_trace(
                response,
                fallback_latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
            )

            if response.tool_calls:
                working_messages.append(self._build_tool_call_message(response.tool_calls))
                tool_messages, trace_entries = await self._execute_tool_calls(response.tool_calls)
                tool_trace.extend(trace_entries)
                working_messages.extend(tool_messages)
                step_trace["tool_results"] = trace_entries
                react_trace.append(step_trace)
                continue

            if response.message is not None:
                react_trace.append(step_trace)
                if response.message.content.strip() in self._NOOP_SENTINELS:
                    return ModeResult.noop(
                        summary="react mode chose noop",
                        metadata=self._response_metadata(
                            response,
                            tool_trace=tool_trace,
                            react_trace=react_trace,
                        ),
                    )
                return ModeResult(
                    finish_reason=FinishReason.COMPLETED,
                    messages=[response.message],
                    summary="react mode produced an assistant response",
                    metadata=self._response_metadata(
                        response,
                        tool_trace=tool_trace,
                        react_trace=react_trace,
                    ),
                )

            react_trace.append(step_trace)
            return ModeResult.noop(
                summary="react mode received no assistant message or tool call",
                metadata=self._response_metadata(
                    response,
                    tool_trace=tool_trace,
                    react_trace=react_trace,
                ),
            )

        return ModeResult.noop(
            summary="react mode reached max_steps without final assistant response",
            metadata={
                "max_steps": self.max_steps,
                "tool_trace": tool_trace,
                "react_trace": react_trace,
            },
        )

    def _build_tool_call_message(self, tool_calls: list[LLMToolCall]) -> Message:
        return Message(
            role=MessageRole.ASSISTANT,
            content="",
            tool_calls=[
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": self._serialize_tool_arguments(tool_call.arguments),
                    },
                }
                for tool_call in tool_calls
            ],
            metadata={"tool_call_count": len(tool_calls)},
        )

    def _build_working_messages(
        self,
        *,
        history: list[Message],
        event: AgentEvent,
    ) -> list[Message]:
        messages = history.copy()

        if (
            not messages
            or messages[0].role is not MessageRole.SYSTEM
            or messages[0].content != self.system_prompt
        ):
            messages.insert(
                0,
                Message(
                    role=MessageRole.SYSTEM,
                    content=self.system_prompt,
                    metadata={"system_prompt_kind": "base_system_prompt"},
                ),
            )

        if event.message is not None:
            messages.append(event.message)

        return messages

    async def _execute_tool_calls(
        self,
        tool_calls: list[LLMToolCall],
    ) -> tuple[list[Message], list[dict[str, Any]]]:
        tool_messages: list[Message] = []
        trace_entries: list[dict[str, Any]] = []

        for tool_call in tool_calls:
            result = await self.tool_registry.execute_tool(
                name=tool_call.name,
                arguments=tool_call.arguments,
            )
            tool_messages.append(
                Message(
                    role=MessageRole.TOOL,
                    content=result.content,
                    name=tool_call.name,
                    tool_call_id=tool_call.id,
                    metadata={
                        "data": result.data,
                        "tool_metadata": result.metadata,
                    },
                )
            )
            trace_entries.append(
                {
                    "tool_name": tool_call.name,
                    "arguments": dict(tool_call.arguments),
                    "content": result.content,
                    "data": dict(result.data),
                }
            )

        return tool_messages, trace_entries

    def _serialize_tool_arguments(self, arguments: dict[str, Any]) -> str:
        import json

        return json.dumps(arguments, ensure_ascii=False)

    def _response_metadata(
        self,
        response: LLMResponse,
        *,
        tool_trace: list[dict[str, Any]] | None = None,
        react_trace: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {}

        if response.finish_reason is not None:
            metadata["llm_finish_reason"] = response.finish_reason
        if response.model is not None:
            metadata["llm_model"] = response.model
        if response.usage is not None:
            metadata["llm_usage"] = response.usage.model_dump(mode="json")
        if response.metadata:
            metadata["llm_response"] = response.metadata
        if tool_trace:
            metadata["tool_trace"] = tool_trace
        if react_trace:
            metadata["react_trace"] = react_trace

        return metadata

    def _serialize_request_trace(
        self,
        messages: list[Message],
    ) -> dict[str, Any]:
        return {
            "message_count": len(messages),
            "messages": [
                self._serialize_message_trace(message)
                for message in messages
            ],
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters_schema": tool.parameters_schema,
                }
                for tool in self.tool_registry.to_llm_specs()
            ],
        }

    def _serialize_response_trace(
        self,
        response: LLMResponse,
        *,
        fallback_latency_ms: float,
    ) -> dict[str, Any]:
        latency_ms = None
        if response.metadata:
            latency_ms = response.metadata.get("latency_ms")
        if latency_ms is None:
            latency_ms = fallback_latency_ms

        return {
            "model": response.model,
            "finish_reason": response.finish_reason,
            "latency_ms": latency_ms,
            "usage": (
                response.usage.model_dump(mode="json")
                if response.usage is not None
                else None
            ),
            "assistant_message": (
                self._serialize_message_trace(response.message)
                if response.message is not None
                else None
            ),
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "name": tool_call.name,
                    "arguments": dict(tool_call.arguments),
                }
                for tool_call in response.tool_calls
            ],
            "provider_metadata": dict(response.metadata),
        }

    def _serialize_message_trace(
        self,
        message: Message,
    ) -> dict[str, Any]:
        return {
            "role": message.role.value,
            "name": message.name,
            "content": message.content,
            "tool_call_id": message.tool_call_id,
            "tool_calls": list(message.tool_calls),
        }
