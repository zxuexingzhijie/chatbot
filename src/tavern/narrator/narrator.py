from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator

from tavern.narrator.prompts import NarrativeContext, build_narrative_prompt
from tavern.world.models import ActionResult
from tavern.world.state import WorldState

if TYPE_CHECKING:
    from tavern.llm.service import LLMService
    from tavern.world.memory import MemoryContext


class Narrator:
    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service

    async def stream_narrative(
        self,
        result: ActionResult,
        state: WorldState,
        memory_ctx: MemoryContext | None = None,
    ) -> AsyncGenerator[str, None]:
        try:
            ctx = self._build_context(result, state)
            messages = build_narrative_prompt(ctx, memory_ctx)
            system_prompt = messages[0]["content"]
            action_message = messages[1]["content"]
            async for chunk in self._llm.stream_narrative(system_prompt, action_message):
                yield chunk
        except Exception:
            yield result.message

    def _build_context(self, result: ActionResult, state: WorldState) -> NarrativeContext:
        player = state.characters[state.player_id]
        location = state.locations[player.location_id]

        target_name: str | None = None
        if result.target:
            if result.target in state.characters:
                target_name = state.characters[result.target].name
            elif result.target in state.items:
                target_name = state.items[result.target].name
            else:
                target_name = result.target

        return NarrativeContext(
            action_type=result.action.value,
            action_message=result.message,
            location_name=location.name,
            location_desc=location.description,
            player_name=player.name,
            target=target_name,
        )
