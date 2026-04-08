"""Domain models for the Phone chat subsystem."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)


@dataclass
class ChatThread:
    """A single direct chat thread between the user and a companion."""

    thread_id: str
    companion_id: str
    user_id: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        companion_id: str,
        user_id: str,
        title: Optional[str] = None,
    ) -> "ChatThread":
        now = utc_now()
        return cls(
            thread_id=str(uuid4()),
            companion_id=companion_id,
            user_id=user_id,
            title=title or companion_id,
            status="active",
            created_at=now,
            updated_at=now,
        )

    def touch(self) -> None:
        self.updated_at = utc_now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "companion_id": self.companion_id,
            "user_id": self.user_id,
            "title": self.title,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ChatThread":
        return cls(
            thread_id=payload["thread_id"],
            companion_id=payload["companion_id"],
            user_id=payload["user_id"],
            title=payload["title"],
            status=payload["status"],
            created_at=datetime.fromisoformat(payload["created_at"]),
            updated_at=datetime.fromisoformat(payload["updated_at"]),
        )


@dataclass
class ChatMessage:
    """A single chat message inside a direct chat thread."""

    message_id: str
    thread_id: str
    sender: str
    content: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        thread_id: str,
        sender: str,
        content: str,
    ) -> "ChatMessage":
        return cls(
            message_id=str(uuid4()),
            thread_id=thread_id,
            sender=sender,
            content=content,
            created_at=utc_now(),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "sender": self.sender,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ChatMessage":
        return cls(
            message_id=payload["message_id"],
            thread_id=payload["thread_id"],
            sender=payload["sender"],
            content=payload["content"],
            created_at=datetime.fromisoformat(payload["created_at"]),
        )
