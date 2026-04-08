"""Profile models for concrete companion agents."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CompanionProfile(BaseModel):
    """Structured profile that anchors a concrete companion persona."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(min_length=1)
    companion_name: str = Field(min_length=1)
    persona_path: str = Field(min_length=1)
    default_mode: str = Field(min_length=1)
    enabled_tools: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "companion_name": self.companion_name,
            "persona_path": self.persona_path,
            "default_mode": self.default_mode,
            "enabled_tools": list(self.enabled_tools),
        }

        if self.metadata:
            payload["metadata"] = self.metadata

        return payload
