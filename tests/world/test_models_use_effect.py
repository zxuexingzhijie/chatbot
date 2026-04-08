from __future__ import annotations
from tavern.world.models import EventSpec, UseEffect, Item


def test_event_spec_roundtrip():
    spec = EventSpec(id="box_opened", type="story", description="铁盒被打开了", actor="player")
    data = spec.model_dump()
    restored = EventSpec(**data)
    assert restored == spec


def test_event_spec_actor_optional():
    spec = EventSpec(id="evt1", type="story", description="something")
    assert spec.actor is None


def test_use_effect_unlock_roundtrip():
    eff = UseEffect(type="unlock", location="bar_area", exit_direction="down")
    data = eff.model_dump()
    restored = UseEffect(**data)
    assert restored == eff


def test_use_effect_with_event_roundtrip():
    eff = UseEffect(
        type="story_event",
        event=EventSpec(id="box_opened", type="story", description="铁盒打开了"),
    )
    data = eff.model_dump()
    restored = UseEffect(**data)
    assert restored.event is not None
    assert restored.event.id == "box_opened"


def test_item_with_use_effects_roundtrip():
    item = Item(
        id="cellar_key",
        name="地下室钥匙",
        description="一把钥匙",
        use_effects=(
            UseEffect(type="unlock", location="bar_area", exit_direction="down"),
            UseEffect(type="consume"),
        ),
    )
    data = item.model_dump()
    restored = Item(**data)
    assert len(restored.use_effects) == 2
    assert restored.use_effects[0].type == "unlock"
    assert restored.use_effects[1].type == "consume"


def test_item_use_effects_default_empty():
    item = Item(id="x", name="X", description="d")
    assert item.use_effects == ()


def test_use_effect_spawn_to_inventory_default():
    assert UseEffect(type="spawn_item").spawn_to_inventory is True


def test_use_effect_spawn_to_inventory_false_roundtrip():
    eff = UseEffect(type="spawn_item", item_id="x", spawn_to_inventory=False)
    data = eff.model_dump()
    restored = UseEffect(**data)
    assert restored.spawn_to_inventory is False


def test_loader_builds_item_with_use_effects():
    from tavern.world.loader import _build_items
    raw = {
        "cellar_key": {
            "name": "地下室钥匙",
            "description": "一把钥匙",
            "portable": True,
            "usable_with": ["cellar_door"],
            "use_effects": [
                {"type": "unlock", "location": "bar_area", "exit_direction": "down"},
                {"type": "consume"},
            ],
        }
    }
    items = _build_items(raw)
    key = items["cellar_key"]
    assert len(key.use_effects) == 2
    assert key.use_effects[0].type == "unlock"
    assert key.use_effects[0].location == "bar_area"
    assert key.use_effects[1].type == "consume"


def test_loader_builds_item_with_story_event_effect():
    from tavern.world.loader import _build_items
    raw = {
        "rusty_box": {
            "name": "铁盒",
            "description": "生锈的盒子",
            "use_effects": [
                {
                    "type": "story_event",
                    "event": {
                        "id": "box_opened",
                        "type": "story",
                        "description": "铁盒打开了",
                    },
                }
            ],
        }
    }
    items = _build_items(raw)
    box = items["rusty_box"]
    assert len(box.use_effects) == 1
    assert box.use_effects[0].event is not None
    assert box.use_effects[0].event.id == "box_opened"
