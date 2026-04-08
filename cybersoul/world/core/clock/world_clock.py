"""Minimal world clock that only emits a timezone-aware current time."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


class WorldClock:
    """Provide the current world time as a timezone-aware datetime."""

    def __init__(self, timezone_name: str = "Asia/Shanghai") -> None:
        self.timezone_name = timezone_name
        self._timezone = ZoneInfo(timezone_name)

    def now(self) -> datetime:
        """Return the current world time."""

        return datetime.now(self._timezone)

    def ensure_aware(self, value: datetime) -> datetime:
        """Normalize datetimes into the world clock timezone."""

        if value.tzinfo is None:
            return value.replace(tzinfo=self._timezone)
        return value.astimezone(self._timezone)

    def to_iso(self, value: datetime | None = None) -> str:
        """Serialize a world time as ISO 8601."""

        return self.ensure_aware(value or self.now()).isoformat()
