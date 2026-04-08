"""Tests for the current agents/core building blocks."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock

from agents.core.base.agent import BaseAgent
from agents.core.base.mode import BaseMode
from agents.core.llm.client import OpenAICompatibleLLMClient
from agents.core.llm.config import LLMConfig
from agents.core.llm.schemas import LLMRequest, LLMResponse, LLMUsage
from agents.core.messaging.event import AgentEvent, EventSource, EventType
from agents.core.messaging.message import (
    Message,
    MessageBlock,
    MessageBlockType,
    MessageRole,
)
from agents.core.messaging.mode_result import (
    FinishReason,
    ModeEffect,
    ModeEffectType,
    ModeResult,
)
from agents.modes.plan_solve.plan_solve_mode import PlanSolveMode
from agents.modes.react.react_mode import ReActMode
from agents.modes.reflection.reflection_mode import ReflectionMode
from agents.roles.companion.agent import CompanionAgent
from agents.roles.companion.profile import CompanionProfile
from agents.tools.base.tool import BaseTool, ToolResult
from agents.tools.registry.registry import ToolRegistry


class MessageAndEventTests(TestCase):
    def test_message_from_text_populates_text_block(self) -> None:
        message = Message(role=MessageRole.USER, content="你睡了吗？")

        self.assertEqual(message.content, "你睡了吗？")
        self.assertEqual(len(message.blocks), 1)
        self.assertEqual(message.blocks[0].type, MessageBlockType.TEXT)
        self.assertEqual(message.to_payload(), {"role": "user", "content": "你睡了吗？"})

    def test_multimodal_message_builds_text_fallback(self) -> None:
        message = Message(
            role=MessageRole.USER,
            blocks=[
                MessageBlock(type=MessageBlockType.TEXT, text="看一下这个"),
                MessageBlock(type=MessageBlockType.IMAGE, uri="https://example.com/image.jpg"),
            ],
        )

        self.assertTrue(message.is_multimodal)
        self.assertEqual(message.content, "看一下这个")
        self.assertEqual(
            message.to_payload(),
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "看一下这个"},
                    {"type": "image", "uri": "https://example.com/image.jpg"},
                ],
            },
        )

    def test_event_factories_keep_runtime_semantics(self) -> None:
        perception = AgentEvent.perception(
            payload={"channel": "wechat"},
            correlation_id="session_1",
        )
        message = Message(role=MessageRole.USER, content="你睡了吗？")
        semantic = AgentEvent.semantic_message(
            message=message,
            source=EventSource.RUNTIME,
            causation_id=perception.id,
            correlation_id="session_1",
        )

        self.assertEqual(perception.type, EventType.PERCEPTION)
        self.assertIsNone(perception.message)
        self.assertEqual(semantic.type, EventType.MESSAGE)
        self.assertEqual(semantic.message.content, "你睡了吗？")
        self.assertEqual(semantic.causation_id, perception.id)


class ModeResultTests(TestCase):
    def test_mode_result_serializes_messages_and_effects(self) -> None:
        result = ModeResult(
            finish_reason=FinishReason.COMPLETED,
            messages=[Message(role=MessageRole.ASSISTANT, content="还没呢，怎么啦？")],
            effects=[
                ModeEffect(
                    type=ModeEffectType.EXECUTE_COMMAND,
                    target="gui_agent",
                    payload={"action": "send_wechat_message"},
                )
            ],
            summary="reply to user",
        )

        payload = result.to_payload()

        self.assertEqual(payload["finish_reason"], "completed")
        self.assertEqual(payload["messages"][0]["content"], "还没呢，怎么啦？")
        self.assertEqual(payload["effects"][0]["type"], "execute_command")
        self.assertEqual(payload["summary"], "reply to user")

    def test_noop_helper_marks_empty_result(self) -> None:
        result = ModeResult.noop(summary="nothing to do")

        self.assertTrue(result.is_noop)
        self.assertEqual(result.finish_reason, FinishReason.NOOP)


class OpenAICompatibleClientTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.client = OpenAICompatibleLLMClient(
            LLMConfig(
                api_key="test-key",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                model="qwen3.5-flash-2026-02-23",
            )
        )

    async def test_complete_serializes_request_and_parses_response(self) -> None:
        response = SimpleNamespace(
            id="resp_1",
            model="qwen3.5-flash-2026-02-23",
            usage=SimpleNamespace(
                prompt_tokens=12,
                completion_tokens=8,
                total_tokens=20,
            ),
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(
                        content="还没呢，怎么啦？",
                        tool_calls=None,
                        name=None,
                    ),
                )
            ],
        )
        self.client._client.chat.completions.create = AsyncMock(return_value=response)

        request = LLMRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content="你是一个陪伴体。"),
                Message(role=MessageRole.USER, content="你睡了吗？"),
            ],
            temperature=0.7,
            max_tokens=128,
        )

        parsed = await self.client.complete(request)

        kwargs = self.client._client.chat.completions.create.await_args.kwargs
        self.assertEqual(kwargs["model"], "qwen3.5-flash-2026-02-23")
        self.assertFalse(kwargs["stream"])
        self.assertEqual(kwargs["messages"][1]["content"], "你睡了吗？")
        self.assertEqual(parsed.message.content, "还没呢，怎么啦？")
        self.assertEqual(parsed.usage.total_tokens, 20)
        self.assertEqual(parsed.finish_reason, "stop")

    async def test_stream_parses_incremental_text_chunks(self) -> None:
        async def fake_stream():
            yield SimpleNamespace(
                id="chunk_1",
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="还没", tool_calls=None),
                        finish_reason=None,
                    )
                ],
            )
            yield SimpleNamespace(
                id="chunk_2",
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content="呢。", tool_calls=None),
                        finish_reason="stop",
                    )
                ],
            )

        self.client._client.chat.completions.create = AsyncMock(return_value=fake_stream())

        request = LLMRequest(
            messages=[Message(role=MessageRole.USER, content="你睡了吗？")],
            stream=True,
        )

        chunks = []
        async for chunk in self.client.stream(request):
            chunks.append(chunk)

        kwargs = self.client._client.chat.completions.create.await_args.kwargs
        self.assertTrue(kwargs["stream"])
        self.assertEqual([chunk.delta_text for chunk in chunks], ["还没", "呢。"])
        self.assertEqual(chunks[-1].finish_reason, "stop")


class FakeLLMClient:
    def __init__(self, response: LLMResponse):
        self.response = response
        self.requests = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return self.response

    async def stream(self, request: LLMRequest):
        self.requests.append(request)
        if False:
            yield request


class FakeSequenceLLMClient:
    def __init__(self, responses: list[LLMResponse]):
        self.responses = responses
        self.requests = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return self.responses.pop(0)

    async def stream(self, request: LLMRequest):
        self.requests.append(request)
        if False:
            yield request


class EchoTool(BaseTool):
    def __init__(self) -> None:
        super().__init__(
            name="echo_tool",
            description="Echo user content back as tool context.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                },
                "required": ["text"],
            },
        )

    async def execute(self, arguments: dict[str, str]) -> ToolResult:
        return ToolResult(
            content="tool observation: " + arguments.get("text", ""),
            data={"echoed_text": arguments.get("text", "")},
        )


class ReplyMode(BaseMode):
    async def _run(self, event: AgentEvent, history: list[Message], **kwargs) -> ModeResult:
        request_messages = history.copy()
        if event.message is not None:
            request_messages.append(event.message)

        response = await self._complete(LLMRequest(messages=request_messages))

        return ModeResult(
            messages=[response.message] if response.message is not None else [],
            effects=[
                ModeEffect(
                    type=ModeEffectType.EXECUTE_COMMAND,
                    target="gui_agent",
                    payload={"action": "send_wechat_message"},
                )
            ],
            summary="reply generated",
        )


class FixedDraftMode(BaseMode):
    def __init__(self, name: str, result: ModeResult):
        super().__init__(name=name, llm_client=FakeLLMClient(LLMResponse()))
        self.result = result
        self.calls = 0

    async def _run(self, event: AgentEvent, history: list[Message], **kwargs) -> ModeResult:
        self.calls += 1
        return self.result


class AgentWorkflowTests(IsolatedAsyncioTestCase):
    async def test_agent_workflow_keeps_history_explicit(self) -> None:
        llm_response = LLMResponse(
            message=Message(role=MessageRole.ASSISTANT, content="还没呢，怎么啦？"),
            usage=LLMUsage(prompt_tokens=10, completion_tokens=8, total_tokens=18),
            finish_reason="stop",
            model="qwen3.5-flash-2026-02-23",
        )
        llm_client = FakeLLMClient(llm_response)
        mode = ReplyMode(name="reply_mode", llm_client=llm_client)
        agent = BaseAgent(name="main_companion", default_mode=mode)

        user_message = Message(role=MessageRole.USER, content="你睡了吗？")
        event = AgentEvent.semantic_message(message=user_message)

        result = await agent.handle_event(event)

        self.assertEqual(len(llm_client.requests), 1)
        self.assertEqual(llm_client.requests[0].messages[-1].content, "你睡了吗？")
        self.assertEqual(result.messages[0].content, "还没呢，怎么啦？")
        self.assertEqual(result.effects[0].type, ModeEffectType.EXECUTE_COMMAND)
        self.assertEqual(agent.get_history(), [])

        agent.add_message(user_message)
        agent.add_messages(result.messages)

        self.assertEqual(
            [message.content for message in agent.get_history()],
            ["你睡了吗？", "还没呢，怎么啦？"],
        )

    async def test_agent_requires_mode(self) -> None:
        agent = BaseAgent(name="main_companion")
        event = AgentEvent.perception(payload={"channel": "wechat"})

        with self.assertRaises(ValueError):
            await agent.handle_event(event)


class CompanionAgentTests(TestCase):
    def test_companion_profile_serializes_expected_fields(self) -> None:
        profile = CompanionProfile(
            id="nana_v1",
            companion_name="Nana",
            persona_path="agents/prompts/characters/nana/soul.md",
            default_mode="react",
            enabled_tools=["screen_capture", "wechat_send"],
            metadata={"locale": "zh-CN"},
        )

        self.assertEqual(
            profile.to_payload(),
            {
                "id": "nana_v1",
                "companion_name": "Nana",
                "persona_path": "agents/prompts/characters/nana/soul.md",
                "default_mode": "react",
                "enabled_tools": ["screen_capture", "wechat_send"],
                "metadata": {"locale": "zh-CN"},
            },
        )

    def test_companion_agent_exposes_profile_and_tools(self) -> None:
        registry = ToolRegistry()
        profile = CompanionProfile(
            id="nana_v1",
            companion_name="Nana",
            persona_path="agents/prompts/characters/nana/soul.md",
            default_mode="react",
        )
        agent = CompanionAgent(
            name="main_companion",
            profile=profile,
            tool_registry=registry,
        )

        agent.register_tool(EchoTool())

        self.assertEqual(agent.get_profile().companion_name, "Nana")
        self.assertEqual(agent.get_profile_payload()["default_mode"], "react")
        self.assertEqual([tool.name for tool in agent.list_tools()], ["echo_tool"])


class ReActModeTests(IsolatedAsyncioTestCase):
    async def test_react_mode_runs_tool_loop_then_returns_assistant_message(self) -> None:
        llm_client = FakeSequenceLLMClient(
            [
                LLMResponse(
                    tool_calls=[
                        {
                            "id": "call_1",
                            "name": "echo_tool",
                            "arguments": {"text": "你睡了吗？"},
                        }
                    ]
                ),
                LLMResponse(
                    message=Message(role=MessageRole.ASSISTANT, content="还没呢，怎么啦？"),
                    finish_reason="stop",
                    model="qwen3.5-flash-2026-02-23",
                ),
            ]
        )
        tool_registry = ToolRegistry()
        tool_registry.register(EchoTool())
        mode = ReActMode(
            name="react_mode",
            llm_client=llm_client,
            tool_registry=tool_registry,
            system_prompt="你是一个陪伴体。",
            max_steps=3,
        )

        result = await mode.run(
            event=AgentEvent.semantic_message(
                message=Message(role=MessageRole.USER, content="你睡了吗？")
            ),
            history=[],
        )

        self.assertEqual(len(llm_client.requests), 2)
        first_request = llm_client.requests[0]
        second_request = llm_client.requests[1]

        self.assertEqual(first_request.messages[0].role, MessageRole.SYSTEM)
        self.assertEqual(first_request.messages[-1].content, "你睡了吗？")
        self.assertEqual(second_request.messages[-2].role, MessageRole.ASSISTANT)
        self.assertEqual(second_request.messages[-2].tool_calls[0]["function"]["name"], "echo_tool")
        self.assertEqual(second_request.messages[-1].role, MessageRole.TOOL)
        self.assertEqual(second_request.messages[-1].content, "tool observation: 你睡了吗？")
        self.assertEqual(result.messages[0].content, "还没呢，怎么啦？")
        self.assertEqual(result.finish_reason, FinishReason.COMPLETED)
        self.assertEqual(result.metadata["tool_trace"][0]["tool_name"], "echo_tool")
        self.assertEqual(len(result.metadata["react_trace"]), 2)
        self.assertEqual(
            result.metadata["react_trace"][0]["request"]["tools"][0]["name"],
            "echo_tool",
        )
        self.assertEqual(
            result.metadata["react_trace"][0]["response"]["tool_calls"][0]["name"],
            "echo_tool",
        )
        self.assertEqual(
            result.metadata["react_trace"][1]["request"]["messages"][-1]["role"],
            "tool",
        )

    async def test_react_mode_treats_noop_sentinel_as_noop(self) -> None:
        llm_client = FakeLLMClient(
            LLMResponse(
                message=Message(role=MessageRole.ASSISTANT, content="NOOP"),
                finish_reason="stop",
            )
        )
        mode = ReActMode(
            name="react_mode",
            llm_client=llm_client,
            tool_registry=ToolRegistry(),
            system_prompt="你是一个陪伴体。",
            max_steps=3,
        )

        result = await mode.run(
            event=AgentEvent.semantic_message(
                message=Message(role=MessageRole.USER, content="这轮先不用说话。")
            ),
            history=[],
        )

        self.assertTrue(result.is_noop)
        self.assertEqual(result.summary, "react mode chose noop")

    async def test_react_mode_keeps_base_system_prompt_before_runtime_system_messages(self) -> None:
        llm_client = FakeLLMClient(
            LLMResponse(
                message=Message(role=MessageRole.ASSISTANT, content="我先看看现在的情况。"),
                finish_reason="stop",
            )
        )
        mode = ReActMode(
            name="react_mode",
            llm_client=llm_client,
            tool_registry=ToolRegistry(),
            system_prompt="你是一个陪伴体。",
            max_steps=2,
        )

        await mode.run(
            event=AgentEvent.semantic_message(
                message=Message(role=MessageRole.USER, content="现在方便说话吗？")
            ),
            history=[
                Message(
                    role=MessageRole.SYSTEM,
                    content="[State]\ncurrent_place_id: okhema",
                )
            ],
        )

        request = llm_client.requests[0]
        self.assertEqual(request.messages[0].content, "你是一个陪伴体。")
        self.assertEqual(
            request.messages[0].metadata["system_prompt_kind"],
            "base_system_prompt",
        )
        self.assertEqual(request.messages[1].content, "[State]\ncurrent_place_id: okhema")
        self.assertEqual(request.messages[-1].content, "现在方便说话吗？")

class PlanSolveModeTests(IsolatedAsyncioTestCase):
    async def test_plan_solve_mode_plans_then_executes_step_with_tools(self) -> None:
        llm_client = FakeSequenceLLMClient(
            [
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content='["读取当前聊天窗口内容", "生成最终回复"]',
                    ),
                    finish_reason="stop",
                    model="qwen3.5-flash-2026-02-23",
                ),
                LLMResponse(
                    tool_calls=[
                        {
                            "id": "call_1",
                            "name": "echo_tool",
                            "arguments": {"text": "用户最后一条消息：你睡了吗？"},
                        }
                    ]
                ),
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content="聊天窗口已读取，对方最后一条消息是：你睡了吗？",
                    ),
                    finish_reason="stop",
                    model="qwen3.5-flash-2026-02-23",
                ),
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content="还没呢，怎么啦？",
                    ),
                    finish_reason="stop",
                    model="qwen3.5-flash-2026-02-23",
                ),
            ]
        )
        tool_registry = ToolRegistry()
        tool_registry.register(EchoTool())
        mode = PlanSolveMode(
            name="plan_solve_mode",
            llm_client=llm_client,
            planner_prompt="你是一个擅长规划任务的陪伴体执行规划器。",
            executor_prompt="你是一个严格按步骤执行任务的陪伴体执行器。",
            tool_registry=tool_registry,
            max_plan_steps=4,
            max_step_rounds=3,
        )

        result = await mode.run(
            event=AgentEvent.semantic_message(
                message=Message(role=MessageRole.USER, content="看看微信里对方说了什么，然后帮我回一句")
            ),
            history=[],
        )

        self.assertEqual(len(llm_client.requests), 4)
        self.assertEqual(llm_client.requests[0].tools, [])
        self.assertEqual(llm_client.requests[1].tools[0].name, "echo_tool")
        self.assertEqual(llm_client.requests[2].messages[-1].role, MessageRole.TOOL)
        self.assertEqual(
            llm_client.requests[2].messages[-1].content,
            "tool observation: 用户最后一条消息：你睡了吗？",
        )
        self.assertEqual(result.finish_reason, FinishReason.COMPLETED)
        self.assertEqual(result.messages[0].content, "还没呢，怎么啦？")
        self.assertEqual(
            result.metadata["plan"],
            ["读取当前聊天窗口内容", "生成最终回复"],
        )
        self.assertEqual(len(result.metadata["step_results"]), 2)
        self.assertEqual(
            result.metadata["step_results"][0]["result"],
            "聊天窗口已读取，对方最后一条消息是：你睡了吗？",
        )

    async def test_plan_solve_mode_returns_error_when_plan_is_invalid(self) -> None:
        llm_client = FakeSequenceLLMClient(
            [
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content="第一步先看消息，第二步再回复。",
                    ),
                    finish_reason="stop",
                )
            ]
        )
        mode = PlanSolveMode(
            name="plan_solve_mode",
            llm_client=llm_client,
            planner_prompt="你是规划器。",
            executor_prompt="你是执行器。",
            tool_registry=ToolRegistry(),
        )

        result = await mode.run(
            event=AgentEvent.semantic_message(
                message=Message(role=MessageRole.USER, content="帮我处理这段对话")
            ),
            history=[],
        )

        self.assertEqual(result.finish_reason, FinishReason.ERROR)
        self.assertEqual(result.messages, [])
        self.assertEqual(result.metadata["failed_stage"], "planning")


class ReflectionModeTests(IsolatedAsyncioTestCase):
    async def test_reflection_mode_refines_base_mode_output(self) -> None:
        base_mode = FixedDraftMode(
            name="fixed_base_mode",
            result=ModeResult(
                finish_reason=FinishReason.COMPLETED,
                messages=[Message(role=MessageRole.ASSISTANT, content="还没呢，怎么啦？")],
                effects=[
                    ModeEffect(
                        type=ModeEffectType.EXECUTE_COMMAND,
                        target="gui_agent",
                        payload={"action": "send_wechat_message"},
                    )
                ],
                summary="base draft ready",
            ),
        )
        reflection_llm = FakeSequenceLLMClient(
            [
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content='{"should_refine": true, "feedback": "语气再温柔一些，并且更主动承接对方情绪。"}',
                    ),
                    finish_reason="stop",
                ),
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content="还没呢，你是不是也还没睡呀？怎么啦，想和我说说吗？",
                    ),
                    finish_reason="stop",
                ),
            ]
        )
        mode = ReflectionMode(
            name="reflection_mode",
            llm_client=reflection_llm,
            base_mode=base_mode,
            reflection_prompt="你是一个严格但温和的回复审查员。",
            refinement_prompt="你是一个擅长润色陪伴体回复的编辑。",
        )

        result = await mode.run(
            event=AgentEvent.semantic_message(
                message=Message(role=MessageRole.USER, content="你睡了吗？")
            ),
            history=[],
        )

        self.assertEqual(base_mode.calls, 1)
        self.assertEqual(len(reflection_llm.requests), 2)
        self.assertEqual(result.finish_reason, FinishReason.COMPLETED)
        self.assertEqual(
            result.messages[0].content,
            "还没呢，你是不是也还没睡呀？怎么啦，想和我说说吗？",
        )
        self.assertEqual(result.effects[0].type, ModeEffectType.EXECUTE_COMMAND)
        self.assertTrue(result.metadata["reflection"]["should_refine"])
        self.assertTrue(result.metadata["reflection"]["refined"])

    async def test_reflection_mode_can_wrap_plan_solve_mode_without_refinement(self) -> None:
        base_llm = FakeSequenceLLMClient(
            [
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content='["生成回复"]',
                    ),
                    finish_reason="stop",
                    model="qwen3.5-flash-2026-02-23",
                ),
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content="还没呢，怎么啦？",
                    ),
                    finish_reason="stop",
                    model="qwen3.5-flash-2026-02-23",
                ),
            ]
        )
        plan_solve_mode = PlanSolveMode(
            name="plan_solve_mode",
            llm_client=base_llm,
            planner_prompt="你是规划器。",
            executor_prompt="你是执行器。",
            tool_registry=ToolRegistry(),
        )
        reflection_llm = FakeSequenceLLMClient(
            [
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content='{"should_refine": false, "feedback": ""}',
                    ),
                    finish_reason="stop",
                )
            ]
        )
        mode = ReflectionMode(
            name="reflection_mode",
            llm_client=reflection_llm,
            base_mode=plan_solve_mode,
            reflection_prompt="你是审查员。",
            refinement_prompt="你是润色器。",
        )

        result = await mode.run(
            event=AgentEvent.semantic_message(
                message=Message(role=MessageRole.USER, content="帮我回一句简单的晚安前闲聊")
            ),
            history=[],
        )

        self.assertEqual(len(base_llm.requests), 2)
        self.assertEqual(len(reflection_llm.requests), 1)
        self.assertEqual(result.messages[0].content, "还没呢，怎么啦？")
        self.assertFalse(result.metadata["reflection"]["should_refine"])
        self.assertEqual(result.metadata["reflection"]["base_mode_name"], "plan_solve_mode")
