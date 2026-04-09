from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tavern.engine.actions import ActionType
from tavern.world.models import ActionRequest

if TYPE_CHECKING:
    from tavern.llm.service import LLMService
    from tavern.world.state import WorldState

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.5


class IntentParser:
    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service

    async def parse(
        self,
        player_input: str,
        *,
        location_id: str,
        npcs: list[str],
        items: list[str],
        exits: list[str],
        state: WorldState | None = None,
    ) -> ActionRequest:
        scene_context: dict = {
            "location": location_id,
            "npcs": npcs,
            "items": items,
            "exits": exits,
        }

        if state is not None:
            npc_parts = []
            for npc_id in npcs:
                npc = state.characters.get(npc_id)
                name = npc.name if npc else npc_id
                npc_parts.append(f"{name}({npc_id})")
            scene_context["npcs_display"] = ", ".join(npc_parts) or "无"

            item_parts = []
            location = state.locations.get(location_id)
            all_item_ids = list(items)
            if location:
                player = state.characters.get(state.player_id)
                if player:
                    all_item_ids = list(dict.fromkeys(list(items) + list(player.inventory)))
            for item_id in all_item_ids:
                item = state.items.get(item_id)
                name = item.name if item else item_id
                item_parts.append(f"{name}({item_id})")
            scene_context["items_display"] = ", ".join(item_parts) or "无"

            exit_parts = []
            if location:
                for direction, exit_ in location.exits.items():
                    target_loc = state.locations.get(exit_.target)
                    loc_name = target_loc.name if target_loc else exit_.target
                    exit_parts.append(f"{direction}→{loc_name}({exit_.target})")
            scene_context["exits_display"] = ", ".join(exit_parts) or "无"
        else:
            scene_context["npcs_display"] = ", ".join(npcs) or "无"
            scene_context["items_display"] = ", ".join(items) or "无"
            scene_context["exits_display"] = ", ".join(exits) or "无"

        try:
            result = await self._llm.classify_intent(player_input, scene_context)
        except Exception:
            logger.warning("LLM intent classification failed, falling back to CUSTOM")
            return ActionRequest(
                action=ActionType.CUSTOM,
                detail=player_input,
                confidence=0.0,
                is_fallback=True,
            )

        if result.confidence < CONFIDENCE_THRESHOLD:
            logger.info(
                "Low confidence %.2f for action %s, falling back to CUSTOM",
                result.confidence,
                result.action,
            )
            return ActionRequest(
                action=ActionType.CUSTOM,
                detail=player_input,
                confidence=result.confidence,
                is_fallback=True,
            )

        return result
