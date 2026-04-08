"""Composition-root utilities for wiring runnable Cybersoul instances."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CYBERSOUL_ROOT = PROJECT_ROOT / "cybersoul"

if str(CYBERSOUL_ROOT) not in sys.path:
    sys.path.insert(0, str(CYBERSOUL_ROOT))

__all__ = [
    "PROJECT_ROOT",
    "CYBERSOUL_ROOT",
]
