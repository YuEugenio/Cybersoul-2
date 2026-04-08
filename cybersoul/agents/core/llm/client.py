"""Async OpenAI-compatible LLM client used by the current project."""

from __future__ import annotations

import base64
import json
import time
from typing import Any, AsyncIterator, Optional

from openai import AsyncOpenAI

from agents.core.llm.config import LLMConfig
from agents.core.llm.schemas import (
    LLMChunk,
    LLMRequest,
    LLMResponse,
    LLMToolCall,
    LLMToolSpec,
    LLMUsage,
)
from agents.core.messaging.message import Message, MessageBlock, MessageBlockType, MessageRole


class OpenAICompatibleLLMClient:
    """Thin adapter around the Chat Completions API."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        payload = self._build_request_payload(request, stream=False)
        started_at = time.perf_counter()
        response = await self._client.chat.completions.create(**payload)
        parsed = self._parse_response(response)
        parsed.metadata.setdefault(
            "latency_ms",
            round((time.perf_counter() - started_at) * 1000, 2),
        )
        return parsed

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]:
        payload = self._build_request_payload(request, stream=True)
        response = await self._client.chat.completions.create(**payload)

        tool_buffers: dict[int, dict[str, str]] = {}

        async for chunk in response:
            parsed_chunk = self._parse_stream_chunk(chunk, tool_buffers)
            if parsed_chunk is not None:
                yield parsed_chunk

    def _build_request_payload(
        self,
        request: LLMRequest,
        *,
        stream: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": [self._serialize_message(message) for message in request.messages],
            "stream": stream,
        }

        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = self._serialize_tools(request.tools)
            payload["tool_choice"] = "auto"

        return payload

    def _serialize_message(self, message: Message) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": message.role.value}

        if message.name:
            payload["name"] = message.name
        if message.role is MessageRole.TOOL and message.tool_call_id:
            payload["tool_call_id"] = message.tool_call_id
        if message.role is MessageRole.ASSISTANT and message.tool_calls:
            payload["tool_calls"] = message.tool_calls
            payload["content"] = message.content or ""
            return payload

        if message.is_multimodal and message.role is not MessageRole.TOOL:
            content = self._serialize_multimodal_content(message)
            payload["content"] = content if content is not None else message.content
            return payload

        payload["content"] = message.content
        return payload

    def _serialize_multimodal_content(
        self,
        message: Message,
    ) -> Optional[list[dict[str, Any]]]:
        parts: list[dict[str, Any]] = []

        for block in message.blocks:
            part = self._serialize_block(block)
            if part is None:
                return None
            parts.append(part)

        return parts or None

    def _serialize_block(self, block: MessageBlock) -> Optional[dict[str, Any]]:
        if block.type is MessageBlockType.TEXT:
            return {"type": "text", "text": block.text}

        if block.type is MessageBlockType.IMAGE:
            image_url = block.uri or self._build_data_uri(block)
            if image_url is None:
                return None
            return {"type": "image_url", "image_url": {"url": image_url}}

        return None

    def _build_data_uri(self, block: MessageBlock) -> Optional[str]:
        if block.data is None or not block.mime_type:
            return None

        if isinstance(block.data, bytes):
            encoded = base64.b64encode(block.data).decode("utf-8")
            return f"data:{block.mime_type};base64,{encoded}"

        if isinstance(block.data, str):
            return f"data:{block.mime_type};base64,{block.data}"

        return None

    def _serialize_tools(self, tools: list[LLMToolSpec]) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []

        for tool in tools:
            parameters = tool.parameters_schema or {"type": "object", "properties": {}}
            serialized.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": parameters,
                    },
                }
            )

        return serialized

    def _parse_response(self, response: Any) -> LLMResponse:
        choices = getattr(response, "choices", None) or []
        first_choice = choices[0] if choices else None
        raw_message = getattr(first_choice, "message", None) if first_choice else None

        metadata: dict[str, Any] = {}
        response_id = getattr(response, "id", None)
        if response_id:
            metadata["response_id"] = response_id

        return LLMResponse(
            message=self._to_assistant_message(raw_message),
            tool_calls=self._to_tool_calls(getattr(raw_message, "tool_calls", None)),
            usage=self._to_usage(getattr(response, "usage", None)),
            finish_reason=getattr(first_choice, "finish_reason", None),
            model=getattr(response, "model", None),
            metadata=metadata,
        )

    def _parse_stream_chunk(
        self,
        chunk: Any,
        tool_buffers: dict[int, dict[str, str]],
    ) -> Optional[LLMChunk]:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            return None

        first_choice = choices[0]
        delta = getattr(first_choice, "delta", None)
        delta_text = self._extract_text_content(getattr(delta, "content", None)) or ""

        if delta is not None:
            for raw_tool_call in getattr(delta, "tool_calls", None) or []:
                index = getattr(raw_tool_call, "index", 0)
                buffer = tool_buffers.setdefault(
                    index,
                    {"id": "", "name": "", "arguments": ""},
                )

                tool_call_id = getattr(raw_tool_call, "id", None)
                if tool_call_id:
                    buffer["id"] = tool_call_id

                function = getattr(raw_tool_call, "function", None)
                if function is None:
                    continue

                function_name = getattr(function, "name", None)
                if function_name:
                    buffer["name"] = function_name

                arguments_part = getattr(function, "arguments", None)
                if arguments_part:
                    buffer["arguments"] += arguments_part

        finish_reason = getattr(first_choice, "finish_reason", None)
        tool_call_deltas: list[LLMToolCall] = []

        if finish_reason is not None and tool_buffers:
            for index in sorted(tool_buffers):
                buffer = tool_buffers[index]
                if buffer["id"] and buffer["name"]:
                    tool_call_deltas.append(
                        LLMToolCall(
                            id=buffer["id"],
                            name=buffer["name"],
                            arguments=self._parse_tool_arguments(buffer["arguments"]),
                        )
                    )
            tool_buffers.clear()

        if not delta_text and not tool_call_deltas and finish_reason is None:
            return None

        metadata: dict[str, Any] = {}
        chunk_id = getattr(chunk, "id", None)
        if chunk_id:
            metadata["chunk_id"] = chunk_id

        return LLMChunk(
            delta_text=delta_text,
            tool_call_deltas=tool_call_deltas,
            finish_reason=finish_reason,
            metadata=metadata,
        )

    def _to_assistant_message(self, raw_message: Any) -> Optional[Message]:
        if raw_message is None:
            return None

        content = self._extract_text_content(getattr(raw_message, "content", None))
        if not content:
            return None

        return Message(
            role=MessageRole.ASSISTANT,
            content=content,
            name=getattr(raw_message, "name", None),
        )

    def _to_tool_calls(self, raw_tool_calls: Any) -> list[LLMToolCall]:
        if not raw_tool_calls:
            return []

        tool_calls: list[LLMToolCall] = []

        for raw_tool_call in raw_tool_calls:
            function = getattr(raw_tool_call, "function", None)
            name = getattr(function, "name", None)
            tool_call_id = getattr(raw_tool_call, "id", None)

            if not tool_call_id or not name:
                continue

            tool_calls.append(
                LLMToolCall(
                    id=tool_call_id,
                    name=name,
                    arguments=self._parse_tool_arguments(
                        getattr(function, "arguments", None)
                    ),
                )
            )

        return tool_calls

    def _to_usage(self, raw_usage: Any) -> Optional[LLMUsage]:
        if raw_usage is None:
            return None

        return LLMUsage(
            prompt_tokens=getattr(raw_usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(raw_usage, "completion_tokens", 0) or 0,
            total_tokens=getattr(raw_usage, "total_tokens", 0) or 0,
        )

    def _parse_tool_arguments(self, raw_arguments: Any) -> dict[str, Any]:
        if raw_arguments is None:
            return {}

        if isinstance(raw_arguments, dict):
            return raw_arguments

        if not isinstance(raw_arguments, str):
            return {"value": raw_arguments}

        stripped = raw_arguments.strip()
        if not stripped:
            return {}

        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return {"_raw": raw_arguments}

        if isinstance(parsed, dict):
            return parsed

        return {"value": parsed}

    def _extract_text_content(self, content: Any) -> Optional[str]:
        if content is None:
            return None

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                text = self._extract_text_part(item)
                if text:
                    parts.append(text)
            joined = "".join(parts)
            return joined or None

        return str(content)

    def _extract_text_part(self, item: Any) -> Optional[str]:
        if isinstance(item, str):
            return item

        if isinstance(item, dict):
            if item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    return text
                if isinstance(text, dict):
                    value = text.get("value")
                    if isinstance(value, str):
                        return value
            return None

        item_type = getattr(item, "type", None)
        if item_type != "text":
            return None

        text = getattr(item, "text", None)
        if isinstance(text, str):
            return text

        value = getattr(text, "value", None)
        if isinstance(value, str):
            return value

        return None
