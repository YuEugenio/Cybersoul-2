"""Reflection mode that critiques and optionally refines another mode's output."""

from __future__ import annotations

import json
from typing import Any, Optional

from agents.core.base.mode import BaseMode
from agents.core.llm.schemas import LLMRequest, LLMResponse
from agents.core.messaging.event import AgentEvent
from agents.core.messaging.message import Message, MessageRole
from agents.core.messaging.mode_result import FinishReason, ModeResult


class ReflectionMode(BaseMode):
    """Wrap a base mode and improve its final response through reflection."""

    def __init__(
        self,
        name: str,
        llm_client,
        base_mode: BaseMode,
        reflection_prompt: str,
        refinement_prompt: str,
    ):
        super().__init__(name=name, llm_client=llm_client)
        self.base_mode = base_mode
        self.reflection_prompt = reflection_prompt
        self.refinement_prompt = refinement_prompt

    async def _run(
        self,
        event: AgentEvent,
        history: list[Message],
        **kwargs: Any,
    ) -> ModeResult:
        base_result = await self.base_mode.run(event=event, history=history, **kwargs)

        if base_result.finish_reason is not FinishReason.COMPLETED:
            return base_result

        draft_index, draft_message = self._find_reflectable_message(base_result.messages)
        if draft_message is None:
            return base_result

        question = self._extract_question(event)
        reflection, reflection_response = await self._reflect(
            question=question,
            draft=draft_message.content,
            base_result=base_result,
        )

        reflection_metadata: dict[str, Any] = {
            "base_mode_name": self.base_mode.name,
            "should_refine": reflection["should_refine"],
            "feedback": reflection["feedback"],
            "parsed": reflection["parsed"],
            "draft_message_index": draft_index,
            "reflection_response": self._response_metadata(reflection_response),
        }
        if reflection_response.message is not None:
            reflection_metadata["reflection_raw_response"] = (
                reflection_response.message.content
            )

        if not reflection["parsed"] or not reflection["should_refine"]:
            return self._copy_result(
                base_result,
                metadata=self._merged_metadata(base_result, reflection_metadata),
            )

        refined_message, refine_response = await self._refine(
            question=question,
            draft=draft_message.content,
            feedback=reflection["feedback"],
        )

        if refined_message is None:
            reflection_metadata["refinement_response"] = self._response_metadata(
                refine_response
            )
            reflection_metadata["refinement_raw_response"] = None
            reflection_metadata["refined"] = False
            return self._copy_result(
                base_result,
                metadata=self._merged_metadata(base_result, reflection_metadata),
            )

        reflection_metadata["refined"] = True
        reflection_metadata["refined_content"] = refined_message.content
        reflection_metadata["refinement_response"] = self._response_metadata(
            refine_response
        )
        reflection_metadata["refinement_raw_response"] = refined_message.content

        messages = list(base_result.messages)
        messages[draft_index] = self._build_refined_message(
            original=draft_message,
            refined_content=refined_message.content,
        )

        return ModeResult(
            finish_reason=base_result.finish_reason,
            messages=messages,
            effects=list(base_result.effects),
            summary="reflection mode refined base output",
            metadata=self._merged_metadata(base_result, reflection_metadata),
        )

    async def _reflect(
        self,
        *,
        question: str,
        draft: str,
        base_result: ModeResult,
    ) -> tuple[dict[str, Any], LLMResponse]:
        request = LLMRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content=self.reflection_prompt),
                Message(
                    role=MessageRole.USER,
                    content=self._build_reflection_input(
                        question=question,
                        draft=draft,
                        base_result=base_result,
                    ),
                ),
            ],
            max_tokens=1024,
        )
        response = await self._complete(request)

        if response.message is None:
            return {"parsed": False, "should_refine": False, "feedback": ""}, response

        return self._parse_reflection(response.message.content), response

    async def _refine(
        self,
        *,
        question: str,
        draft: str,
        feedback: str,
    ) -> tuple[Optional[Message], LLMResponse]:
        request = LLMRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content=self.refinement_prompt),
                Message(
                    role=MessageRole.USER,
                    content=self._build_refinement_input(
                        question=question,
                        draft=draft,
                        feedback=feedback,
                    ),
                ),
            ],
            max_tokens=1024,
        )
        response = await self._complete(request)
        return response.message, response

    def _find_reflectable_message(
        self,
        messages: list[Message],
    ) -> tuple[int, Optional[Message]]:
        for index in range(len(messages) - 1, -1, -1):
            if messages[index].role is MessageRole.ASSISTANT:
                return index, messages[index]
        return -1, None

    def _extract_question(self, event: AgentEvent) -> str:
        if event.message is None:
            return ""
        return event.message.content.strip()

    def _build_reflection_input(
        self,
        *,
        question: str,
        draft: str,
        base_result: ModeResult,
    ) -> str:
        return (
            "Review the draft response and decide whether it needs refinement.\n"
            "Return a JSON object only with this exact schema:\n"
            '{"should_refine": true, "feedback": "specific revision guidance"}\n'
            'If the draft is already good enough, return {"should_refine": false, "feedback": ""}.\n\n'
            f"Original task:\n{question or 'None'}\n\n"
            f"Draft response:\n{draft}\n\n"
            f"Base mode metadata:\n{json.dumps(base_result.metadata, ensure_ascii=False, default=str)}"
        )

    def _build_refinement_input(
        self,
        *,
        question: str,
        draft: str,
        feedback: str,
    ) -> str:
        return (
            "Revise the draft according to the feedback.\n"
            "Keep the answer aligned with the original task.\n"
            "Return only the revised final response text.\n\n"
            f"Original task:\n{question or 'None'}\n\n"
            f"Original draft:\n{draft}\n\n"
            f"Feedback:\n{feedback}"
        )

    def _parse_reflection(self, raw_content: str) -> dict[str, Any]:
        candidate = self._extract_json(raw_content.strip()) or raw_content.strip()

        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            return {"parsed": False, "should_refine": False, "feedback": ""}

        if not isinstance(parsed, dict):
            return {"parsed": False, "should_refine": False, "feedback": ""}

        feedback = parsed.get("feedback", "")
        if not isinstance(feedback, str):
            feedback = str(feedback)

        return {
            "parsed": True,
            "should_refine": bool(parsed.get("should_refine", False)),
            "feedback": feedback.strip(),
        }

    def _extract_json(self, text: str) -> str:
        if "```json" in text:
            return text.split("```json", 1)[1].split("```", 1)[0].strip()
        if "```" in text:
            parts = text.split("```")
            if len(parts) >= 3:
                return parts[1].strip()
        return ""

    def _build_refined_message(
        self,
        *,
        original: Message,
        refined_content: str,
    ) -> Message:
        metadata = dict(original.metadata)
        metadata["refined_from_message_id"] = original.id
        return Message(
            role=original.role,
            content=refined_content,
            name=original.name,
            metadata=metadata,
        )

    def _copy_result(
        self,
        base_result: ModeResult,
        *,
        metadata: dict[str, Any],
    ) -> ModeResult:
        return ModeResult(
            finish_reason=base_result.finish_reason,
            messages=list(base_result.messages),
            effects=list(base_result.effects),
            summary=base_result.summary,
            metadata=metadata,
        )

    def _merged_metadata(
        self,
        base_result: ModeResult,
        reflection_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        metadata = dict(base_result.metadata)
        metadata["reflection"] = reflection_metadata
        return metadata

    def _response_metadata(self, response: LLMResponse) -> dict[str, Any]:
        metadata: dict[str, Any] = {}

        if response.finish_reason is not None:
            metadata["llm_finish_reason"] = response.finish_reason
        if response.model is not None:
            metadata["llm_model"] = response.model
        if response.usage is not None:
            metadata["llm_usage"] = response.usage.model_dump(mode="json")
        if response.metadata:
            metadata["llm_response"] = response.metadata

        return metadata
