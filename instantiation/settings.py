"""Runtime settings used by the composition layer."""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_OPENAI_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_LLM_MODEL_ID = "qwen3.5-flash-2026-02-23"


class RuntimeLLMSettings(BaseModel):
    """Environment-backed settings for the current LLM runtime."""

    model_config = ConfigDict(str_strip_whitespace=True)

    api_key: str = Field(min_length=1)
    base_url: str = Field(default=DEFAULT_OPENAI_BASE_URL, min_length=1)
    model_id: str = Field(default=DEFAULT_LLM_MODEL_ID, min_length=1)
    timeout_seconds: float = Field(default=60.0, gt=0)

    @classmethod
    def from_env(cls) -> "RuntimeLLMSettings":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required to instantiate the Cybersoul companion runtime."
            )

        base_url = os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).strip()
        model_id = os.getenv("LLM_MODEL_ID", DEFAULT_LLM_MODEL_ID).strip()
        timeout_raw = os.getenv("LLM_TIMEOUT_SECONDS", "60").strip() or "60"

        return cls(
            api_key=api_key,
            base_url=base_url,
            model_id=model_id,
            timeout_seconds=float(timeout_raw),
        )
