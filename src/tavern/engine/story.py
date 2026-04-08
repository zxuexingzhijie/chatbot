from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import yaml

from tavern.world.models import ActionResult, Event
from tavern.world.skills import ActivationCondition
from tavern.world.state import StateDiff

if TYPE_CHECKING:
    from pathlib import Path
    from tavern.world.memory import EventTimeline, RelationshipGraph
    from tavern.world.state import WorldState

logger = logging.getLogger(__name__)

TriggerMode = Literal["passive", "continue", "both"]


@dataclass(frozen=True)
class HintEvent:
    description: str
    actor: str


@dataclass(frozen=True)
class FailForward:
    after_turns: int
    hint_event: HintEvent


@dataclass(frozen=True)
class NewEventSpec:
    id: str
    type: str
    description: str
    actor: str | None = None


@dataclass(frozen=True)
class ItemPlacement:
    item_id: str
    to: str


@dataclass(frozen=True)
class ItemRemoval:
    item_id: str
    from_: str


@dataclass(frozen=True)
class StoryEffects:
    quest_updates: dict[str, dict]
    new_events: tuple[NewEventSpec, ...]
    add_items: tuple[ItemPlacement, ...] = ()
    remove_items: tuple[ItemRemoval, ...] = ()
    character_stat_deltas: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass(frozen=True)
class StoryNode:
    id: str
    act: str
    requires: tuple[str, ...]
    repeatable: bool
    trigger_mode: TriggerMode
    conditions: tuple[ActivationCondition, ...]
    effects: StoryEffects
    narrator_hint: str | None
    fail_forward: FailForward | None


@dataclass(frozen=True)
class StoryResult:
    node_id: str
    diff: StateDiff
    narrator_hint: str | None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _mode_matches(node_mode: TriggerMode, trigger: TriggerMode) -> bool:
    return node_mode == "both" or node_mode == trigger


def _all_conditions_met(
    node: StoryNode,
    state: "WorldState",
    timeline: "EventTimeline",
    relationships: "RelationshipGraph",
) -> bool:
    from tavern.engine.story_conditions import CONDITION_REGISTRY
    for cond in node.conditions:
        evaluator = CONDITION_REGISTRY.get(cond.type)
        if evaluator is None:
            logger.warning(
                "StoryEngine: unknown condition type %r — node %s skipped",
                cond.type,
                node.id,
            )
            return False
        if not evaluator(cond, state, timeline, relationships):
            return False
    return True


def _build_result(node: StoryNode, state: "WorldState") -> StoryResult:
    events = tuple(
        Event(
            id=e.id,
            turn=state.turn,
            type=e.type,
            actor=e.actor if e.actor is not None else state.player_id,
            description=e.description,
        )
        for e in node.effects.new_events
    )
    quest_updates = {
        **node.effects.quest_updates,
        node.id: {"_story_status": "completed"},
    }

    updated_characters: dict[str, dict] = {}
    updated_locations: dict[str, dict] = {}

    player = state.characters.get(state.player_id)
    player_inv = list(player.inventory) if player else []
    inv_changed = False

    def _loc_items(loc_id: str) -> list:
        if loc_id in updated_locations:
            return list(updated_locations[loc_id]["items"])
        loc = state.locations.get(loc_id)
        return list(loc.items) if loc else []

    for placement in node.effects.add_items:
        if placement.to == "inventory":
            player_inv.append(placement.item_id)
            inv_changed = True
        else:
            items = _loc_items(placement.to)
            items.append(placement.item_id)
            updated_locations[placement.to] = {"items": tuple(items)}

    for removal in node.effects.remove_items:
        if removal.from_ == "inventory":
            player_inv = [i for i in player_inv if i != removal.item_id]
            inv_changed = True
        else:
            items = _loc_items(removal.from_)
            items = [i for i in items if i != removal.item_id]
            updated_locations[removal.from_] = {"items": tuple(items)}

    if inv_changed:
        updated_characters[state.player_id] = {"inventory": tuple(player_inv)}

    diff = StateDiff(
        new_events=events,
        quest_updates=quest_updates,
        updated_characters=updated_characters,
        updated_locations=updated_locations,
        character_stat_deltas=dict(node.effects.character_stat_deltas),
        turn_increment=0,
    )
    return StoryResult(node_id=node.id, diff=diff, narrator_hint=node.narrator_hint)


