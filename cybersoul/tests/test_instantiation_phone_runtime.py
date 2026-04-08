"""Tests for the Cyrene runtime and scene orchestration layers."""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path
from unittest import TestCase

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
CYBERSOUL_ROOT = PROJECT_ROOT / "cybersoul"
if str(CYBERSOUL_ROOT) not in sys.path:
    sys.path.insert(0, str(CYBERSOUL_ROOT))

from Phone.models import ChatMessage
from agents.core.llm.schemas import LLMRequest, LLMResponse
from agents.core.messaging.message import Message, MessageRole
from agents.core.messaging.mode_result import ModeEffect, ModeEffectType, ModeResult
from agents.runtime import CompanionRuntime
from agents.runtime.execution import RuntimeEffectExecutor
from memory import ActorMemoryStore, MemoryRecord
from instantiation.companions import build_cyrene_agent
from instantiation.amphoreus.context import (
    build_cyrene_runtime_context_builder,
    build_heartbeat_profile,
)
from instantiation.amphoreus.scene_activation import SceneActivationOrchestrator
from instantiation.amphoreus.world_graph import TRANSIT_PLACE_ID
from instantiation.runtime import (
    build_cyrene_companion_runtime,
    build_cyrene_heartbeat_runner,
)
from world.core.clock import WorldClock
from world.core.manager import WorldManager
from world.core.state import ActivityBlock, ActorState, WorldState


class FakeLLMClient:
    def __init__(self) -> None:
        self.requests = []

    async def complete(self, request):
        self.requests.append(request)
        return LLMResponse(
            message=Message(
                role=MessageRole.ASSISTANT,
                content="我在这里，已经看到你发来的话了。",
            )
        )


class FakeSequenceLLMClient:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = responses
        self.requests: list[LLMRequest] = []

    async def complete(self, request):
        self.requests.append(request)
        return self.responses.pop(0)


class ManualWorldClock(WorldClock):
    def __init__(self, *, timezone_name: str = "Asia/Shanghai", started_at=None) -> None:
        super().__init__(timezone_name=timezone_name)
        self._now = self.ensure_aware(started_at or super().now())

    def now(self):
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now = self._now + delta


class StaticResultAgent:
    def __init__(self, result_factory) -> None:
        self.result_factory = result_factory
        self.history: list[Message] = []
        self.captured_history: list[Message] = []

    def clear_history(self) -> None:
        self.history.clear()

    def add_message(self, message: Message) -> None:
        self.history.append(message)

    def add_messages(self, messages: list[Message]) -> None:
        self.history.extend(messages)

    async def handle_event(self, event) -> ModeResult:
        self.captured_history = list(self.history)
        return self.result_factory()


