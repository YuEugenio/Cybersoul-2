"""Lightweight memory storage for Runtime MVP."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from memory.models import MemoryRecord


class ActorMemoryStore:
    """A small actor-centric memory store with optional JSON persistence."""

    def __init__(self, store_path: str | Path | None = None) -> None:
        self.store_path = Path(store_path).resolve() if store_path is not None else None
        self._records: list[MemoryRecord] = []
        if self.store_path is not None:
            self._load()

    def add(self, record: MemoryRecord) -> MemoryRecord:
        self._records.append(record)
        self._records.sort(key=lambda item: item.created_at, reverse=True)
        self._persist()
        return record

    def list_recent(
        self,
        *,
        actor_id: str,
        limit: int = 4,
        memory_types: Iterable[str] | None = None,
        counterpart_ids: Iterable[str] | None = None,
        place_id: str | None = None,
    ) -> list[MemoryRecord]:
        normalized_types = {
            memory_type.strip().lower().replace(" ", "_")
            for memory_type in (memory_types or [])
            if str(memory_type).strip()
        }
        normalized_counterparts = {
            counterpart_id.strip()
            for counterpart_id in (counterpart_ids or [])
            if str(counterpart_id).strip()
        }

        filtered = [
            record
            for record in self._records
            if record.actor_id == actor_id
            and (
                not normalized_types
                or record.memory_type in normalized_types
            )
        ]
        if not filtered:
            return []

        def score(record: MemoryRecord) -> tuple[float, float]:
            score_value = record.importance
            if place_id and record.place_id == place_id:
                score_value += 0.35
            if normalized_counterparts and record.counterpart_id in normalized_counterparts:
                score_value += 0.45

            age_hours = max(
                0.0,
                (self._reference_now() - record.created_at.astimezone(timezone.utc)).total_seconds()
                / 3600.0,
            )
            recency_score = 1.0 / (1.0 + age_hours)
            return (score_value + 0.35 * recency_score, record.created_at.timestamp())

        ranked = sorted(filtered, key=score, reverse=True)
        return ranked[: max(1, limit)]

    def __len__(self) -> int:
        return len(self._records)

    def _load(self) -> None:
        if self.store_path is None or not self.store_path.exists():
            return

        raw_items = json.loads(self.store_path.read_text(encoding="utf-8"))
        self._records = [MemoryRecord.model_validate(item) for item in raw_items]
        self._records.sort(key=lambda item: item.created_at, reverse=True)

    def _persist(self) -> None:
        if self.store_path is None:
            return

        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [record.model_dump(mode="json") for record in self._records]
        self.store_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _reference_now(self) -> datetime:
        return datetime.now(timezone.utc)
