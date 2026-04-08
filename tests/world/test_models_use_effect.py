from __future__ import annotations
import pytest
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
