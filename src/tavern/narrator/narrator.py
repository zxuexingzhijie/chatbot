from __future__ import annotations

import logging
from typing import TYPE_CHECKING, AsyncGenerator

from tavern.narrator.prompts import NarrativeContext, build_ending_prompt, build_narrative_prompt
from tavern.world.models import ActionResult
from tavern.world.state import WorldState

if TYPE_CHECKING:
    from tavern.llm.service import LLMService
    from tavern.world.memory import MemoryContext

logger = logging.getLogger(__name__)


class Narrator:
    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service

    async def stream_narrative(
        self,
        result: ActionResult,
        state: WorldState,
        memory_ctx: MemoryContext | None = None,
        story_hint: str | None = None,
    ) -> AsyncGenerator[str, None]:
        try:
            ctx = self._build_context(result, state)
            messages = build_narrative_prompt(ctx, memory_ctx, story_hint=story_hint)
            system_prompt = messages[0]["content"]
            action_message = messages[1]["content"]
            async for chunk in self._llm.stream_narrative(system_prompt, action_message):
                yield chunk
        except Exception:
            logger.exception("Narrative stream failed, falling back to plain text")
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

    async def stream_ending_narrative(
        self,
        ending_id: str,
        narrator_hint: str,
        state: WorldState,
        memory_ctx: MemoryContext | None = None,
    ) -> AsyncGenerator[str, None]:
        try:
            messages = build_ending_prompt(ending_id, narrator_hint, state, memory_ctx)
            system_prompt = messages[0]["content"]
            user_content = messages[1]["content"]
            async for chunk in self._llm.stream_narrative(system_prompt, user_content):
                yield chunk
        except Exception:
            logger.exception("Ending narrative stream failed, falling back to plain text")
            yield f"[结局: {ending_id}]"

    async def stream_continue_narrative(
        self,
        state: WorldState,
        memory_ctx: MemoryContext | None = None,
    ) -> AsyncGenerator[str, None]:
        player = state.characters[state.player_id]
        location = state.locations[player.location_id]

        npc_names = []
        for npc_id in location.npcs:
            npc = state.characters.get(npc_id)
            if npc:
                npc_names.append(npc.name)

        item_names = []
        for item_id in location.items:
            item = state.items.get(item_id)
            if item:
                item_names.append(item.name)

        memory_section = ""
        if memory_ctx:
            if memory_ctx.recent_events:
                memory_section += f"\n最近事件: {memory_ctx.recent_events}"
            if memory_ctx.relationships:
                memory_section += f"\n人际关系: {memory_ctx.relationships}"

        system_prompt = (
            "你是一个奇幻文字冒险游戏的叙事者。用文学性的中文描写场景变化。\n"
            "请基于当前场景，描述一小段时间流逝后发生的微妙变化或新事件。\n"
            "2-3句话即可，要有画面感和沉浸感。不要重复之前的描述。"
        )
        user_content = (
            f"地点: {location.name} — {location.description}\n"
            f"玩家: {player.name}\n"
            f"在场NPC: {', '.join(npc_names) if npc_names else '无'}\n"
            f"可见物品: {', '.join(item_names) if item_names else '无'}"
            f"{memory_section}\n\n"
            "请描述场景中发生的新变化，推进一小步剧情。"
        )
        try:
            async for chunk in self._llm.stream_narrative(system_prompt, user_content):
                yield chunk
        except Exception:
            logger.exception("Continue narrative stream failed")
            yield "时间悄悄流逝，酒馆中一切如常。"
