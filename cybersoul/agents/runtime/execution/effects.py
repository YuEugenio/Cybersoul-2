"""Runtime-side execution of mode effects into durable world state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from agents.core.messaging.mode_result import ModeEffect, ModeEffectType
from memory import ActorMemoryStore, MemoryRecord
from world.core.manager import WorldManager
from world.core.state import ActivityBlock, ActorState


@dataclass(slots=True)
class EffectExecutionRecord:
    """A debuggable record for one runtime effect execution attempt."""

    effect_type: str
    target: str | None
    status: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "effect_type": self.effect_type,
            "status": self.status,
        }
        if self.target is not None:
            payload["target"] = self.target
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass(slots=True)
class RuntimeExecutionReport:
    """Aggregate execution report returned after runtime side effects run."""

    records: list[EffectExecutionRecord] = field(default_factory=list)

    @property
    def applied_count(self) -> int:
        return sum(1 for record in self.records if record.status == "applied")

    @property
    def pending_count(self) -> int:
        return sum(1 for record in self.records if record.status == "pending")

    @property
    def error_count(self) -> int:
        return sum(1 for record in self.records if record.status == "error")

    def to_payload(self) -> dict[str, Any]:
        return {
            "records": [record.to_payload() for record in self.records],
            "applied_count": self.applied_count,
            "pending_count": self.pending_count,
            "error_count": self.error_count,
        }


class RuntimeEffectExecutor:
    """Apply supported runtime effects against the durable world manager."""

    def __init__(self, memory_store: ActorMemoryStore | None = None) -> None:
        self.memory_store = memory_store

    def execute(
        self,
        *,
        actor_id: str,
        effects: list[ModeEffect],
        world_manager: WorldManager,
        reference_time: datetime,
    ) -> RuntimeExecutionReport:
        records: list[EffectExecutionRecord] = []
        for effect in effects:
            if effect.type is ModeEffectType.PATCH_STATE:
                records.append(
                    self._apply_patch_state(
                        actor_id=actor_id,
                        effect=effect,
                        world_manager=world_manager,
                        reference_time=reference_time,
                    )
                )
                continue

            if effect.type is ModeEffectType.WRITE_MEMORY:
                records.append(
                    self._apply_write_memory(
                        actor_id=actor_id,
                        effect=effect,
                        world_manager=world_manager,
                        reference_time=reference_time,
                    )
                )
                continue

            records.append(
                EffectExecutionRecord(
                    effect_type=effect.type.value,
                    target=effect.target,
                    status="pending",
                    details={"reason": "unsupported_effect_type"},
                )
            )

        return RuntimeExecutionReport(records=records)

    def _apply_patch_state(
        self,
        *,
        actor_id: str,
        effect: ModeEffect,
        world_manager: WorldManager,
        reference_time: datetime,
    ) -> EffectExecutionRecord:
        target_actor_id = effect.target or actor_id
        payload = effect.payload
        existing_state = world_manager.get_actor_state(target_actor_id)
        current_place_id = payload.get("current_place_id")
        if not current_place_id and existing_state is not None:
            current_place_id = existing_state.current_place_id
        if not current_place_id:
            return EffectExecutionRecord(
                effect_type=effect.type.value,
                target=target_actor_id,
                status="error",
                details={"reason": "current_place_id_missing"},
            )

        clear_activity = bool(payload.get("clear_activity"))
        activity_patch = payload.get("activity")
        if clear_activity and activity_patch is not None:
            return EffectExecutionRecord(
                effect_type=effect.type.value,
                target=target_actor_id,
                status="error",
                details={"reason": "clear_activity_conflicts_with_activity_patch"},
            )

        try:
            if clear_activity:
                activity_block = None
            elif activity_patch is not None:
                activity_block = self._build_activity_block(
                    activity_patch=activity_patch,
                    world_manager=world_manager,
                    reference_time=reference_time,
                )
            elif existing_state is not None:
                activity_block = existing_state.current_activity_block
            else:
                activity_block = None

            next_state = ActorState(
                actor_id=target_actor_id,
                current_place_id=str(current_place_id),
                current_activity_block=activity_block,
            )
        except (TypeError, ValueError) as exc:
            return EffectExecutionRecord(
                effect_type=effect.type.value,
                target=target_actor_id,
                status="error",
                details={"reason": str(exc)},
            )

        world_manager.set_actor_state(next_state)

        patched_fields = []
        if "current_place_id" in payload:
            patched_fields.append("current_place_id")
        if clear_activity:
            patched_fields.append("current_activity_block")
        elif activity_patch is not None:
            patched_fields.append("current_activity_block")

        details: dict[str, Any] = {
            "current_place_id": next_state.current_place_id,
            "patched_fields": patched_fields,
        }
        if next_state.current_activity_block is not None:
            details["current_activity_type"] = next_state.current_activity_block.activity_type
            if next_state.current_activity_block.planned_until is not None:
                details["activity_planned_until"] = (
                    next_state.current_activity_block.planned_until.isoformat()
                )
        else:
            details["current_activity_type"] = None

        return EffectExecutionRecord(
            effect_type=effect.type.value,
            target=target_actor_id,
            status="applied",
            details=details,
        )

    def _apply_write_memory(
        self,
        *,
        actor_id: str,
        effect: ModeEffect,
        world_manager: WorldManager,
        reference_time: datetime,
    ) -> EffectExecutionRecord:
        if self.memory_store is None:
            return EffectExecutionRecord(
                effect_type=effect.type.value,
                target=effect.target or actor_id,
                status="pending",
                details={"reason": "memory_store_not_configured"},
            )

        target_actor_id = effect.target or actor_id
        payload = effect.payload
        content = str(payload.get("content", "")).strip()
        if not content:
            return EffectExecutionRecord(
                effect_type=effect.type.value,
                target=target_actor_id,
                status="error",
                details={"reason": "memory.content is required"},
            )

        importance_raw = payload.get("importance", 0.6)
        try:
            importance = max(0.0, min(1.0, float(importance_raw)))
        except (TypeError, ValueError):
            return EffectExecutionRecord(
                effect_type=effect.type.value,
                target=target_actor_id,
                status="error",
                details={"reason": "memory.importance must be numeric"},
            )

        actor_state = world_manager.get_actor_state(target_actor_id)
        place_id = payload.get("place_id")
        if not place_id and actor_state is not None:
            place_id = actor_state.current_place_id

        try:
            created_at = self._coerce_datetime(
                value=payload.get("created_at"),
                world_manager=world_manager,
                default=reference_time,
            )
        except ValueError as exc:
            return EffectExecutionRecord(
                effect_type=effect.type.value,
                target=target_actor_id,
                status="error",
                details={"reason": str(exc)},
            )

        tags = payload.get("tags", [])
        if tags is None:
            tags = []
        if not isinstance(tags, list):
            return EffectExecutionRecord(
                effect_type=effect.type.value,
                target=target_actor_id,
                status="error",
                details={"reason": "memory.tags must be a list"},
            )

        record = MemoryRecord(
            actor_id=target_actor_id,
            memory_type=str(payload.get("memory_type", "episodic")),
            content=content,
            summary=str(payload["summary"]).strip() if payload.get("summary") else None,
            importance=importance,
            counterpart_id=(
                str(payload["counterpart_id"]).strip()
                if payload.get("counterpart_id")
                else None
            ),
            place_id=str(place_id).strip() if place_id else None,
            tags=[str(tag).strip() for tag in tags if str(tag).strip()],
            created_at=created_at,
            metadata=dict(payload.get("metadata", {})) if isinstance(payload.get("metadata", {}), dict) else {},
        )
        self.memory_store.add(record)

        return EffectExecutionRecord(
            effect_type=effect.type.value,
            target=target_actor_id,
            status="applied",
            details={
                "memory_id": record.id,
                "memory_type": record.memory_type,
                "counterpart_id": record.counterpart_id,
                "place_id": record.place_id,
                "importance": record.importance,
            },
        )

    def _build_activity_block(
        self,
        *,
        activity_patch: Any,
        world_manager: WorldManager,
        reference_time: datetime,
    ) -> ActivityBlock:
        if not isinstance(activity_patch, dict):
            raise ValueError("activity patch must be an object")

        activity_type = str(activity_patch.get("activity_type", "")).strip()
        if not activity_type:
            raise ValueError("activity.activity_type is required")

        started_at = self._coerce_datetime(
            value=activity_patch.get("started_at"),
            world_manager=world_manager,
            default=reference_time,
        )

        planned_until = None
        if activity_patch.get("planned_until") is not None:
            planned_until = self._coerce_datetime(
                value=activity_patch.get("planned_until"),
                world_manager=world_manager,
            )
        elif activity_patch.get("planned_duration_minutes") is not None:
            planned_duration_minutes = float(activity_patch["planned_duration_minutes"])
            if planned_duration_minutes < 0:
                raise ValueError("activity.planned_duration_minutes must be >= 0")
            planned_until = started_at + timedelta(minutes=planned_duration_minutes)

        raw_payload = activity_patch.get("payload", {})
        if raw_payload is None:
            raw_payload = {}
        if not isinstance(raw_payload, dict):
            raise ValueError("activity.payload must be an object")

        return ActivityBlock(
            activity_type=activity_type,
            started_at=started_at,
            planned_until=planned_until,
            payload=raw_payload,
        )

    def _coerce_datetime(
        self,
        *,
        value: Any,
        world_manager: WorldManager,
        default: datetime | None = None,
    ) -> datetime:
        if value is None:
            if default is None:
                raise ValueError("datetime value is required")
            return world_manager.clock.ensure_aware(default)

        if isinstance(value, datetime):
            return world_manager.clock.ensure_aware(value)
        if isinstance(value, str):
            return world_manager.clock.ensure_aware(datetime.fromisoformat(value))

        raise ValueError("datetime must be an ISO string or datetime object")
