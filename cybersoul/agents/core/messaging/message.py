"""Core message contracts shared across the agent stack."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _message_id() -> str:
    return f"msg_{uuid4().hex}"


class MessageRole(str, Enum):
    """Protocol-level roles used by the semantic message layer."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class MessageBlockType(str, Enum):
    """Supported content block types for future multimodal expansion."""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    JSON = "json"


class MessageBlock(BaseModel):
    """A structured content block inside a message."""

    model_config = ConfigDict(use_enum_values=False)

    type: MessageBlockType
    text: Optional[str] = None
    uri: Optional[str] = None
    mime_type: Optional[str] = None
    data: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_payload(self) -> "MessageBlock":
        if self.type is MessageBlockType.TEXT and not self.text:
            raise ValueError("text block requires a non-empty text field")

        if self.type in {
            MessageBlockType.IMAGE,
            MessageBlockType.AUDIO,
            MessageBlockType.VIDEO,
        } and not self.uri and self.data is None:
            raise ValueError(
                f"{self.type.value} block requires either uri or data"
            )

        if self.type is MessageBlockType.JSON and self.data is None:
            raise ValueError("json block requires a data field")

        return self

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": self.type.value}

        if self.text is not None:
            payload["text"] = self.text
        if self.uri is not None:
            payload["uri"] = self.uri
        if self.mime_type is not None:
            payload["mime_type"] = self.mime_type
        if self.data is not None:
            payload["data"] = self.data
        if self.metadata:
            payload["metadata"] = self.metadata

        return payload


class Message(BaseModel):
    """Canonical semantic message object used by agents, modes, and LLM clients."""

    model_config = ConfigDict(use_enum_values=False)

    id: str = Field(default_factory=_message_id)
    role: MessageRole
    content: str = ""
    blocks: list[MessageBlock] = Field(default_factory=list)
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)

    @model_validator(mode="after")
    def normalize_content(self) -> "Message":
        if not self.content and not self.blocks and not self.tool_calls:
            raise ValueError("message requires content or blocks")

        if self.content and not self.blocks:
            self.blocks = [MessageBlock(type=MessageBlockType.TEXT, text=self.content)]

        if self.blocks and not self.content:
            self.content = self._build_text_fallback(self.blocks)

        return self

    @property
    def text_content(self) -> str:
        parts = [
            block.text.strip()
            for block in self.blocks
            if block.type is MessageBlockType.TEXT and block.text
        ]
        return "\n\n".join(part for part in parts if part)

    @property
    def is_multimodal(self) -> bool:
        if not self.blocks:
            return False
        if len(self.blocks) > 1:
            return True
        return self.blocks[0].type is not MessageBlockType.TEXT

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": self.role.value}

        if self.is_multimodal:
            payload["content"] = [block.to_payload() for block in self.blocks]
        else:
            payload["content"] = self.content

        if self.name:
            payload["name"] = self.name
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            payload["tool_calls"] = self.tool_calls
        if self.metadata:
            payload["metadata"] = self.metadata

        return payload

    @classmethod
    def from_text(
        cls,
        role: MessageRole,
        content: str,
        **kwargs: Any,
    ) -> "Message":
        return cls(role=role, content=content, **kwargs)

    @staticmethod
    def _build_text_fallback(blocks: list[MessageBlock]) -> str:
        text_parts = [
            block.text.strip()
            for block in blocks
            if block.type is MessageBlockType.TEXT and block.text
        ]
        if text_parts:
            return "\n\n".join(part for part in text_parts if part)

        labels: list[str] = []
        for block in blocks:
            if block.type is MessageBlockType.IMAGE:
                labels.append("[image]")
            elif block.type is MessageBlockType.AUDIO:
                labels.append("[audio]")
            elif block.type is MessageBlockType.VIDEO:
                labels.append("[video]")
            elif block.type is MessageBlockType.JSON:
                labels.append("[json]")
            else:
                labels.append(f"[{block.type.value}]")

        return " ".join(labels)

    def __str__(self) -> str:
        return f"[{self.role.value}] {self.content}"
