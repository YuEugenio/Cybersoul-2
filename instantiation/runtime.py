"""Compatibility wrapper for the default instance-backed companion runtime."""

from instantiation.amphoreus.runtime import (
    build_cyrene_companion_runtime,
    build_cyrene_heartbeat_runner,
)

__all__ = [
    "build_cyrene_companion_runtime",
    "build_cyrene_heartbeat_runner",
]
