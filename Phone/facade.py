"""High-level facade for the Phone chat subsystem."""

from __future__ import annotations

from typing import Dict, Optional

from Phone.models import ChatMessage, ChatThread
from Phone.service import PhoneChatService
from Phone.store import PhoneStore


class PhoneFacade:
    """A compact facade used by runtime code or tools."""

    def __init__(self, service: Optional[PhoneChatService] = None):
        self.service = service or PhoneChatService()

    @classmethod
    def from_store_path(cls, file_path: str) -> "PhoneFacade":
        return cls(service=PhoneChatService(store=PhoneStore(file_path=file_path)))

    def open_chat(
        self,
        companion_id: str = "cyrene",
        user_id: str = "user",
        title: Optional[str] = None,
    ) -> ChatThread:
        return self.service.get_or_create_thread(
            companion_id=companion_id,
            user_id=user_id,
            title=title,
        )

    def send_from_user(self, thread_id: str, content: str) -> ChatMessage:
        return self.service.send_user_message(thread_id=thread_id, content=content)

    def send_from_companion(self, thread_id: str, content: str) -> ChatMessage:
        return self.service.send_companion_message(thread_id=thread_id, content=content)

    def list_message_models(
        self,
        thread_id: str,
        limit: Optional[int] = None,
    ) -> list[ChatMessage]:
        return self.service.list_messages(thread_id=thread_id, limit=limit)

    def read_messages(
        self,
        thread_id: str,
        limit: Optional[int] = None,
    ) -> Dict[str, object]:
        return self.service.thread_payload(thread_id=thread_id, limit=limit)
