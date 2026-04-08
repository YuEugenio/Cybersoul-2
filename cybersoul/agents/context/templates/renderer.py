"""Render selected context packets into a stable sectioned prompt block."""

from __future__ import annotations

from collections import defaultdict

from agents.context.packets import ContextPacket

SECTION_TITLES = (
    ("role_policies", "[Role & Policies]"),
    ("trigger", "[Trigger]"),
    ("state", "[State]"),
    ("evidence", "[Evidence]"),
    ("memory", "[Memory]"),
    ("context", "[Context]"),
    ("output_contract", "[Output Contract]"),
)


class ContextTemplateRenderer:
    """Render packets into a stable, debuggable prompt skeleton."""

    def render(self, packets: list[ContextPacket]) -> str:
        grouped: dict[str, list[str]] = defaultdict(list)
        for packet in packets:
            if packet.content.strip():
                grouped[packet.section].append(packet.content.strip())

        sections: list[str] = []
        for section_key, section_title in SECTION_TITLES:
            entries = grouped.get(section_key)
            if not entries:
                continue
            sections.append(section_title + "\n" + "\n\n".join(entries))

        return "\n\n".join(sections).strip()
