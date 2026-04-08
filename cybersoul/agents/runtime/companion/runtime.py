"""Minimal actor-centric runtime for companion agents."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Callable, Sequence

from agents.context import (
    ContextBuildRequest,
    ContextBuilder,
    ContextPacket,
    ContextProfile,
)
from agents.core.messaging.event import AgentEvent, EventSource
from agents.core.messaging.message import Message
from agents.core.messaging.mode_result import ModeResult
from agents.runtime.execution import RuntimeEffectExecutor, RuntimeHandoffSummary
from world.core.manager import WorldManager


class CompanionRuntime:
    """Run a companion agent against actor-centric context and world state."""

    def __init__(
        self,
        *,
        actor_id: str,
        agent_factory: Callable[[], CompanionAgent],
        context_builder: ContextBuilder,
        world_manager: WorldManager | None = None,
        effect_executor: RuntimeEffectExecutor | None = None,
    ) -> None:
        self.actor_id = actor_id
        self.agent_factory = agent_factory
        self.context_builder = context_builder
        self.world_manager = world_manager or WorldManager()
        self.effect_executor = effect_executor or RuntimeEffectExecutor()
        self._last_handoff_summary: RuntimeHandoffSummary | None = None

    def run_event(
        self,
        *,
        event: AgentEvent,
        profile: ContextProfile,
        history: Sequence[Message] | None = None,
        scene_messages: Sequence[Message] | None = None,
        custom_packets: Sequence[ContextPacket] | None = None,
        metadata: dict | None = None,
    ) -> ModeResult:
        agent = self.agent_factory()
        world_state = self.world_manager.snapshot()
        actor_state = world_state.get_actor_state(self.actor_id)
        runtime_packets = list(custom_packets or [])
        if self._last_handoff_summary is not None:
            runtime_packets.append(self._last_handoff_summary.to_packet())
        request_metadata = dict(metadata or {})
        available_tools = self._serialize_tools(agent)
        if available_tools:
            request_metadata["available_tools"] = available_tools
        profile_payload = self._serialize_agent_profile(agent)
        if profile_payload is not None:
            request_metadata["agent_profile"] = profile_payload
        context_bundle = self.context_builder.build(
            ContextBuildRequest(
                actor_id=self.actor_id,
                profile=profile,
                event=event,
                world_state=world_state,
                actor_state=actor_state,
                recent_messages=list(history or []),
                scene_messages=list(scene_messages or []),
                custom_packets=runtime_packets,
                metadata=request_metadata,
            )
        )

        agent.clear_history()
        agent.add_message(context_bundle.to_system_message())
        if history:
            agent.add_messages(list(history))

        result = asyncio.run(agent.handle_event(event))
        execution_report = self.effect_executor.execute(
            actor_id=self.actor_id,
            effects=list(result.effects),
            world_manager=self.world_manager,
            reference_time=world_state.current_time,
        )
        updated_world_state = self.world_manager.snapshot()
        updated_actor_state = updated_world_state.get_actor_state(self.actor_id)
        handoff_summary = RuntimeHandoffSummary.from_turn(
            actor_id=self.actor_id,
            profile_name=profile.name,
            world_state=updated_world_state,
            actor_state=updated_actor_state,
            result=result,
        )
        self._last_handoff_summary = handoff_summary
        result.metadata.setdefault("runtime", {})
        result.metadata["runtime"].update(
            {
                "actor_id": self.actor_id,
                "context_profile": profile.name,
                "selected_packet_count": len(context_bundle.selected_packets),
                "truncated_packet_count": len(context_bundle.truncated_packets),
                "context_token_estimate": context_bundle.token_estimate,
                "available_tools": available_tools,
                "agent_profile": profile_payload,
                "event_trace": self._serialize_event(event),
                "context_trace": {
                    "base_system_prompt": context_bundle.system_prompt,
                    "runtime_context_text": context_bundle.runtime_context_text,
                    "selected_packets": self._serialize_packets(
                        context_bundle.selected_packets
                    ),
                    "truncated_packets": self._serialize_packets(
                        context_bundle.truncated_packets
                    ),
                },
                "effect_execution": execution_report.to_payload(),
                "handoff_summary": handoff_summary.to_payload(),
                "clean_state": {
                    "context_attached": True,
                    "handoff_summary_written": True,
                    "actor_state_available": updated_actor_state is not None,
                    "requested_effect_count": len(result.effects),
                    "pending_effect_count": execution_report.pending_count,
                    "effect_error_count": execution_report.error_count,
                },
            }
        )
        return result

    def run_heartbeat_tick(
        self,
        *,
        profile: ContextProfile,
        history: Sequence[Message] | None = None,
        scene_messages: Sequence[Message] | None = None,
        custom_packets: Sequence[ContextPacket] | None = None,
        metadata: dict | None = None,
    ) -> ModeResult:
        event = AgentEvent.perception(
            source=EventSource.SCHEDULER,
            payload={
                "actor_id": self.actor_id,
                "trigger": "heartbeat",
                "profile": profile.name,
            },
            metadata={
                "companion_id": self.actor_id,
                "trigger": "heartbeat",
            },
        )
        return self.run_event(
            event=event,
            profile=profile,
            history=history,
            scene_messages=scene_messages,
            custom_packets=custom_packets,
            metadata=metadata,
        )

    def get_last_handoff_summary(self) -> RuntimeHandoffSummary | None:
        """Return the latest structured summary emitted by this runtime."""

        return self._last_handoff_summary

    def _serialize_tools(self, agent) -> list[dict]:
        if not hasattr(agent, "list_tools"):
            return []
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters_schema": self._json_safe(tool.parameters_schema),
            }
            for tool in agent.list_tools()
        ]

    def _serialize_agent_profile(self, agent) -> dict | None:
        try:
            return self._json_safe(agent.get_profile_payload())
        except AttributeError:
            return None

    def _serialize_event(self, event: AgentEvent | None) -> dict | None:
        if event is None:
            return None
        return {
            "id": event.id,
            "type": event.type.value,
            "source": event.source.value,
            "occurred_at": event.occurred_at.isoformat(),
            "payload": self._json_safe(event.payload),
            "metadata": self._json_safe(event.metadata),
            "message": self._serialize_message(event.message),
        }

    def _serialize_packets(
        self,
        packets: Sequence[ContextPacket],
    ) -> list[dict[str, object]]:
        return [
            {
                "packet_id": packet.packet_id,
                "kind": packet.kind,
                "section": packet.section,
                "timestamp": packet.timestamp.isoformat(),
                "relevance_score": packet.relevance_score,
                "token_count": packet.token_count,
                "content": packet.content,
                "metadata": self._json_safe(packet.metadata),
            }
            for packet in packets
        ]

    def _serialize_message(self, message: Message | None) -> dict | None:
        if message is None:
            return None
        return {
            "id": message.id,
            "role": message.role.value,
            "name": message.name,
            "content": message.content,
            "tool_call_id": message.tool_call_id,
            "tool_calls": self._json_safe(message.tool_calls),
            "metadata": self._json_safe(message.metadata),
            "created_at": message.created_at.isoformat(),
        }

    def _json_safe(self, value):
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {
                str(key): self._json_safe(inner_value)
                for key, inner_value in value.items()
            }
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [self._json_safe(item) for item in value]
        if hasattr(value, "model_dump"):
            return self._json_safe(value.model_dump(mode="json"))
        return value
