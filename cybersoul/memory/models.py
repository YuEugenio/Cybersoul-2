"""Minimal actor-centric memory records for Runtime MVP."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _memory_id() -> str:
    return f"mem_{uuid4().hex}"


class MemoryRecord(BaseModel):
    """A distilled memory item that can be written back and reused later."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(default_factory=_memory_id)
    actor_id: str = Field(min_length=1)
    memory_type: str = Field(default="episodic", min_length=1)
    content: str = Field(min_length=1)
    summary: str | None = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    counterpart_id: str | None = None
    place_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("memory_type")
    @classmethod
    def normalize_memory_type(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "_")

    @property
    def preview_text(self) -> str:
        return (self.summary or self.content).strip()
