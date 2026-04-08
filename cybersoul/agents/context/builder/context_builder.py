"""A minimal actor-centric context builder following the GSSC pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from agents.context.compression import TokenBudgetCompactor
from agents.context.packets import (
    ContextBuildRequest,
    ContextBundle,
    ContextPacket,
)
from agents.context.templates import ContextTemplateRenderer


class ContextPacketProvider(Protocol):
    """Protocol implemented by instance-level packet providers."""

    def build_packets(self, request: ContextBuildRequest) -> list[ContextPacket]:
        """Return zero or more packets for the current request."""


class ContextBuilder:
    """Gather, select, structure, and compact runtime context packets."""

    def __init__(
        self,
        *,
        system_prompt: str,
        packet_providers: tuple[ContextPacketProvider, ...] = (),
        renderer: ContextTemplateRenderer | None = None,
        compactor: TokenBudgetCompactor | None = None,
    ) -> None:
        self.system_prompt = system_prompt
        self.packet_providers = packet_providers
        self.renderer = renderer or ContextTemplateRenderer()
        self.compactor = compactor or TokenBudgetCompactor()

    def build(self, request: ContextBuildRequest) -> ContextBundle:
        packets = self._gather(request)
        ranked_packets = self._select(request, packets)
        selected_packets, truncated_packets = self.compactor.compact(
            ranked_packets,
            max_tokens=request.profile.max_tokens,
        )
        runtime_context_text = self._structure(selected_packets)
        return ContextBundle(
            system_prompt=self.system_prompt,
            runtime_context_text=runtime_context_text,
            selected_packets=selected_packets,
            truncated_packets=truncated_packets,
            token_estimate=sum(packet.token_count for packet in selected_packets),
            metadata={
                "context_owner": request.actor_id,
                "context_profile": request.profile.name,
                "selected_packet_count": len(selected_packets),
                "truncated_packet_count": len(truncated_packets),
            },
        )

    def _gather(self, request: ContextBuildRequest) -> list[ContextPacket]:
        packets = [
            self._build_policy_packet(request),
            self._build_trigger_packet(request),
            self._build_state_packet(request),
        ]
        tool_packet = self._build_tool_packet(request)
        if tool_packet is not None:
            packets.append(tool_packet)
        packets.append(self._build_output_contract_packet(request))
        for provider in self.packet_providers:
            packets.extend(provider.build_packets(request))
        packets.extend(request.custom_packets)
        return [packet for packet in packets if packet.content.strip()]

    def _select(
        self,
        request: ContextBuildRequest,
        packets: list[ContextPacket],
    ) -> list[ContextPacket]:
        filtered = [
            packet
            for packet in packets
            if self._packet_allowed(request, packet)
        ]
        now = self._reference_time(request)
        ranked = sorted(
            filtered,
            key=lambda packet: (
                self._priority_bucket(request, packet),
                -self._score_packet(request, packet, now),
                packet.section,
            ),
        )
        return ranked

    def _structure(self, packets: list[ContextPacket]) -> str:
        return self.renderer.render(packets)

    def _packet_allowed(
        self,
        request: ContextBuildRequest,
        packet: ContextPacket,
    ) -> bool:
        profile = request.profile
        if packet.kind == "place_card" and not profile.include_place_card:
            return False
        if packet.kind == "npc_card" and not profile.include_visible_npcs:
            return False
        return True

    def _priority_bucket(
        self,
        request: ContextBuildRequest,
        packet: ContextPacket,
    ) -> int:
        if packet.kind in request.profile.required_kinds:
            return 0
        if packet.kind in request.profile.preferred_kinds:
            return 1
        return 2

    def _score_packet(
        self,
        request: ContextBuildRequest,
        packet: ContextPacket,
        reference_time: datetime,
    ) -> float:
        age_seconds = max(
            0.0,
            (reference_time - packet.timestamp.astimezone(timezone.utc)).total_seconds(),
        )
        recency_score = 1.0 / (1.0 + (age_seconds / 3600.0))
        return (
            request.profile.relevance_weight * packet.relevance_score
            + request.profile.recency_weight * recency_score
        )

    def _reference_time(self, request: ContextBuildRequest) -> datetime:
        if request.world_state is not None:
            return request.world_state.current_time.astimezone(timezone.utc)
        if request.event is not None:
            return request.event.occurred_at.astimezone(timezone.utc)
        return datetime.now(timezone.utc)

    def _build_policy_packet(self, request: ContextBuildRequest) -> ContextPacket:
        return ContextPacket(
            kind="policy",
            section="role_policies",
            content=(
                "以下内容是本轮运行时上下文补充。"
                "它用于帮助当前 actor 在此刻做判断，不覆盖基础 system prompt 中的稳定身份、长期规则与人格设定。"
            ),
            relevance_score=1.0,
        )

    def _build_trigger_packet(self, request: ContextBuildRequest) -> ContextPacket:
        if request.event is None:
            content = f"当前触发来源未显式提供，本轮按 profile={request.profile.name} 组织上下文。"
            timestamp = self._reference_time(request)
        else:
            lines = [
                f"event_type: {request.event.type.value}",
                f"source: {request.event.source.value}",
                f"profile: {request.profile.name}",
            ]
            if request.event.message is not None and request.event.message.content.strip():
                lines.append("incoming_message: " + request.event.message.content.strip())
            if request.event.payload:
                payload_items = ", ".join(
                    f"{key}={value}" for key, value in sorted(request.event.payload.items())
                )
                lines.append("payload: " + payload_items)
            content = "\n".join(lines)
            timestamp = request.event.occurred_at

        return ContextPacket(
            kind="event",
            section="trigger",
            content=content,
            timestamp=timestamp,
            relevance_score=1.0,
        )

    def _build_state_packet(self, request: ContextBuildRequest) -> ContextPacket:
        lines: list[str] = []
        timestamp = self._reference_time(request)

        if request.world_state is not None:
            lines.append("current_time: " + request.world_state.current_time.isoformat())
        if request.actor_state is not None:
            lines.append("current_place_id: " + request.actor_state.current_place_id)
            activity_block = request.actor_state.current_activity_block
            if activity_block is not None:
                lines.append("current_activity_type: " + activity_block.activity_type)
                lines.append("activity_started_at: " + activity_block.started_at.isoformat())
                if activity_block.planned_until is not None:
                    lines.append(
                        "activity_planned_until: " + activity_block.planned_until.isoformat()
                    )
                if activity_block.payload:
                    payload_items = ", ".join(
                        f"{key}={value}"
                        for key, value in sorted(activity_block.payload.items())
                    )
                    lines.append("activity_payload: " + payload_items)
        if not lines:
            lines.append("当前 world state / actor state 尚未提供完整信息。")

        return ContextPacket(
            kind="state",
            section="state",
            content="\n".join(lines),
            timestamp=timestamp,
            relevance_score=1.0,
        )

    def _build_output_contract_packet(self, request: ContextBuildRequest) -> ContextPacket:
        contract_by_profile = {
            "heartbeat": (
                "本轮优先判断下一步生活推进、是否需要观察手机、是否需要推进地点或活动，"
                "没有必要时可以保持安静并输出 no-op。"
            ),
            "scene_turn": (
                "本轮优先给出场景内的一步回应、提议、动作或工具调用。"
                "不要替其他 actor 做决定。"
            ),
            "writeback": (
                "本轮优先产出可供写回的 distilled memory / state delta，"
                "不要重复展开完整叙述。"
            ),
        }
        content = contract_by_profile.get(
            request.profile.name,
            "本轮输出应保持一步一决策，只推进当前最相关的一小步。",
        )
        return ContextPacket(
            kind="policy",
            section="output_contract",
            content=content,
            relevance_score=0.95,
        )

    def _build_tool_packet(
        self,
        request: ContextBuildRequest,
    ) -> ContextPacket | None:
        available_tools = request.metadata.get("available_tools", [])
        if not available_tools:
            return None

        lines = ["本轮可用工具如下："]
        for tool in available_tools:
            name = str(tool.get("name", "")).strip()
            if not name:
                continue
            description = str(tool.get("description", "")).strip()
            if description:
                lines.append(f"- {name}: {description}")
            else:
                lines.append(f"- {name}")

        lines.extend(
            [
                "如果当前场景或对方明确请求一个你可以通过工具正式完成的动作，应优先直接发起 tool call，"
                "不要只用台词假装工具结果已经产生。",
                "当你决定使用工具时，直接使用运行时提供的原生工具调用；不要把参数写成普通文本说明或伪 JSON。",
            ]
        )

        return ContextPacket(
            kind="policy",
            section="output_contract",
            content="\n".join(lines),
            relevance_score=0.96,
        )
