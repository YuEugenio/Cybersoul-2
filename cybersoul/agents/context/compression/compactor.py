"""Token-budget compaction for selected context packets."""

from __future__ import annotations

from agents.context.packets import ContextPacket


class TokenBudgetCompactor:
    """Keep the highest-priority packets that fit within the token budget."""

    def compact(
        self,
        packets: list[ContextPacket],
        max_tokens: int,
    ) -> tuple[list[ContextPacket], list[ContextPacket]]:
        selected: list[ContextPacket] = []
        truncated: list[ContextPacket] = []
        total_tokens = 0

        for packet in packets:
            next_total = total_tokens + packet.token_count
            if selected and next_total > max_tokens:
                truncated.append(packet)
                continue
            selected.append(packet)
            total_tokens = next_total

        return selected, truncated
