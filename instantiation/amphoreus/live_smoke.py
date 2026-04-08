"""Manual live-smoke harnesses for real LLM validation in Amphoreus."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import TextIO
from typing import Any

from memory import ActorMemoryStore
from world.core.clock import WorldClock
from world.core.manager import WorldManager
from world.core.state import ActivityBlock, ActorState, WorldState

from instantiation.amphoreus.scene_activation import SceneActivationOrchestrator
from instantiation.llm import build_llm_client
from instantiation.runtime import (
    build_cyrene_companion_runtime,
    build_cyrene_heartbeat_runner,
)


SCRIPT_DIR = Path(__file__).resolve().parent


class OutputMirror:
    """Mirror smoke output to both stdout and a persisted text log."""

    def __init__(self, log_path: Path | None = None) -> None:
        self.log_path = log_path
        self._file: TextIO | None = None
        if log_path is not None:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._file = log_path.open("w", encoding="utf-8")

    def emit_line(self, line: str = "") -> None:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
        if self._file is not None:
            self._file.write(line + "\n")
            self._file.flush()

    def emit_block(self, text: str) -> None:
        if not text:
            self.emit_line()
            return
        for line in text.splitlines():
            self.emit_line(line)

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None


def build_scene_world_manager() -> WorldManager:
    """Create a stable observatory scene for manual live verification."""

    clock = WorldClock(timezone_name="Asia/Shanghai")
    started_at = clock.now()
    world_manager = WorldManager(
        clock=clock,
        initial_state=WorldState(current_time=started_at),
    )
    world_manager.set_actor_state(
        ActorState(
            actor_id="cyrene",
            current_place_id="temple_and_observatory",
            current_activity_block=ActivityBlock(
                activity_type="visiting",
                started_at=started_at,
                planned_until=started_at + timedelta(minutes=20),
            ),
        )
    )
    world_manager.set_actor_state(
        ActorState(
            actor_id="tribbie",
            current_place_id="temple_and_observatory",
            current_activity_block=ActivityBlock(
                activity_type="watching_stars",
                started_at=started_at,
                planned_until=started_at + timedelta(minutes=20),
            ),
        )
    )
    return world_manager


def run_heartbeat_scene_smoke() -> dict[str, Any]:
    """Run one real heartbeat tick followed by the scene loop."""

    llm_client = build_llm_client()
    memory_store = ActorMemoryStore()
    world_manager = build_scene_world_manager()
    runner = build_cyrene_heartbeat_runner(
        llm_client=llm_client,
        world_manager=world_manager,
        memory_store=memory_store,
    )
    record = runner.run_tick()
    return {
        "scenario": "heartbeat_scene",
        "tick_index": record.tick_index,
        "actor_place_id": record.actor_place_id,
        "cyrene_result": _mode_result_payload(record.cyrene_result),
        "scene_turns": [_scene_turn_payload(turn) for turn in record.scene_turns],
    }


def run_tribbie_divination_smoke(
    *,
    scene_turn_limit: int = 6,
    initiating_content: str = "昔涟轻声问：缇宝，要不要替我占一卦？",
) -> dict[str, Any]:
    """Run a scene session that explicitly asks Tribbie for divination."""

    llm_client = build_llm_client()
    memory_store = ActorMemoryStore()
    world_manager = build_scene_world_manager()
    protagonist_runtime = build_cyrene_companion_runtime(
        llm_client=llm_client,
        world_manager=world_manager,
        memory_store=memory_store,
    )
    orchestrator = SceneActivationOrchestrator(
        world_manager=world_manager,
        memory_store=memory_store,
        llm_client=llm_client,
        scene_turn_limit=scene_turn_limit,
    )
    turns = orchestrator.activate_for_actor(
        actor_id="cyrene",
        scene_id="temple_and_observatory",
        initiating_content=initiating_content,
        intent="scene_enter",
        causal_ref="live_smoke_divination",
        protagonist_runtime=protagonist_runtime,
    )
    return {
        "scenario": "tribbie_divination",
        "scene_turns": [_scene_turn_payload(turn) for turn in turns],
    }


def _scene_turn_payload(turn) -> dict[str, Any]:
    return {
        "target_agent_id": turn.target_agent_id,
        "from_agent": turn.envelope.from_agent,
        "to_agent": turn.envelope.to_agent,
        "intent": turn.envelope.intent,
        "content": turn.envelope.content,
        "result": _mode_result_payload(turn.result),
    }


def _mode_result_payload(result) -> dict[str, Any]:
    runtime_payload = _runtime_payload(result.metadata.get("runtime", {}))
    return {
        "finish_reason": result.finish_reason.value,
        "summary": result.summary,
        "messages": [
            {
                "role": message.role.value,
                "content": message.content,
            }
            for message in result.messages
        ],
        "tool_trace": result.metadata.get("tool_trace", []),
        "react_trace": result.metadata.get("react_trace", []),
        "runtime": runtime_payload,
    }


def _runtime_payload(runtime: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(runtime, dict):
        return {}

    handoff = runtime.get("handoff_summary", {})
    trimmed_handoff = {}
    if isinstance(handoff, dict):
        trimmed_handoff = {
            "actor_id": handoff.get("actor_id"),
            "profile_name": handoff.get("profile_name"),
            "created_at": handoff.get("created_at"),
            "current_time": handoff.get("current_time"),
            "current_place_id": handoff.get("current_place_id"),
            "current_activity_type": handoff.get("current_activity_type"),
            "finish_reason": handoff.get("finish_reason"),
            "latest_assistant_message": handoff.get("latest_assistant_message"),
            "metadata": handoff.get("metadata", {}),
        }

    return {
        "actor_id": runtime.get("actor_id"),
        "context_profile": runtime.get("context_profile"),
        "selected_packet_count": runtime.get("selected_packet_count"),
        "truncated_packet_count": runtime.get("truncated_packet_count"),
        "context_token_estimate": runtime.get("context_token_estimate"),
        "available_tools": runtime.get("available_tools", []),
        "agent_profile": runtime.get("agent_profile"),
        "event_trace": runtime.get("event_trace"),
        "context_trace": runtime.get("context_trace", {}),
        "effect_execution": runtime.get("effect_execution", {}),
        "handoff_summary": trimmed_handoff,
        "clean_state": runtime.get("clean_state", {}),
    }


def render_pretty_payload(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    prompt_cache: dict[str, str] = {}
    scenario = str(payload.get("scenario", "unknown"))
    lines.append(f"=== Amphoreus Live Smoke :: {scenario} ===")

    if scenario == "heartbeat_scene":
        lines.append(f"tick_index: {payload.get('tick_index')}")
        lines.append(f"actor_place_id: {payload.get('actor_place_id')}")
        lines.append("")
        lines.extend(
            _render_mode_result(
                title="Heartbeat Turn / Cyrene",
                result=payload.get("cyrene_result", {}),
                prompt_cache=prompt_cache,
            )
        )
    else:
        lines.append(f"scene_turn_count: {len(payload.get('scene_turns', []))}")

    scene_turns = payload.get("scene_turns", [])
    if scene_turns:
        lines.append("")
        lines.append("=== Scene Turns ===")
        for index, turn in enumerate(scene_turns, start=1):
            lines.append("")
            lines.extend(_render_scene_turn(index=index, turn=turn, prompt_cache=prompt_cache))

    return "\n".join(lines).strip()


def _render_scene_turn(
    *,
    index: int,
    turn: dict[str, Any],
    prompt_cache: dict[str, str],
) -> list[str]:
    result = turn.get("result", {})
    title = (
        f"Turn {index} :: {turn.get('from_agent')} -> {turn.get('to_agent')} "
        f"[intent={turn.get('intent')}]"
    )
    lines = [title]
    content = str(turn.get("content", "")).strip()
    if content:
        lines.append("Incoming Scene Message:")
        lines.append(_indent_block(content))
    lines.extend(
        _render_mode_result(
            title="Turn Result",
            result=result,
            prompt_cache=prompt_cache,
        )
    )
    return lines


def _render_mode_result(
    *,
    title: str,
    result: dict[str, Any],
    prompt_cache: dict[str, str],
) -> list[str]:
    lines = [title]
    runtime = result.get("runtime", {})
    actor_id = str(runtime.get("actor_id") or "unknown")
    lines.append(
        "Summary: "
        f"actor={actor_id}, profile={runtime.get('context_profile')}, "
        f"finish_reason={result.get('finish_reason')}, summary={result.get('summary')}"
    )

    available_tools = runtime.get("available_tools", [])
    if available_tools:
        lines.append("Available Tools:")
        for tool in available_tools:
            name = tool.get("name")
            description = tool.get("description")
            lines.append(f"  - {name}: {description}")
    else:
        lines.append("Available Tools: none")

    event_trace = runtime.get("event_trace")
    if event_trace:
        lines.append("Event Trace:")
        lines.append(
            _indent_block(
                json.dumps(event_trace, ensure_ascii=False, indent=2)
            )
        )

    context_trace = runtime.get("context_trace", {})
    base_system_prompt = str(context_trace.get("base_system_prompt", "")).strip()
    runtime_context_text = str(context_trace.get("runtime_context_text", "")).strip()
    lines.extend(
        _render_context_trace(
            actor_id=actor_id,
            runtime=runtime,
            context_trace=context_trace,
            base_system_prompt=base_system_prompt,
            runtime_context_text=runtime_context_text,
            prompt_cache=prompt_cache,
        )
    )

    react_trace = result.get("react_trace", [])
    if react_trace:
        lines.append("ReAct Trace:")
        for step in react_trace:
            lines.extend(
                _render_react_step(
                    step=step,
                    base_system_prompt=base_system_prompt,
                    runtime_context_text=runtime_context_text,
                )
            )
    else:
        lines.append("ReAct Trace: none")

    messages = result.get("messages", [])
    if messages:
        lines.append("Final Assistant Messages:")
        for index, message in enumerate(messages, start=1):
            lines.append(
                f"  [{index}] role={message.get('role')}"
            )
            lines.append(_indent_block(str(message.get("content", "")), prefix="    "))

    tool_trace = result.get("tool_trace", [])
    if tool_trace:
        lines.append("Tool Trace Summary:")
        for index, trace in enumerate(tool_trace, start=1):
            lines.append(
                f"  [{index}] {trace.get('tool_name')} args="
                f"{json.dumps(trace.get('arguments', {}), ensure_ascii=False)}"
            )
            lines.append(_indent_block(str(trace.get("content", "")), prefix="    "))

    effect_execution = runtime.get("effect_execution", {})
    lines.append(
        "Effects: "
        f"applied={effect_execution.get('applied_count', 0)}, "
        f"pending={effect_execution.get('pending_count', 0)}, "
        f"errors={effect_execution.get('error_count', 0)}"
    )

    handoff = runtime.get("handoff_summary", {})
    if handoff:
        lines.append("Handoff Summary:")
        lines.append(
            _indent_block(
                json.dumps(handoff, ensure_ascii=False, indent=2)
            )
        )

    return lines


def _render_context_trace(
    *,
    actor_id: str,
    runtime: dict[str, Any],
    context_trace: dict[str, Any],
    base_system_prompt: str,
    runtime_context_text: str,
    prompt_cache: dict[str, str],
) -> list[str]:
    lines = [
        "Context Assembly:",
        (
            "  selected_packets="
            f"{runtime.get('selected_packet_count', 0)}, "
            f"truncated_packets={runtime.get('truncated_packet_count', 0)}, "
            f"token_estimate={runtime.get('context_token_estimate', 0)}"
        ),
    ]

    selected_packets = context_trace.get("selected_packets", [])
    if selected_packets:
        lines.append("  Selected Packets:")
        for packet in selected_packets:
            header = (
                f"    - {packet.get('kind')}/{packet.get('section')} "
                f"(tokens={packet.get('token_count')}, "
                f"relevance={packet.get('relevance_score')})"
            )
            lines.append(header)
            lines.append(_indent_block(str(packet.get("content", "")), prefix="      "))

    truncated_packets = context_trace.get("truncated_packets", [])
    if truncated_packets:
        lines.append("  Truncated Packets:")
        for packet in truncated_packets:
            header = (
                f"    - {packet.get('kind')}/{packet.get('section')} "
                f"(tokens={packet.get('token_count')}, "
                f"relevance={packet.get('relevance_score')})"
            )
            lines.append(header)
            lines.append(_indent_block(str(packet.get("content", "")), prefix="      "))

    if base_system_prompt:
        previous_prompt = prompt_cache.get(actor_id)
        if previous_prompt == base_system_prompt:
            lines.append(f"  Base System Prompt: [same as previous turn for {actor_id}]")
        else:
            prompt_cache[actor_id] = base_system_prompt
            lines.append("  Base System Prompt:")
            lines.append(_indent_block(base_system_prompt, prefix="    "))

    if runtime_context_text:
        lines.append("  Runtime Context Message:")
        lines.append(_indent_block(runtime_context_text, prefix="    "))

    return lines


def _render_react_step(
    *,
    step: dict[str, Any],
    base_system_prompt: str,
    runtime_context_text: str,
) -> list[str]:
    lines = [f"  Step {step.get('step_index')}"]
    request = step.get("request", {})
    response = step.get("response", {})

    lines.append(
        f"    Request Message Count: {request.get('message_count', 0)}"
    )
    lines.append("    Request Messages:")
    for index, message in enumerate(request.get("messages", []), start=1):
        role = message.get("role")
        content = str(message.get("content", ""))
        if role == "system" and content == base_system_prompt:
            lines.append(f"      [{index}] system(base_system_prompt)")
            continue
        if role == "system" and content == runtime_context_text:
            lines.append(f"      [{index}] system(runtime_context)")
            continue
        lines.append(f"      [{index}] role={role}")
        if message.get("tool_calls"):
            lines.append(
                _indent_block(
                    json.dumps(message.get("tool_calls"), ensure_ascii=False, indent=2),
                    prefix="        ",
                )
            )
        if content.strip():
            lines.append(_indent_block(content, prefix="        "))

    request_tools = request.get("tools", [])
    if request_tools:
        lines.append("    Tools Offered To Model:")
        for tool in request_tools:
            lines.append(f"      - {tool.get('name')}: {tool.get('description')}")
    else:
        lines.append("    Tools Offered To Model: none")

    lines.append(
        "    Model Response: "
        f"model={response.get('model')}, "
        f"finish_reason={response.get('finish_reason')}, "
        f"latency_ms={response.get('latency_ms')}"
    )
    usage = response.get("usage")
    if usage:
        lines.append(
            "    Usage: "
            f"prompt={usage.get('prompt_tokens')}, "
            f"completion={usage.get('completion_tokens')}, "
            f"total={usage.get('total_tokens')}"
        )

    tool_calls = response.get("tool_calls", [])
    if tool_calls:
        lines.append("    Tool Calls:")
        for tool_call in tool_calls:
            lines.append(
                f"      - {tool_call.get('name')} "
                f"args={json.dumps(tool_call.get('arguments', {}), ensure_ascii=False)}"
            )

    tool_results = step.get("tool_results", [])
    if tool_results:
        lines.append("    Tool Results:")
        for tool_result in tool_results:
            lines.append(
                f"      - {tool_result.get('tool_name')} "
                f"args={json.dumps(tool_result.get('arguments', {}), ensure_ascii=False)}"
            )
            lines.append(
                _indent_block(str(tool_result.get("content", "")), prefix="        ")
            )

    assistant_message = response.get("assistant_message")
    if assistant_message and assistant_message.get("content", "").strip():
        lines.append("    Assistant Message:")
        lines.append(
            _indent_block(str(assistant_message.get("content", "")), prefix="      ")
        )

    provider_metadata = response.get("provider_metadata")
    if provider_metadata:
        lines.append("    Provider Metadata:")
        lines.append(
            _indent_block(
                json.dumps(provider_metadata, ensure_ascii=False, indent=2),
                prefix="      ",
            )
        )

    return lines


def _indent_block(text: str, *, prefix: str = "  ") -> str:
    stripped = text.rstrip()
    if not stripped:
        return prefix.rstrip()
    return "\n".join(prefix + line for line in stripped.splitlines())


def _resolve_log_path(
    *,
    scenario: str,
    log_file: str | None,
) -> Path:
    if log_file:
        candidate = Path(log_file).expanduser()
        if not candidate.is_absolute():
            candidate = SCRIPT_DIR / candidate
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        candidate = SCRIPT_DIR / f"{scenario}_{stamp}.txt"

    if not candidate.suffix:
        candidate = candidate.with_suffix(".txt")
    return candidate.resolve()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a manual live LLM smoke scenario for Amphoreus.",
    )
    parser.add_argument(
        "--scenario",
        choices=("heartbeat_scene", "tribbie_divination"),
        default="heartbeat_scene",
    )
    parser.add_argument(
        "--format",
        choices=("pretty", "json"),
        default="pretty",
    )
    parser.add_argument(
        "--scene-turn-limit",
        type=int,
        default=6,
    )
    parser.add_argument(
        "--initiating-content",
        default="昔涟轻声问：缇宝，要不要替我占一卦？",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help=(
            "Optional text log path. If omitted, the script writes to "
            "<script_dir>/<scenario>_<timestamp>.txt next to this smoke script."
        ),
    )
    args = parser.parse_args()
    log_path = _resolve_log_path(
        scenario=args.scenario,
        log_file=args.log_file,
    )
    output = OutputMirror(log_path=log_path)

    output.emit_line(
        "[live_smoke] "
        f"scenario={args.scenario} format={args.format} log_file={log_path}"
    )

    try:
        if args.scenario == "tribbie_divination":
            payload = run_tribbie_divination_smoke(
                scene_turn_limit=args.scene_turn_limit,
                initiating_content=args.initiating_content,
            )
        else:
            payload = run_heartbeat_scene_smoke()

        output.emit_line()
        if args.format == "json":
            output.emit_block(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            output.emit_block(render_pretty_payload(payload))
        output.emit_line()
        output.emit_line(f"[live_smoke] saved_to={log_path}")
    finally:
        output.close()


if __name__ == "__main__":
    main()