class CyreneCompanionRuntimeTests(TestCase):
    def test_build_cyrene_agent_registers_phone_tool_by_default(self) -> None:
        agent = build_cyrene_agent(llm_client=FakeLLMClient())

        self.assertEqual(agent.get_profile().enabled_tools, ["phone_chat"])
        self.assertEqual([tool.name for tool in agent.list_tools()], ["phone_chat"])

    def test_runtime_can_run_heartbeat_tick_with_shared_context_pipeline(self) -> None:
        fake_llm = FakeLLMClient()
        clock = WorldClock(timezone_name="Asia/Shanghai")
        started_at = clock.now()
        world_manager = WorldManager(
            clock=clock,
            initial_state=WorldState(current_time=started_at),
        )
        world_manager.set_actor_state(
            ActorState(
                actor_id="cyrene",
                current_place_id="okhema",
                current_activity_block=ActivityBlock(
                    activity_type="resting",
                    started_at=started_at,
                    planned_until=started_at + timedelta(minutes=15),
                ),
            )
        )
        runtime = build_cyrene_companion_runtime(
            llm_client=fake_llm,
            world_manager=world_manager,
        )

        result = runtime.run_heartbeat_tick(profile=build_heartbeat_profile())

        self.assertEqual(result.messages[0].content, "我在这里，已经看到你发来的话了。")
        self.assertEqual(result.metadata["runtime"]["context_profile"], "heartbeat")
        self.assertEqual(len(fake_llm.requests), 1)

        request = fake_llm.requests[0]
        self.assertEqual(request.messages[0].metadata["system_prompt_kind"], "base_system_prompt")
        self.assertEqual(request.messages[1].role, MessageRole.SYSTEM)
        self.assertEqual([tool.name for tool in request.tools], ["phone_chat", "travel_to_place"])
        self.assertIn("[Trigger]", request.messages[1].content)
        self.assertIn("profile: heartbeat", request.messages[1].content)
        self.assertIn("[State]", request.messages[1].content)
        self.assertIn("current_place_id: okhema", request.messages[1].content)
        self.assertIn("本轮可用工具如下：", request.messages[1].content)
        self.assertIn("phone_chat", request.messages[1].content)
        self.assertIn("travel_to_place", request.messages[1].content)
        self.assertNotIn("mailbox_status", request.messages[1].content)
        self.assertEqual(len(request.messages), 2)
        self.assertEqual(
            [tool["name"] for tool in result.metadata["runtime"]["available_tools"]],
            ["phone_chat", "travel_to_place"],
        )
        self.assertEqual(
            result.metadata["runtime"]["context_trace"]["selected_packets"][0]["kind"],
            "policy",
        )
        self.assertIn(
            "current_place_id: okhema",
            result.metadata["runtime"]["context_trace"]["runtime_context_text"],
        )

    def test_heartbeat_context_does_not_expose_phone_state_without_tool_observation(self) -> None:
        fake_llm = FakeLLMClient()
        clock = WorldClock(timezone_name="Asia/Shanghai")
        started_at = clock.now()
        world_manager = WorldManager(
            clock=clock,
            initial_state=WorldState(current_time=started_at),
        )
        world_manager.set_actor_state(
            ActorState(
                actor_id="cyrene",
                current_place_id="okhema",
                current_activity_block=ActivityBlock(
                    activity_type="resting",
                    started_at=started_at,
                    planned_until=started_at + timedelta(minutes=15),
                ),
            )
        )
        runtime = build_cyrene_companion_runtime(
            llm_client=fake_llm,
            world_manager=world_manager,
        )
        phone_messages = [
            ChatMessage.create(
                thread_id="thread_hidden",
                sender="user",
                content="你现在方便吗？",
            )
        ]

        runtime.run_heartbeat_tick(
            profile=build_heartbeat_profile(),
            metadata={
                "thread_id": "thread_hidden",
                "phone_messages": phone_messages,
            },
        )

        request = fake_llm.requests[0]
        self.assertNotIn("mailbox_status", request.messages[1].content)
        self.assertNotIn("thread_hidden", request.messages[1].content)
        self.assertNotIn("pending_user_messages", request.messages[1].content)

    def test_runtime_persists_handoff_summary_into_next_heartbeat_context(self) -> None:
        fake_llm = FakeLLMClient()
        clock = WorldClock(timezone_name="Asia/Shanghai")
        started_at = clock.now()
        world_manager = WorldManager(
            clock=clock,
            initial_state=WorldState(current_time=started_at),
        )
        world_manager.set_actor_state(
            ActorState(
                actor_id="cyrene",
                current_place_id="okhema",
                current_activity_block=ActivityBlock(
                    activity_type="resting",
                    started_at=started_at,
                    planned_until=started_at + timedelta(minutes=15),
                ),
            )
        )
        runtime = build_cyrene_companion_runtime(
            llm_client=fake_llm,
            world_manager=world_manager,
        )

        first_result = runtime.run_heartbeat_tick(profile=build_heartbeat_profile())
        second_result = runtime.run_heartbeat_tick(profile=build_heartbeat_profile())

        self.assertEqual(
            first_result.metadata["runtime"]["handoff_summary"]["latest_assistant_message"],
            "我在这里，已经看到你发来的话了。",
        )
        self.assertEqual(
            second_result.metadata["runtime"]["handoff_summary"]["profile_name"],
            "heartbeat",
        )
        self.assertIsNotNone(runtime.get_last_handoff_summary())
        self.assertEqual(len(fake_llm.requests), 2)

        second_request = fake_llm.requests[1]
        self.assertIn("[Context]", second_request.messages[1].content)
        self.assertIn("recent_runtime_handoff:", second_request.messages[1].content)
        self.assertIn(
            "latest_assistant_message: 我在这里，已经看到你发来的话了。",
            second_request.messages[1].content,
        )

    def test_runtime_applies_patch_state_effects_before_handoff(self) -> None:
        clock = WorldClock(timezone_name="Asia/Shanghai")
        started_at = clock.now()
        world_manager = WorldManager(
            clock=clock,
            initial_state=WorldState(current_time=started_at),
        )
        world_manager.set_actor_state(
            ActorState(
                actor_id="cyrene",
                current_place_id="okhema",
                current_activity_block=ActivityBlock(
                    activity_type="resting",
                    started_at=started_at,
                    planned_until=started_at + timedelta(minutes=15),
                ),
            )
        )

        created_agents: list[StaticResultAgent] = []

        def agent_factory() -> StaticResultAgent:
            agent = StaticResultAgent(
                lambda: ModeResult(
                    messages=[
                        Message(
                            role=MessageRole.ASSISTANT,
                            content="我去占星塔看看接下来会发生什么。",
                        )
                    ],
                    effects=[
                        ModeEffect(
                            type=ModeEffectType.PATCH_STATE,
                            payload={
                                "current_place_id": "temple_and_observatory",
                                "activity": {
                                    "activity_type": "divination",
                                    "planned_duration_minutes": 30,
                                    "payload": {"with": "tribbie"},
                                },
                            },
                        )
                    ],
                    summary="move to the observatory",
                )
            )
            created_agents.append(agent)
            return agent

        runtime = CompanionRuntime(
            actor_id="cyrene",
            agent_factory=agent_factory,
            context_builder=build_cyrene_runtime_context_builder(
                system_prompt="你是一个陪伴体。",
            ),
            world_manager=world_manager,
        )

        result = runtime.run_heartbeat_tick(profile=build_heartbeat_profile())

        updated_state = world_manager.get_actor_state("cyrene")
        self.assertIsNotNone(updated_state)
        self.assertEqual(updated_state.current_place_id, "temple_and_observatory")
        self.assertIsNotNone(updated_state.current_activity_block)
        self.assertEqual(updated_state.current_activity_block.activity_type, "divination")
        self.assertEqual(updated_state.current_activity_block.payload, {"with": "tribbie"})
        self.assertEqual(len(created_agents), 1)
        self.assertEqual(
            result.metadata["runtime"]["effect_execution"]["applied_count"],
            1,
        )
        self.assertEqual(
            result.metadata["runtime"]["clean_state"]["pending_effect_count"],
            0,
        )
        self.assertEqual(
            result.metadata["runtime"]["handoff_summary"]["current_place_id"],
            "temple_and_observatory",
        )

    def test_runtime_writes_memory_and_rehydrates_it_into_later_context(self) -> None:
        clock = WorldClock(timezone_name="Asia/Shanghai")
        started_at = clock.now()
        world_manager = WorldManager(
            clock=clock,
            initial_state=WorldState(current_time=started_at),
        )
        world_manager.set_actor_state(
            ActorState(
                actor_id="cyrene",
                current_place_id="temple_and_observatory",
                current_activity_block=ActivityBlock(
                    activity_type="chatting",
                    started_at=started_at,
                    planned_until=started_at + timedelta(minutes=10),
                ),
            )
        )

        memory_store = ActorMemoryStore()
        created_agents: list[StaticResultAgent] = []
        results = [
            ModeResult(
                messages=[
                    Message(
                        role=MessageRole.ASSISTANT,
                        content="缇宝刚替我占了一卦，说我很快会再次想起你。",
                    )
                ],
                effects=[
                    ModeEffect(
                        type=ModeEffectType.WRITE_MEMORY,
                        payload={
                            "memory_type": "relationship",
                            "counterpart_id": "tribbie",
                            "importance": 0.88,
                            "content": "缇宝在占星塔替昔涟占卜，并留下值得下次继续谈起的结果。",
                            "summary": "缇宝替昔涟占卜过，下次见面可继续延续这件事。",
                            "tags": ["tribbie", "divination"],
                        },
                    )
                ],
                summary="write back the divination encounter",
            ),
            ModeResult(
                messages=[
                    Message(
                        role=MessageRole.ASSISTANT,
                        content="我记得上次在这里，缇宝替我占过一卦。",
                    )
                ],
                summary="recall the previous scene memory",
            ),
        ]

        def agent_factory() -> StaticResultAgent:
            agent = StaticResultAgent(lambda: results.pop(0))
            created_agents.append(agent)
            return agent

        runtime = CompanionRuntime(
            actor_id="cyrene",
            agent_factory=agent_factory,
            context_builder=build_cyrene_runtime_context_builder(
                system_prompt="你是一个陪伴体。",
                memory_store=memory_store,
            ),
            world_manager=world_manager,
            effect_executor=RuntimeEffectExecutor(memory_store=memory_store),
        )

        first_result = runtime.run_heartbeat_tick(profile=build_heartbeat_profile())
        second_result = runtime.run_heartbeat_tick(profile=build_heartbeat_profile())

        self.assertEqual(len(memory_store), 1)
        self.assertEqual(
            first_result.metadata["runtime"]["effect_execution"]["applied_count"],
            1,
        )
        self.assertEqual(
            first_result.metadata["runtime"]["effect_execution"]["records"][0]["effect_type"],
            "write_memory",
        )
        self.assertEqual(len(created_agents), 2)
        self.assertIn("[Memory]", created_agents[1].captured_history[0].content)
        self.assertIn(
            "memory_type: relationship",
            created_agents[1].captured_history[0].content,
        )
        self.assertIn(
            "缇宝替昔涟占卜过，下次见面可继续延续这件事。",
            created_agents[1].captured_history[0].content,
        )
        self.assertEqual(
            second_result.messages[0].content,
            "我记得上次在这里，缇宝替我占过一卦。",
        )


