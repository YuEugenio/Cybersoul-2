"""Plan-and-solve mode for structured multi-step execution."""

from __future__ import annotations

import json
from typing import Any, Optional

from agents.core.base.mode import BaseMode
from agents.core.llm.schemas import LLMRequest, LLMResponse, LLMToolCall
from agents.core.messaging.event import AgentEvent
from agents.core.messaging.message import Message, MessageRole
from agents.core.messaging.mode_result import FinishReason, ModeResult
from agents.tools.registry.registry import ToolRegistry


class PlanSolveMode(BaseMode):
    """Two-stage mode that plans first and then executes each step."""

    def __init__(
        self,
        name: str,
        llm_client,
        planner_prompt: str,
        executor_prompt: str,
        tool_registry: ToolRegistry,
        max_plan_steps: int = 8,
        max_step_rounds: int = 5,
    ):
        super().__init__(name=name, llm_client=llm_client)
        self.planner_prompt = planner_prompt
        self.executor_prompt = executor_prompt
        self.tool_registry = tool_registry
        self.max_plan_steps = max_plan_steps
        self.max_step_rounds = max_step_rounds

    async def _run(
        self,
        event: AgentEvent,
        history: list[Message],
        **kwargs: Any,
    ) -> ModeResult:
        question = self._extract_question(event)
        if not question:
            return ModeResult.noop(summary="plan_solve mode received no question")

        plan, planner_response = await self._generate_plan(
            question=question,
            history=history,
        )

        if not plan:
            return ModeResult(
                finish_reason=FinishReason.ERROR,
                summary="plan_solve mode failed to generate a valid plan",
                metadata={
                    "failed_stage": "planning",
                    "question": question,
                    "planner_raw_response": planner_response.message.content
                    if planner_response.message is not None
                    else None,
                    "planner_response": self._response_metadata(planner_response),
                },
            )

        final_answer, step_results, execution_error = await self._execute_plan(
            question=question,
            plan=plan,
            history=history,
        )

        metadata: dict[str, Any] = {
            "question": question,
            "plan": plan,
            "plan_steps_count": len(plan),
            "step_results": step_results,
            "planner_raw_response": planner_response.message.content
            if planner_response.message is not None
            else None,
            "planner_response": self._response_metadata(planner_response),
        }

        if execution_error is not None:
            metadata.update(execution_error)
            return ModeResult(
                finish_reason=FinishReason.ERROR,
                summary="plan_solve mode failed during execution",
                metadata=metadata,
            )

        if not final_answer:
            return ModeResult(
                finish_reason=FinishReason.ERROR,
                summary="plan_solve mode finished without a final answer",
                metadata=metadata,
            )

        return ModeResult(
            finish_reason=FinishReason.COMPLETED,
            messages=[Message(role=MessageRole.ASSISTANT, content=final_answer)],
            summary="plan_solve mode executed the full plan",
            metadata=metadata,
        )

    async def _generate_plan(
        self,
        *,
        question: str,
        history: list[Message],
    ) -> tuple[list[str], LLMResponse]:
        request = LLMRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content=self.planner_prompt),
                *history,
                Message(
                    role=MessageRole.USER,
                    content=self._build_planner_input(question),
                ),
            ],
            max_tokens=1024,
        )
        response = await self._complete(request)

        if response.message is None:
            return [], response

        plan = self._parse_plan(response.message.content)
        if self.max_plan_steps > 0:
            plan = plan[: self.max_plan_steps]

        return plan, response

    async def _execute_plan(
        self,
        *,
        question: str,
        plan: list[str],
        history: list[Message],
    ) -> tuple[Optional[str], list[dict[str, Any]], Optional[dict[str, Any]]]:
        step_results: list[dict[str, Any]] = []
        final_answer: Optional[str] = None

        for index, step in enumerate(plan):
            step_result, step_error = await self._execute_step(
                question=question,
                plan=plan,
                step_index=index,
                step=step,
                history=history,
                completed_steps=step_results,
            )

            if step_error is not None:
                return None, step_results, step_error

            step_results.append(step_result)
            final_answer = step_result["result"]

        return final_answer, step_results, None

    async def _execute_step(
        self,
        *,
        question: str,
        plan: list[str],
        step_index: int,
        step: str,
        history: list[Message],
        completed_steps: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
        working_messages = [
            Message(role=MessageRole.SYSTEM, content=self.executor_prompt),
            *history,
            Message(
                role=MessageRole.USER,
                content=self._build_executor_input(
                    question=question,
                    plan=plan,
                    completed_steps=completed_steps,
                    current_step=step,
                ),
            ),
        ]

        tool_traces: list[dict[str, Any]] = []

        for round_index in range(self.max_step_rounds):
            response = await self._complete(
                LLMRequest(
                    messages=working_messages,
                    tools=self.tool_registry.to_llm_specs(),
                )
            )

            if response.tool_calls:
                tool_messages = await self._execute_tool_calls(response.tool_calls)
                working_messages.extend(tool_messages)
                tool_traces.extend(self._tool_trace_entries(response.tool_calls))
                continue

            if response.message is not None:
                return (
                    {
                        "index": step_index + 1,
                        "step": step,
                        "result": response.message.content,
                        "rounds": round_index + 1,
                        "tool_calls": tool_traces,
                        "response": self._response_metadata(response),
                    },
                    None,
                )

            return (
                {},
                {
                    "failed_stage": "execution",
                    "failed_step_index": step_index,
                    "failed_step": step,
                    "reason": "executor returned neither tool calls nor a message",
                    "executor_response": self._response_metadata(response),
                },
            )

        return (
            {},
            {
                "failed_stage": "execution",
                "failed_step_index": step_index,
                "failed_step": step,
                "reason": "executor reached max_step_rounds",
                "max_step_rounds": self.max_step_rounds,
            },
        )

    async def _execute_tool_calls(
        self,
        tool_calls: list[LLMToolCall],
    ) -> list[Message]:
        tool_messages: list[Message] = []

        for tool_call in tool_calls:
            result = await self.tool_registry.execute_tool(
                name=tool_call.name,
                arguments=tool_call.arguments,
            )
            tool_messages.append(
                Message(
                    role=MessageRole.TOOL,
                    content=result.content,
                    name=tool_call.name,
                    tool_call_id=tool_call.id,
                    metadata={
                        "data": result.data,
                        "tool_metadata": result.metadata,
                    },
                )
            )

        return tool_messages

    def _extract_question(self, event: AgentEvent) -> str:
        if event.message is None:
            return ""
        return event.message.content.strip()

    def _build_planner_input(self, question: str) -> str:
        return (
            "You are in the planning stage.\n"
            "Generate an ordered execution plan for the task below.\n"
            "Return JSON array only, with each item being one executable step.\n\n"
            f"Task:\n{question}"
        )

    def _build_executor_input(
        self,
        *,
        question: str,
        plan: list[str],
        completed_steps: list[dict[str, Any]],
        current_step: str,
    ) -> str:
        return (
            "You are in the execution stage.\n"
            "Strictly complete the current step while staying aligned with the plan.\n"
            "You may call tools only when they help finish the current step.\n"
            "When the current step is complete, return only the step result.\n\n"
            f"Original task:\n{question}\n\n"
            f"Complete plan:\n{json.dumps(plan, ensure_ascii=False, indent=2)}\n\n"
            f"Completed steps:\n{self._serialize_completed_steps(completed_steps)}\n\n"
            f"Current step:\n{current_step}"
        )

    def _parse_plan(self, raw_content: str) -> list[str]:
        text = raw_content.strip()
        if not text:
            return []

        fenced_text = self._extract_json_fence(text)
        candidate = fenced_text or text

        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            return []

        if not isinstance(parsed, list):
            return []

        plan: list[str] = []
        for item in parsed:
            if not isinstance(item, str):
                continue
            normalized = item.strip()
            if normalized:
                plan.append(normalized)

        return plan

    def _extract_json_fence(self, text: str) -> str:
        if "```json" in text:
            return text.split("```json", 1)[1].split("```", 1)[0].strip()
        if "```" in text:
            parts = text.split("```")
            if len(parts) >= 3:
                return parts[1].strip()
        return ""

    def _serialize_completed_steps(
        self,
        completed_steps: list[dict[str, Any]],
    ) -> str:
        if not completed_steps:
            return "None"

        lines: list[str] = []
        for item in completed_steps:
            lines.append(
                f"Step {item['index']}: {item['step']}\nResult: {item['result']}"
            )
        return "\n\n".join(lines)

    def _tool_trace_entries(
        self,
        tool_calls: list[LLMToolCall],
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": tool_call.id,
                "name": tool_call.name,
                "arguments": tool_call.arguments,
            }
            for tool_call in tool_calls
        ]

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
