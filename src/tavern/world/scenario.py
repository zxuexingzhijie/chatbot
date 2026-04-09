from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

REQUIRED_FILES = ("world.yaml", "characters.yaml")
META_FIELDS = ("name", "description", "author", "version")


@dataclass(frozen=True)
class ScenarioMeta:
    name: str
    description: str
    author: str
    version: str
    path: Path


def load_scenario_meta(path: Path) -> ScenarioMeta:
    meta_path = path / "scenario.yaml"
    raw = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    return ScenarioMeta(
        name=raw["name"],
        description=raw["description"],
        author=raw["author"],
        version=str(raw["version"]),
        path=path,
    )


def validate_scenario(path: Path) -> list[str]:
    errors: list[str] = []

    meta_path = path / "scenario.yaml"
    if not meta_path.exists():
        errors.append(f"缺少元数据文件: {meta_path}")
    else:
        try:
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
            if not isinstance(meta, dict):
                errors.append("scenario.yaml 内容不是字典")
            else:
                for field in META_FIELDS:
                    if not meta.get(field):
                        errors.append(f"scenario.yaml 缺少必需字段: {field}")
        except yaml.YAMLError as exc:
            errors.append(f"scenario.yaml 解析失败: {exc}")

    parsed: dict[str, dict] = {}
    for filename in REQUIRED_FILES:
        file_path = path / filename
        if not file_path.exists():
            errors.append(f"缺少必需文件: {filename}")
        else:
            try:
                data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
                parsed[filename] = data if isinstance(data, dict) else {}
            except yaml.YAMLError as exc:
                errors.append(f"{filename} 解析失败: {exc}")

    world_data = parsed.get("world.yaml", {})
    chars_data = parsed.get("characters.yaml", {})

    if world_data and chars_data:
        errors.extend(_cross_reference_check(world_data, chars_data))

    return errors


def _cross_reference_check(world_data: dict, chars_data: dict) -> list[str]:
    errors: list[str] = []
    locations = world_data.get("locations", {})
    items = world_data.get("items", {})
    location_ids = set(locations.keys())

    all_char_ids: set[str] = set()
    player = chars_data.get("player", {})
    if player:
        all_char_ids.add(player.get("id", "player"))
    npcs = chars_data.get("npcs", {})
    if isinstance(npcs, dict):
        all_char_ids.update(npcs.keys())

    if player:
        loc = player.get("location_id")
        if loc and loc not in location_ids:
            errors.append(
                f"角色 player 的 location_id '{loc}' 不存在于 locations 中"
            )
    if isinstance(npcs, dict):
        for npc_id, npc_data in npcs.items():
            if isinstance(npc_data, dict):
                loc = npc_data.get("location_id")
                if loc and loc not in location_ids:
                    errors.append(
                        f"角色 {npc_id} 的 location_id '{loc}' 不存在于 locations 中"
                    )

    for loc_id, loc_data in locations.items():
        if not isinstance(loc_data, dict):
            continue
        for npc_id in loc_data.get("npcs", []):
            if npc_id not in all_char_ids:
                errors.append(f"地点 {loc_id} 引用了不存在的 NPC: {npc_id}")

    for loc_id, loc_data in locations.items():
        if not isinstance(loc_data, dict):
            continue
        exits = loc_data.get("exits", {})
        if isinstance(exits, dict):
            for direction, exit_data in exits.items():
                target = (
                    exit_data.get("target") if isinstance(exit_data, dict) else None
                )
                if target and target not in location_ids:
                    errors.append(
                        f"地点 {loc_id} 的出口 {direction} 指向不存在的地点: {target}"
                    )

    item_ids = set(items.keys()) if isinstance(items, dict) else set()
    for loc_id, loc_data in locations.items():
        if not isinstance(loc_data, dict):
            continue
        exits = loc_data.get("exits", {})
        if isinstance(exits, dict):
            for direction, exit_data in exits.items():
                key_item = (
                    exit_data.get("key_item") if isinstance(exit_data, dict) else None
                )
                if key_item and key_item not in item_ids:
                    errors.append(
                        f"地点 {loc_id} 出口 {direction} 的 key_item "
                        f"'{key_item}' 不存在于 items 中"
                    )

    return errors


SCENARIO_TEMPLATE = """\
# 场景元数据
name: {name}
description: 请在此描述你的场景
author: Unknown
version: "1.0"
"""

WORLD_TEMPLATE = """\
# 世界定义 — 地点和物品
locations:
  start_room:
    name: 起始房间
    description: 这是一个空旷的房间，等待你来填充。
    exits: {}
    items: []
    npcs: []

items: {}
"""

CHARACTERS_TEMPLATE = """\
# 角色定义
player:
  id: player
  name: 冒险者
  role: player
  traits:
    - 勇敢
  stats:
    hp: 100
  inventory: []
  location_id: start_room

npcs: {}
"""

STORY_TEMPLATE = """\
# 剧情节点定义
nodes: []
"""


def scaffold_scenario(name: str, parent: Path) -> Path:
    target = parent / name
    if target.exists():
        raise FileExistsError(f"目录已存在: {target}")
    target.mkdir(parents=True)
    (target / "skills").mkdir()
    (target / "scenario.yaml").write_text(
        SCENARIO_TEMPLATE.format(name=name), encoding="utf-8"
    )
    (target / "world.yaml").write_text(WORLD_TEMPLATE, encoding="utf-8")
    (target / "characters.yaml").write_text(CHARACTERS_TEMPLATE, encoding="utf-8")
    (target / "story.yaml").write_text(STORY_TEMPLATE, encoding="utf-8")
    return target