class SceneActivationOrchestratorTests(TestCase):
    def test_scene_orchestrator_activates_visible_npc_with_a2a_envelope_and_memory(self) -> None:
        fake_llm = FakeSequenceLLMClient(
            [
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content="我在这里，已经看到你发来的话了。",
                    )
                ),
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content="NOOP",
                    )
                ),
            ]
        )
        clock = WorldClock(timezone_name="Asia/Shanghai")
        started_at = clock.now()
        world_manager = WorldManager(
            clock=clock,
            initial_state=WorldState(current_time=started_at),
        )
        world_manager.set_actor_state(
            ActorState(
                actor_id="cyrene",
                current_place_id="temple_and_observatory",
                current_activity_block=ActivityBlock(
                    activity_type="visiting",
                    started_at=started_at,
                    planned_until=started_at + timedelta(minutes=20),
                ),
            )
        )
        world_manager.set_actor_state(
            ActorState(
                actor_id="tribbie",
                current_place_id="temple_and_observatory",
                current_activity_block=ActivityBlock(
                    activity_type="watching_stars",
                    started_at=started_at,
                    planned_until=started_at + timedelta(minutes=20),
                ),
            )
        )

        memory_store = ActorMemoryStore()
        memory_store.add(
            MemoryRecord(
                actor_id="tribbie",
                memory_type="relationship",
                counterpart_id="cyrene",
                place_id="temple_and_observatory",
                importance=0.91,
                content="上次昔涟来到占星塔时，缇宝曾替她点灯并留下温柔的祝愿。",
                summary="缇宝记得自己曾替昔涟点过灯。",
                created_at=started_at,
            )
        )

        orchestrator = SceneActivationOrchestrator(
            world_manager=world_manager,
            memory_store=memory_store,
            llm_client=fake_llm,
        )

        turns = orchestrator.activate_for_actor(
            actor_id="cyrene",
            initiating_content="昔涟轻轻走上占星塔，抬头看向今晚的星影。",
            intent="respond_to_arrival",
            causal_ref="cyrene_turn_1",
        )

        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0].target_agent_id, "tribbie")
        self.assertEqual(turns[1].target_agent_id, "cyrene")
        self.assertEqual(turns[0].envelope.from_agent, "cyrene")
        self.assertEqual(turns[0].envelope.to_agent, "tribbie")
        self.assertEqual(turns[0].envelope.scene_id, "temple_and_observatory")
        self.assertEqual(
            turns[0].result.messages[0].content,
            "我在这里，已经看到你发来的话了。",
        )
        self.assertTrue(turns[1].result.is_noop)

        self.assertEqual(len(fake_llm.requests), 2)
        first_request = fake_llm.requests[0]
        second_request = fake_llm.requests[1]
        self.assertEqual(first_request.messages[0].metadata["system_prompt_kind"], "base_system_prompt")
        self.assertIn("[Trigger]", first_request.messages[1].content)
        self.assertIn("scene_id=temple_and_observatory", first_request.messages[1].content)
        self.assertIn("incoming_message: 昔涟轻轻走上占星塔，抬头看向今晚的星影。", first_request.messages[1].content)
        self.assertIn("[Memory]", first_request.messages[1].content)
        self.assertIn("缇宝记得自己曾替昔涟点过灯。", first_request.messages[1].content)
        self.assertIn(second_request.messages[-1].content, ["我在这里，已经看到你发来的话了。"])

    def test_scene_orchestrator_allows_tribbie_to_call_divination_tool(self) -> None:
        llm_client = FakeSequenceLLMClient(
            [
                LLMResponse(
                    tool_calls=[
                        {
                            "id": "tool_tribbie_1",
                            "name": "tribbie_divination",
                            "arguments": {
                                "question": "昔涟此刻是否适合把心事说出口？",
                            },
                        }
                    ]
                ),
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content="让我替你占一卦。灯火是吉的，你可以先把话说出一半。",
                    )
                ),
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content="NOOP",
                    )
                ),
            ]
        )
        clock = WorldClock(timezone_name="Asia/Shanghai")
        started_at = clock.now()
        world_manager = WorldManager(
            clock=clock,
            initial_state=WorldState(current_time=started_at),
        )
        world_manager.set_actor_state(
            ActorState(
                actor_id="cyrene",
                current_place_id="temple_and_observatory",
                current_activity_block=ActivityBlock(
                    activity_type="visiting",
                    started_at=started_at,
                    planned_until=started_at + timedelta(minutes=20),
                ),
            )
        )
        world_manager.set_actor_state(
            ActorState(
                actor_id="tribbie",
                current_place_id="temple_and_observatory",
                current_activity_block=ActivityBlock(
                    activity_type="watching_stars",
                    started_at=started_at,
                    planned_until=started_at + timedelta(minutes=20),
                ),
            )
        )

        orchestrator = SceneActivationOrchestrator(
            world_manager=world_manager,
            llm_client=llm_client,
        )

        turns = orchestrator.activate_for_actor(
            actor_id="cyrene",
            initiating_content="昔涟轻声问：缇宝，要不要替我占一卦？",
            intent="scene_enter",
            causal_ref="cyrene_arrival_1",
        )

        self.assertEqual(len(turns), 2)
        self.assertEqual(
            turns[0].result.messages[0].content,
            "让我替你占一卦。灯火是吉的，你可以先把话说出一半。",
        )
        self.assertTrue(turns[1].result.is_noop)
        self.assertEqual(len(llm_client.requests), 3)
        first_request = llm_client.requests[0]
        second_request = llm_client.requests[1]
        third_request = llm_client.requests[2]
        self.assertEqual([tool.name for tool in first_request.tools], ["tribbie_divination"])
        self.assertIn("current_place_activities:", first_request.messages[1].content)
        self.assertIn("tribbie_divination", first_request.messages[1].content)
        self.assertEqual(second_request.messages[-1].role, MessageRole.TOOL)
        self.assertIn("占兆结果:", second_request.messages[-1].content)
        self.assertEqual(third_request.messages[-1].content, "让我替你占一卦。灯火是吉的，你可以先把话说出一半。")


