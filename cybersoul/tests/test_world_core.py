"""Tests for the minimal generic world runtime."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest import TestCase

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
CYBERSOUL_ROOT = PROJECT_ROOT / "cybersoul"
if str(CYBERSOUL_ROOT) not in sys.path:
    sys.path.insert(0, str(CYBERSOUL_ROOT))

from world.core.clock import WorldClock
from world.core.manager import WorldManager
from world.core.state import ActivityBlock, ActorState, WorldState


class WorldClockTests(TestCase):
    def test_clock_emits_timezone_aware_iso_time(self) -> None:
        clock = WorldClock(timezone_name="Asia/Shanghai")

        now = clock.now()
        iso_text = clock.to_iso(now)

        self.assertIsNotNone(now.tzinfo)
        self.assertTrue(iso_text.endswith("+08:00"))


class WorldManagerTests(TestCase):
    def test_manager_tracks_minimal_actor_state(self) -> None:
        clock = WorldClock(timezone_name="Asia/Shanghai")
        started_at = clock.now()
        manager = WorldManager(
            clock=clock,
            initial_state=WorldState(current_time=started_at),
        )
        activity_block = ActivityBlock(
            activity_type="reading",
            started_at=started_at,
            planned_until=started_at + timedelta(minutes=30),
            payload={"topic": "旧信"},
        )
        actor_state = ActorState(
            actor_id="cyrene",
            current_place_id="lin_ting",
            current_activity_block=activity_block,
        )

        manager.set_actor_state(actor_state)
        snapshot = manager.snapshot()

        self.assertEqual(snapshot.get_actor_state("cyrene").current_place_id, "lin_ting")
        self.assertEqual(
            snapshot.get_actor_state("cyrene").current_activity_block.activity_type,
            "reading",
        )

    def test_activity_block_rejects_invalid_timeline(self) -> None:
        started_at = datetime(2026, 3, 21, 12, 0, 0)

        with self.assertRaises(ValueError):
            ActivityBlock(
                activity_type="walking",
                started_at=started_at,
                planned_until=started_at - timedelta(minutes=5),
            )
