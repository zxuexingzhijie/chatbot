from __future__ import annotations

from typing import Any, TYPE_CHECKING

from tavern.content.conditions import evaluate_content_condition
from tavern.engine.seeded_rng import generate_ambience
from tavern.narrator.scene_cache import SceneContext, SceneContextCache

if TYPE_CHECKING:
    from tavern.content.loader import ContentLoader
    from tavern.world.state import WorldState


class CachedPromptBuilder:
    def __init__(
        self,
        content_loader: ContentLoader | None,
        cache: SceneContextCache,
        state_manager: Any,
    ) -> None:
        self._content = content_loader
        self._cache = cache
        self._state_manager = state_manager

    def resolve_content(self, content_id: str) -> str | None:
        if self._content is None:
            return None
        return self._content.resolve(content_id)

    def build_scene_context(self, state: WorldState) -> SceneContext:
        loc_id = state.player_location
        version = self._state_manager.version

        cached = self._cache.get(loc_id, version)
        if cached is not None:
            return cached

        location = state.locations[loc_id]

        description = None
        if self._content is not None:
            description = self._content.resolve(
                loc_id,
                condition_evaluator=lambda when, **kw: evaluate_content_condition(
                    when, turn=state.turn,
                ),
            )
        if description is None:
            description = location.description

        npcs_present = tuple(
            state.characters[npc_id].name
            for npc_id in location.npcs
            if npc_id in state.characters
        )
        items_visible = tuple(
            state.items[item_id].name
            for item_id in location.items
            if item_id in state.items
        )
        exits_available = tuple(location.exits.keys())
        ambience = generate_ambience(loc_id, state.turn)

        context = SceneContext(
            location_description=description,
            npcs_present=npcs_present,
            items_visible=items_visible,
            exits_available=exits_available,
            atmosphere=location.atmosphere,
            ambience=ambience,
        )
        self._cache.put(loc_id, version, context)
        return context
