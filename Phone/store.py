"""Persistent storage for the Phone chat subsystem."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from Phone.models import ChatMessage, ChatThread


class PhoneStore:
    """A tiny JSON-backed store for chat threads and messages."""

    def __init__(self, file_path: Optional[str] = None):
        default_path = Path(__file__).resolve().parent / "data" / "phone_store.json"
        self.file_path = Path(file_path) if file_path is not None else default_path
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._threads: Dict[str, ChatThread] = {}
        self._messages: Dict[str, List[ChatMessage]] = {}
        self._load()

    def _load(self) -> None:
        if not self.file_path.exists():
            self._persist()
            return

        payload = json.loads(self.file_path.read_text(encoding="utf-8"))
        threads = payload.get("threads", {})
        messages = payload.get("messages", {})

        self._threads = {
            thread_id: ChatThread.from_dict(thread_payload)
            for thread_id, thread_payload in threads.items()
        }
        self._messages = {
            thread_id: [ChatMessage.from_dict(message) for message in thread_messages]
            for thread_id, thread_messages in messages.items()
        }

    def _persist(self) -> None:
        payload = {
            "threads": {
                thread_id: thread.to_dict()
                for thread_id, thread in self._threads.items()
            },
            "messages": {
                thread_id: [message.to_dict() for message in messages]
                for thread_id, messages in self._messages.items()
            },
        }
        self.file_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save_thread(self, thread: ChatThread) -> None:
        self._threads[thread.thread_id] = thread
        self._messages.setdefault(thread.thread_id, [])
        self._persist()

    def get_thread(self, thread_id: str) -> Optional[ChatThread]:
        return self._threads.get(thread_id)

    def find_direct_thread(
        self,
        companion_id: str,
        user_id: str,
    ) -> Optional[ChatThread]:
        for thread in self._threads.values():
            if thread.companion_id == companion_id and thread.user_id == user_id:
                return thread
        return None

    def append_message(self, message: ChatMessage) -> None:
        self._messages.setdefault(message.thread_id, []).append(message)
        self._persist()

    def list_messages(
        self,
        thread_id: str,
        limit: Optional[int] = None,
    ) -> List[ChatMessage]:
        messages = list(self._messages.get(thread_id, []))
        if limit is None:
            return messages
        return messages[-limit:]