def _build_hint_result(node: StoryNode, state: "WorldState") -> StoryResult:
    ff = node.fail_forward
    assert ff is not None
    hint_event = Event(
        id=f"hint_{node.id}_{uuid.uuid4().hex[:6]}",
        turn=state.turn,
        type="hint",
        actor=ff.hint_event.actor,
        description=ff.hint_event.description,
    )
    diff = StateDiff(
        new_events=(hint_event,),
        story_active_since_updates={node.id: state.turn},
        turn_increment=0,
    )
    return StoryResult(node_id=node.id, diff=diff, narrator_hint=None)


# ---------------------------------------------------------------------------
# StoryEngine
# ---------------------------------------------------------------------------

class StoryEngine:
    def __init__(self, nodes: dict[str, StoryNode]) -> None:
        self._nodes = nodes

    def get_active_nodes(self, state: "WorldState") -> set[str]:
        completed = {
            nid
            for nid, q in state.quests.items()
            if q.get("_story_status") == "completed"
        }
        return {
            nid
            for nid, node in self._nodes.items()
            if (nid not in completed or node.repeatable)
            and all(r in completed for r in node.requires)
        }

    def check(
        self,
        state: "WorldState",
        trigger_mode: TriggerMode,
        timeline: "EventTimeline",
        relationships: "RelationshipGraph",
    ) -> list[StoryResult]:
        active = self.get_active_nodes(state)
        results = []
        for nid in active:
            node = self._nodes[nid]
            if not _mode_matches(node.trigger_mode, trigger_mode):
                continue
            if _all_conditions_met(node, state, timeline, relationships):
                results.append(_build_result(node, state))
        return results

    def check_fail_forward(self, state: "WorldState") -> list[StoryResult]:
        active = self.get_active_nodes(state)
        results = []
        for nid in active:
            node = self._nodes[nid]
            if node.fail_forward is None:
                continue
            since = state.story_active_since.get(nid)
            if since is None:
                continue
            if state.turn - since >= node.fail_forward.after_turns:
                results.append(_build_hint_result(node, state))
        return results


# ---------------------------------------------------------------------------
# YAML loader
# ---------------------------------------------------------------------------

def load_story_nodes(path: "Path") -> dict[str, StoryNode]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    nodes: dict[str, StoryNode] = {}
    for entry in raw.get("nodes", []):
        try:
            trigger = entry.get("trigger", {})
            conditions = tuple(
                ActivationCondition(**c) for c in (trigger.get("conditions") or [])
            )
            effects_raw = entry.get("effects", {})
            new_events = tuple(
                NewEventSpec(**e) for e in (effects_raw.get("new_events") or [])
            )
            add_items = tuple(
                ItemPlacement(item_id=p["item_id"], to=p["to"])
                for p in (effects_raw.get("add_items") or [])
            )
            remove_items = tuple(
                ItemRemoval(item_id=r["item_id"], from_=r["from"])
                for r in (effects_raw.get("remove_items") or [])
            )
            effects = StoryEffects(
                quest_updates=dict(effects_raw.get("quest_updates") or {}),
                new_events=new_events,
                add_items=add_items,
                remove_items=remove_items,
                character_stat_deltas=dict(effects_raw.get("character_stat_deltas") or {}),
            )
            ff_raw = entry.get("fail_forward")
            fail_forward = None
            if ff_raw:
                hint_raw = ff_raw["hint_event"]
                fail_forward = FailForward(
                    after_turns=int(ff_raw["after_turns"]),
                    hint_event=HintEvent(
                        description=hint_raw["description"],
                        actor=hint_raw["actor"],
                    ),
                )
            node = StoryNode(
                id=entry["id"],
                act=entry.get("act", "act1"),
                requires=tuple(entry.get("requires") or []),
                repeatable=bool(entry.get("repeatable", False)),
                trigger_mode=trigger.get("mode", "passive"),
                conditions=conditions,
                effects=effects,
                narrator_hint=entry.get("narrator_hint"),
                fail_forward=fail_forward,
            )
            nodes[node.id] = node
        except Exception as exc:
            logger.warning(
                "load_story_nodes: failed to parse node %r: %s",
                entry.get("id"),
                exc,
            )
    return nodes
