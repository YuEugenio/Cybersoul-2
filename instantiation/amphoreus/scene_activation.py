"""Minimal scene activation orchestration for Amphoreus NPCs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from agents.core.messaging.agent_message import AgentMessageEnvelope
from agents.core.messaging.event import AgentEvent, EventSource
from agents.core.messaging.message import Message, MessageRole
from agents.core.messaging.mode_result import ModeResult
from agents.runtime import CompanionRuntime
from agents.runtime.execution import RuntimeEffectExecutor
from memory import ActorMemoryStore
from world.core.manager import WorldManager

from instantiation.amphoreus.context import (
    VisibleNpcResolver,
    build_cyrene_runtime_context_builder,
    build_scene_context_builder,
    build_scene_turn_profile,
)
from instantiation.amphoreus.companions import build_cyrene_agent
from instantiation.amphoreus.prompts import build_cyrene_system_prompt
from instantiation.amphoreus.scene_agents import build_scene_agent, build_scene_agent_system_prompt


@dataclass(slots=True)
class SceneActivationTurn:
    """One NPC turn activated from the current scene."""

    target_agent_id: str
    envelope: AgentMessageEnvelope
    result: ModeResult


class SceneActivationOrchestrator:
    """Activate resident NPC agents when the protagonist enters their scene."""

    def __init__(
        self,
        *,
        world_manager: WorldManager,
        memory_store: ActorMemoryStore | None = None,
        llm_client=None,
        visible_npc_resolver: VisibleNpcResolver | None = None,
        scene_turn_limit: int = 6,
    ) -> None:
        self.world_manager = world_manager
        self.memory_store = memory_store or ActorMemoryStore()
        self.llm_client = llm_client
        self.visible_npc_resolver = visible_npc_resolver or VisibleNpcResolver()
        self.scene_turn_limit = max(1, scene_turn_limit)

    def activate_for_actor(
        self,
        *,
        actor_id: str,
        initiating_content: str,
        scene_id: str | None = None,
        intent: str = "scene_update",
        causal_ref: str | None = None,
        protagonist_runtime: CompanionRuntime | None = None,
    ) -> list[SceneActivationTurn]:
        actor_state = self.world_manager.get_actor_state(actor_id)
        if actor_state is None:
            return []

        resolved_scene_id = scene_id or actor_state.current_place_id
        visible_npcs = [
            npc_id
            for npc_id in self.visible_npc_resolver.resolve(actor_state.current_place_id)
            if npc_id != actor_id
        ]

        turns: list[SceneActivationTurn] = []
        for npc_id in visible_npcs:
            turns.extend(
                self._run_scene_session(
                    actor_id=actor_id,
                    npc_id=npc_id,
                    initiating_content=initiating_content,
                    scene_id=resolved_scene_id,
                    intent=intent,
                    causal_ref=causal_ref,
                    protagonist_runtime=protagonist_runtime,
                )
            )
        return turns

    def _run_scene_session(
        self,
        *,
        actor_id: str,
        npc_id: str,
        initiating_content: str,
        scene_id: str,
        intent: str,
        causal_ref: str | None,
        protagonist_runtime: CompanionRuntime | None,
    ) -> list[SceneActivationTurn]:
        turns: list[SceneActivationTurn] = []
        history: list[Message] = []
        current_sender_id = actor_id
        current_receiver_id = npc_id
        current_content = initiating_content
        current_intent = intent

        for scene_turn_index in range(1, self.scene_turn_limit + 1):
            if not self._actors_share_scene(current_sender_id, current_receiver_id, scene_id):
                break

            envelope = AgentMessageEnvelope(
                from_agent=current_sender_id,
                to_agent=current_receiver_id,
                scene_id=scene_id,
                message_type="scene_turn",
                intent=current_intent,
                content=current_content,
                causal_ref=causal_ref,
                metadata={
                    "activation_source": "scene_orchestrator",
                    "scene_turn_index": scene_turn_index,
                },
            )
            receiver_runtime = self._resolve_runtime(
                actor_id=current_receiver_id,
                protagonist_runtime=protagonist_runtime,
            )
            event = AgentEvent.semantic_message(
                message=envelope.to_message(),
                source=EventSource.RUNTIME,
                payload={
                    "scene_id": scene_id,
                    "from_agent": current_sender_id,
                    "to_agent": current_receiver_id,
                    "message_type": "scene_turn",
                    "intent": current_intent,
                    "scene_turn_index": scene_turn_index,
                },
                metadata={
                    "scene_id": scene_id,
                    "activation_source": "scene_orchestrator",
                    "scene_turn_index": scene_turn_index,
                },
                causation_id=causal_ref,
            )
            result = receiver_runtime.run_event(
                event=event,
                profile=build_scene_turn_profile(),
                history=history,
                metadata={
                    "scene_id": scene_id,
                    "memory_counterpart_ids": [current_sender_id],
                    "scene_turn_index": scene_turn_index,
                },
            )
            turns.append(
                SceneActivationTurn(
                    target_agent_id=current_receiver_id,
                    envelope=envelope,
                    result=result,
                )
            )
            history.append(envelope.to_message())

            reply_message = self._last_assistant_message(result.messages)
            if result.is_noop or reply_message is None:
                break

            current_sender_id, current_receiver_id = current_receiver_id, current_sender_id
            current_content = reply_message.content
            current_intent = "scene_reply"

        return turns

    def _build_npc_runtime(self, npc_id: str) -> CompanionRuntime:
        system_prompt = build_scene_agent_system_prompt(npc_id)
        return CompanionRuntime(
            actor_id=npc_id,
            agent_factory=lambda: build_scene_agent(
                npc_id,
                llm_client=self.llm_client,
                system_prompt=system_prompt,
            ),
            context_builder=build_scene_context_builder(
                system_prompt=system_prompt,
                memory_store=self.memory_store,
            ),
            world_manager=self.world_manager,
            effect_executor=RuntimeEffectExecutor(memory_store=self.memory_store),
        )

    def _build_protagonist_runtime(self, actor_id: str) -> CompanionRuntime:
        if actor_id != "cyrene":
            raise ValueError(f"unsupported protagonist actor_id: {actor_id}")

        system_prompt = build_cyrene_system_prompt()
        return CompanionRuntime(
            actor_id=actor_id,
            agent_factory=lambda: build_cyrene_agent(
                llm_client=self.llm_client,
                system_prompt=system_prompt,
                world_manager=self.world_manager,
            ),
            context_builder=build_cyrene_runtime_context_builder(
                system_prompt=system_prompt,
                memory_store=self.memory_store,
            ),
            world_manager=self.world_manager,
            effect_executor=RuntimeEffectExecutor(memory_store=self.memory_store),
        )

    def _resolve_runtime(
        self,
        *,
        actor_id: str,
        protagonist_runtime: CompanionRuntime | None,
    ) -> CompanionRuntime:
        if protagonist_runtime is not None and actor_id == protagonist_runtime.actor_id:
            return protagonist_runtime
        if actor_id == "cyrene":
            return self._build_protagonist_runtime(actor_id)
        return self._build_npc_runtime(actor_id)

    def _actors_share_scene(
        self,
        sender_id: str,
        receiver_id: str,
        scene_id: str,
    ) -> bool:
        sender_state = self.world_manager.get_actor_state(sender_id)
        receiver_state = self.world_manager.get_actor_state(receiver_id)
        if sender_state is None or receiver_state is None:
            return False
        return (
            sender_state.current_place_id == scene_id
            and receiver_state.current_place_id == scene_id
        )

    def _last_assistant_message(
        self,
        messages: Sequence[Message],
    ) -> Message | None:
        for message in reversed(messages):
            if message.role is MessageRole.ASSISTANT and message.content.strip():
                return message
        return None


__all__ = [
    "SceneActivationTurn",
    "SceneActivationOrchestrator",
]
