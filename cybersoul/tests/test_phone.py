"""Tests for the root-level Phone chat subsystem."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, TestCase

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Phone.facade import PhoneFacade
from Phone.service import PhoneChatService
from Phone.store import PhoneStore
from agents.tools.builtin.phone_tool import PhoneChatTool


class PhoneChatServiceTests(TestCase):
    def test_service_creates_thread_and_persists_messages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "phone_store.json"
            facade = PhoneFacade.from_store_path(str(store_path))

            thread = facade.open_chat(companion_id="cyrene", user_id="user", title="昔涟")
            user_message = facade.send_from_user(thread.thread_id, "你在做什么？")
            companion_message = facade.send_from_companion(
                thread.thread_id,
                "我刚从长廊那边回来，风有点大。",
            )

            payload = facade.read_messages(thread.thread_id)

            self.assertEqual(thread.title, "昔涟")
            self.assertEqual(user_message.sender, "user")
            self.assertEqual(companion_message.sender, "companion")
            self.assertEqual(len(payload["messages"]), 2)
            self.assertIn("用户: 你在做什么？", payload["transcript"])
            self.assertIn("昔涟: 我刚从长廊那边回来，风有点大。", payload["transcript"])

            reloaded_service = PhoneChatService(store=PhoneStore(file_path=str(store_path)))
            reloaded_payload = reloaded_service.thread_payload(thread.thread_id)

            self.assertEqual(len(reloaded_payload["messages"]), 2)
            self.assertEqual(reloaded_payload["messages"][0]["content"], "你在做什么？")


class PhoneChatToolTests(IsolatedAsyncioTestCase):
    async def test_tool_reads_and_writes_chat_messages_without_explicit_thread_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / "tool_phone_store.json"
            facade = PhoneFacade.from_store_path(str(store_path))
            tool = PhoneChatTool(
                phone_facade=facade,
                companion_id="cyrene",
                user_id="user",
                title="昔涟",
            )

            open_result = await tool.execute({"action": "open_chat"})
            thread_id = open_result.data["thread_id"]

            facade.send_from_user(thread_id, "你睡了吗？")
            await tool.execute(
                {
                    "action": "send_companion_message",
                    "content": "还没呢，我在看夜里的灯。",
                }
            )
            read_result = await tool.execute(
                {
                    "action": "read_messages",
                    "limit": 10,
                }
            )

            self.assertIn(f"thread_id={thread_id}", open_result.content)
            self.assertIn("用户: 你睡了吗？", read_result.content)
            self.assertIn("昔涟: 还没呢，我在看夜里的灯。", read_result.content)
            self.assertEqual(len(read_result.data["messages"]), 2)
