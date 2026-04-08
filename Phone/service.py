"""Application service for the Phone chat subsystem."""

from __future__ import annotations

from typing import Dict, List, Optional

from Phone.models import ChatMessage, ChatThread
from Phone.store import PhoneStore


class PhoneChatService:
    """Core direct-chat use cases for the MVP phone experience."""

    def __init__(self, store: Optional[PhoneStore] = None):
        self.store = store or PhoneStore()

    def get_or_create_thread(
        self,
        companion_id: str,
        user_id: str,
        title: Optional[str] = None,
    ) -> ChatThread:
        thread = self.store.find_direct_thread(
            companion_id=companion_id,
            user_id=user_id,
        )
        if thread is not None:
            return thread

        thread = ChatThread.create(
            companion_id=companion_id,
            user_id=user_id,
            title=title,
        )
        self.store.save_thread(thread)
        return thread

    def get_thread(self, thread_id: str) -> Optional[ChatThread]:
        return self.store.get_thread(thread_id)

    def list_messages(
        self,
        thread_id: str,
        limit: Optional[int] = None,
    ) -> List[ChatMessage]:
        return self.store.list_messages(thread_id=thread_id, limit=limit)

    def send_message(
        self,
        thread_id: str,
        sender: str,
        content: str,
    ) -> ChatMessage:
        thread = self.store.get_thread(thread_id)
        if thread is None:
            raise ValueError("chat thread not found")

        normalized_sender = sender.strip().lower()
        if normalized_sender not in ("user", "companion"):
            raise ValueError("sender must be 'user' or 'companion'")

        message = ChatMessage.create(
            thread_id=thread_id,
            sender=normalized_sender,
            content=content,
        )
        self.store.append_message(message)
        thread.touch()
        self.store.save_thread(thread)
        return message

    def send_user_message(self, thread_id: str, content: str) -> ChatMessage:
        return self.send_message(thread_id=thread_id, sender="user", content=content)

    def send_companion_message(self, thread_id: str, content: str) -> ChatMessage:
        return self.send_message(
            thread_id=thread_id,
            sender="companion",
            content=content,
        )

    def get_transcript(
        self,
        thread_id: str,
        limit: Optional[int] = None,
    ) -> str:
        lines = []
        for message in self.list_messages(thread_id=thread_id, limit=limit):
            prefix = "用户" if message.sender == "user" else "昔涟"
            lines.append(prefix + ": " + message.content)
        return "\n".join(lines)

    def thread_payload(
        self,
        thread_id: str,
        limit: Optional[int] = None,
    ) -> Dict[str, object]:
        thread = self.get_thread(thread_id)
        if thread is None:
            raise ValueError("chat thread not found")

        messages = self.list_messages(thread_id=thread_id, limit=limit)
        return {
            "thread": thread.to_dict(),
            "messages": [message.to_dict() for message in messages],
            "transcript": self.get_transcript(thread_id=thread_id, limit=limit),
        }
