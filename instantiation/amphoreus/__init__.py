"""Concrete Amphoreus instance package for the Cybersoul framework."""

from __future__ import annotations

from pathlib import Path

INSTANCE_ID = "amphoreus"
INSTANCE_ROOT = Path(__file__).resolve().parent
PROMPTS_ROOT = INSTANCE_ROOT / "prompts"

__all__ = [
    "INSTANCE_ID",
    "INSTANCE_ROOT",
    "PROMPTS_ROOT",
]
