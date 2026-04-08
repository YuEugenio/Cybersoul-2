"""Runtime builders for the Amphoreus companion instance."""

from __future__ import annotations

from Phone.facade import PhoneFacade
from agents.runtime import CompanionRuntime
from agents.runtime.execution import RuntimeEffectExecutor
from memory import ActorMemoryStore
from world.core.manager import WorldManager

from instantiation.amphoreus.companions import build_cyrene_agent
from instantiation.amphoreus.context import build_cyrene_runtime_context_builder
from instantiation.amphoreus.heartbeat_runner import CyreneHeartbeatRunner
from instantiation.amphoreus.prompts import build_cyrene_system_prompt
from instantiation.amphoreus.scene_activation import SceneActivationOrchestrator


def build_cyrene_companion_runtime(
    *,
    llm_client=None,
    phone_facade: PhoneFacade | None = None,
    phone_store_path: str | None = None,
    world_manager: WorldManager | None = None,
    system_prompt: str | None = None,
    memory_store: ActorMemoryStore | None = None,
    memory_store_path: str | None = None,
) -> CompanionRuntime:
    """Build the minimal actor-centric runtime used by Cyrene."""

    resolved_system_prompt = system_prompt or build_cyrene_system_prompt()
    active_memory_store = memory_store or ActorMemoryStore(store_path=memory_store_path)
    active_world_manager = world_manager or WorldManager()
    return CompanionRuntime(
        actor_id="cyrene",
        agent_factory=lambda: build_cyrene_agent(
            llm_client=llm_client,
            system_prompt=resolved_system_prompt,
            phone_facade=phone_facade,
            phone_store_path=phone_store_path,
            world_manager=active_world_manager,
        ),
        context_builder=build_cyrene_runtime_context_builder(
            system_prompt=resolved_system_prompt,
            memory_store=active_memory_store,
        ),
        world_manager=active_world_manager,
        effect_executor=RuntimeEffectExecutor(memory_store=active_memory_store),
    )


def build_cyrene_heartbeat_runner(
    *,
    llm_client=None,
    phone_facade: PhoneFacade | None = None,
    phone_store_path: str | None = None,
    world_manager: WorldManager | None = None,
    system_prompt: str | None = None,
    memory_store: ActorMemoryStore | None = None,
    memory_store_path: str | None = None,
) -> CyreneHeartbeatRunner:
    """Build the bounded heartbeat runner used by the Runtime MVP."""

    active_world_manager = world_manager or WorldManager()
    active_memory_store = memory_store or ActorMemoryStore(store_path=memory_store_path)
    runtime = build_cyrene_companion_runtime(
        llm_client=llm_client,
        phone_facade=phone_facade,
        phone_store_path=phone_store_path,
        world_manager=active_world_manager,
        system_prompt=system_prompt,
        memory_store=active_memory_store,
    )
    scene_orchestrator = SceneActivationOrchestrator(
        world_manager=active_world_manager,
        memory_store=active_memory_store,
        llm_client=llm_client,
    )
    return CyreneHeartbeatRunner(
        runtime=runtime,
        world_manager=active_world_manager,
        scene_orchestrator=scene_orchestrator,
    )


__all__ = [
    "build_cyrene_companion_runtime",
    "build_cyrene_heartbeat_runner",
]
