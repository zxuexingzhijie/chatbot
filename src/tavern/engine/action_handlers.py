from __future__ import annotations

from tavern.engine.action_defs import ActionDef, build_action
from tavern.engine.actions import ActionType
from tavern.engine.rules import (
    _handle_custom,
    _handle_look,
    _handle_move,
    _handle_search,
    _handle_take,
    _handle_talk,
    _handle_use,
)


def build_all_actions() -> list[ActionDef]:
    return [
        build_action(
            action_type=ActionType.MOVE,
            description="移动",
            valid_targets=lambda s: list(s.current_location.exits.keys()),
            is_available=lambda s: len(s.current_location.exits) > 0,
            handler=_handle_move,
            requires_target=True,
        ),
        build_action(
            action_type=ActionType.LOOK,
            description="查看",
            valid_targets=lambda s: (
                list(s.current_location.npcs)
                + list(s.current_location.items)
                + [c.id for c in s.characters.values() if c.id != s.player_id]
            ),
            is_available=lambda s: True,
            handler=_handle_look,
            requires_target=False,
        ),
        build_action(
            action_type=ActionType.SEARCH,
            description="搜索",
            is_available=lambda s: True,
            handler=_handle_search,
            requires_target=False,
        ),
        build_action(
            action_type=ActionType.TAKE,
            description="拾取",
            valid_targets=lambda s: [
                item_id for item_id in s.current_location.items
                if item_id in s.items and s.items[item_id].portable
            ],
            is_available=lambda s: len(s.current_location.items) > 0,
            handler=_handle_take,
            requires_target=True,
        ),
        build_action(
            action_type=ActionType.TALK,
            description="交谈",
            valid_targets=lambda s: [n.id for n in s.npcs_in_location],
            is_available=lambda s: len(s.npcs_in_location) > 0,
            handler=_handle_talk,
            requires_target=True,
        ),
        build_action(
            action_type=ActionType.PERSUADE,
            description="说服",
            valid_targets=lambda s: [n.id for n in s.npcs_in_location],
            is_available=lambda s: len(s.npcs_in_location) > 0,
            handler=_handle_talk,
            requires_target=True,
        ),
        build_action(
            action_type=ActionType.USE,
            description="使用",
            valid_targets=lambda s: list(
                s.characters[s.player_id].inventory
            ) + list(s.current_location.items),
            is_available=lambda s: (
                len(s.characters[s.player_id].inventory) > 0
                or len(s.current_location.items) > 0
            ),
            handler=_handle_use,
            requires_target=True,
        ),
        build_action(
            action_type=ActionType.CUSTOM,
            description="自定义",
            is_available=lambda s: True,
            handler=_handle_custom,
            requires_target=False,
        ),
    ]