class CyreneHeartbeatRunnerTests(TestCase):
    def test_runner_single_tick_drives_cyrene_then_scene_activation(self) -> None:
        fake_llm = FakeSequenceLLMClient(
            [
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content="我在这里，已经看到你发来的话了。",
                    )
                ),
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content="欢迎来这里，今晚的星盘正好肯说话。",
                    )
                ),
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content="NOOP",
                    )
                ),
            ]
        )
        clock = WorldClock(timezone_name="Asia/Shanghai")
        started_at = clock.now()
        world_manager = WorldManager(
            clock=clock,
            initial_state=WorldState(current_time=started_at),
        )
        world_manager.set_actor_state(
            ActorState(
                actor_id="cyrene",
                current_place_id="temple_and_observatory",
                current_activity_block=ActivityBlock(
                    activity_type="visiting",
                    started_at=started_at,
                    planned_until=started_at + timedelta(minutes=20),
                ),
            )
        )
        world_manager.set_actor_state(
            ActorState(
                actor_id="tribbie",
                current_place_id="temple_and_observatory",
                current_activity_block=ActivityBlock(
                    activity_type="watching_stars",
                    started_at=started_at,
                    planned_until=started_at + timedelta(minutes=20),
                ),
            )
        )

        runner = build_cyrene_heartbeat_runner(
            llm_client=fake_llm,
            world_manager=world_manager,
        )

        record = runner.run_tick()

        self.assertEqual(record.tick_index, 1)
        self.assertEqual(record.actor_place_id, "temple_and_observatory")
        self.assertEqual(record.cyrene_result.messages[0].content, "我在这里，已经看到你发来的话了。")
        self.assertEqual(len(record.scene_turns), 2)
        self.assertEqual(record.scene_turns[0].target_agent_id, "tribbie")
        self.assertEqual(record.scene_turns[1].target_agent_id, "cyrene")
        self.assertEqual(
            record.scene_turns[0].envelope.content,
            "我在这里，已经看到你发来的话了。",
        )
        self.assertTrue(record.scene_turns[1].result.is_noop)
        self.assertEqual(len(fake_llm.requests), 3)

    def test_runner_loop_runs_multiple_ticks_and_accumulates_records(self) -> None:
        fake_llm = FakeSequenceLLMClient(
            [
                LLMResponse(message=Message(role=MessageRole.ASSISTANT, content="我在这里，已经看到你发来的话了。")),
                LLMResponse(message=Message(role=MessageRole.ASSISTANT, content="今晚的风很轻。")),
                LLMResponse(message=Message(role=MessageRole.ASSISTANT, content="NOOP")),
                LLMResponse(message=Message(role=MessageRole.ASSISTANT, content="我在这里，已经看到你发来的话了。")),
                LLMResponse(message=Message(role=MessageRole.ASSISTANT, content="钟声刚刚又响了一次。")),
                LLMResponse(message=Message(role=MessageRole.ASSISTANT, content="NOOP")),
            ]
        )
        clock = WorldClock(timezone_name="Asia/Shanghai")
        started_at = clock.now()
        world_manager = WorldManager(
            clock=clock,
            initial_state=WorldState(current_time=started_at),
        )
        world_manager.set_actor_state(
            ActorState(
                actor_id="cyrene",
                current_place_id="temple_and_observatory",
                current_activity_block=ActivityBlock(
                    activity_type="visiting",
                    started_at=started_at,
                    planned_until=started_at + timedelta(minutes=20),
                ),
            )
        )
        world_manager.set_actor_state(
            ActorState(
                actor_id="tribbie",
                current_place_id="temple_and_observatory",
                current_activity_block=ActivityBlock(
                    activity_type="watching_stars",
                    started_at=started_at,
                    planned_until=started_at + timedelta(minutes=20),
                ),
            )
        )

        runner = build_cyrene_heartbeat_runner(
            llm_client=fake_llm,
            world_manager=world_manager,
        )

        records = runner.run_loop(max_ticks=2, interval_seconds=0.0)

        self.assertEqual([record.tick_index for record in records], [1, 2])
        self.assertEqual(runner.tick_count, 2)
        self.assertEqual([len(record.scene_turns) for record in records], [2, 2])
        self.assertEqual(len(fake_llm.requests), 6)

    def test_travel_tool_closes_origin_scene_and_reactivates_destination_after_arrival(self) -> None:
        llm_client = FakeSequenceLLMClient(
            [
                LLMResponse(
                    tool_calls=[
                        {
                            "id": "travel_1",
                            "name": "travel_to_place",
                            "arguments": {
                                "destination_place_id": "temple_and_observatory",
                            },
                        }
                    ]
                ),
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content="我先离开奥赫玛，去占星塔看看今晚的风。",
                    )
                ),
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content="我到了，钟声和风都比城里更近一些。",
                    )
                ),
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content="欢迎来这里，今晚的星盘正好肯说话。",
                    )
                ),
                LLMResponse(
                    message=Message(
                        role=MessageRole.ASSISTANT,
                        content="NOOP",
                    )
                ),
            ]
        )
        clock = ManualWorldClock()
        started_at = clock.now()
        world_manager = WorldManager(
            clock=clock,
            initial_state=WorldState(current_time=started_at),
        )
        world_manager.set_actor_state(
            ActorState(
                actor_id="cyrene",
                current_place_id="okhema",
                current_activity_block=ActivityBlock(
                    activity_type="wandering",
                    started_at=started_at,
                    planned_until=started_at + timedelta(minutes=10),
                ),
            )
        )
        world_manager.set_actor_state(
            ActorState(
                actor_id="aglaea",
                current_place_id="okhema",
                current_activity_block=ActivityBlock(
                    activity_type="inspecting_city",
                    started_at=started_at,
                    planned_until=started_at + timedelta(minutes=20),
                ),
            )
        )
        world_manager.set_actor_state(
            ActorState(
                actor_id="tribbie",
                current_place_id="temple_and_observatory",
                current_activity_block=ActivityBlock(
                    activity_type="watching_stars",
                    started_at=started_at,
                    planned_until=started_at + timedelta(minutes=20),
                ),
            )
        )

        runner = build_cyrene_heartbeat_runner(
            llm_client=llm_client,
            world_manager=world_manager,
        )

        first_record = runner.run_tick()

        updated_state = world_manager.get_actor_state("cyrene")
        self.assertEqual(first_record.actor_place_id, TRANSIT_PLACE_ID)
        self.assertEqual(len(first_record.scene_turns), 0)
        self.assertIsNotNone(updated_state.current_activity_block)
        self.assertEqual(updated_state.current_activity_block.activity_type, "travel")
        self.assertEqual(
            updated_state.current_activity_block.payload["destination_place_id"],
            "temple_and_observatory",
        )

        clock.advance(timedelta(minutes=19))
        second_record = runner.run_tick()

        arrived_state = world_manager.get_actor_state("cyrene")
        self.assertEqual(second_record.actor_place_id, "temple_and_observatory")
        self.assertEqual(arrived_state.current_place_id, "temple_and_observatory")
        self.assertIsNone(arrived_state.current_activity_block)
        self.assertEqual(len(second_record.scene_turns), 2)
        self.assertEqual(second_record.scene_turns[0].target_agent_id, "tribbie")
        self.assertEqual(second_record.scene_turns[1].target_agent_id, "cyrene")
        self.assertTrue(second_record.scene_turns[1].result.is_noop)
        self.assertEqual(len(llm_client.requests), 5)
        self.assertIn("world_transition:", llm_client.requests[2].messages[1].content)
        self.assertIn("to_place_id: temple_and_observatory", llm_client.requests[2].messages[1].content)
        self.assertIn("current_place_activities:", llm_client.requests[2].messages[1].content)
