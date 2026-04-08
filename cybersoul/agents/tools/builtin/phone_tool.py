"""Tool bridge for the root-level Phone chat subsystem."""

from __future__ import annotations

from typing import Any, Dict

from agents.tools.base.tool import BaseTool, ToolResult


class PhoneChatTool(BaseTool):
    """Expose the Phone chat subsystem through the agents tool contract."""

    def __init__(
        self,
        phone_facade: Any,
        companion_id: str = "cyrene",
        user_id: str = "user",
        title: str = "昔涟",
    ):
        super().__init__(
            name="phone_chat",
            description=(
                "Use the phone to inspect or send messages in your one-to-one chat "
                "with the user. If thread_id is omitted, the tool operates on your "
                "default direct chat."
            ),
            parameters_schema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "open_chat",
                            "read_messages",
                            "send_companion_message",
                        ],
                    },
                    "thread_id": {"type": "string"},
                    "companion_id": {"type": "string"},
                    "user_id": {"type": "string"},
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1},
                },
                "required": ["action"],
            },
        )
        self.phone_facade = phone_facade
        self.companion_id = companion_id
        self.user_id = user_id
        self.title = title

    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        action = arguments.get("action")
        if action == "open_chat":
            thread = self.phone_facade.open_chat(
                companion_id=arguments.get("companion_id", self.companion_id),
                user_id=arguments.get("user_id", self.user_id),
                title=arguments.get("title", self.title),
            )
            return ToolResult(
                content=(
                    "已定位手机主聊天线程。"
                    f" thread_id={thread.thread_id}; title={thread.title}。"
                    " 后续读取或发送消息时可以省略 thread_id。"
                ),
                data=thread.to_dict(),
            )

        if action == "read_messages":
            thread = self._resolve_thread(arguments)
            payload = self.phone_facade.read_messages(
                thread_id=thread.thread_id,
                limit=arguments.get("limit"),
            )
            transcript = payload.get("transcript", "")
            return ToolResult(
                content=(
                    f"手机主聊天线程(thread_id={thread.thread_id}, title={thread.title})"
                    + (" 当前聊天记录为空。" if not transcript else " 的聊天记录如下:\n" + transcript)
                ),
                data=payload,
            )

        if action == "send_companion_message":
            thread = self._resolve_thread(arguments)
            message = self.phone_facade.send_from_companion(
                thread_id=thread.thread_id,
                content=self._require(arguments, "content"),
            )
            return ToolResult(
                content=(
                    "已通过手机向用户发送消息。"
                    f" thread_id={thread.thread_id}; content={message.content}"
                ),
                data=message.to_dict(),
            )

        raise ValueError("unsupported phone action")

    def _resolve_thread(self, arguments: Dict[str, Any]):
        thread_id = arguments.get("thread_id")
        if thread_id:
            thread = self.phone_facade.service.get_thread(str(thread_id))
            if thread is None:
                raise ValueError("chat thread not found")
            return thread

        return self.phone_facade.open_chat(
            companion_id=arguments.get("companion_id", self.companion_id),
            user_id=arguments.get("user_id", self.user_id),
            title=arguments.get("title", self.title),
        )

    def _require(self, arguments: Dict[str, Any], key: str) -> Any:
        value = arguments.get(key)
        if value is None or value == "":
            raise ValueError("missing required argument: " + key)
        return value
