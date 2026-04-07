from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tavern.engine.actions import ActionType
from tavern.world.models import ActionRequest

if TYPE_CHECKING:
    from tavern.llm.service import LLMService

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
    ) -> ActionRequest:
        scene_context = {
            "location": location_id,
            "npcs": npcs,
            "items": items,
            "exits": exits,
        }
        try:
            result = await self._llm.classify_intent(player_input, scene_context)
        except Exception:
            logger.warning("LLM intent classification failed, falling back to CUSTOM")
            return ActionRequest(
                action=ActionType.CUSTOM,
                detail=player_input,
                confidence=0.0,
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
            )

        return result
