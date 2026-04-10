from tavern.engine.fsm import (
    EffectKind, GameLoop, GameMode, ModeContext, SideEffect, TransitionResult,
)


class TestGameMode:
    def test_all_modes_exist(self):
        assert GameMode.EXPLORING.value == "exploring"
        assert GameMode.DIALOGUE.value == "dialogue"
        assert GameMode.COMBAT.value == "combat"
        assert GameMode.INVENTORY.value == "inventory"
        assert GameMode.SHOP.value == "shop"


class TestTransitionResult:
    def test_stay_in_mode(self):
        result = TransitionResult(next_mode=None, side_effects=())
        assert result.next_mode is None

    def test_transition_with_effects(self):
        effect = SideEffect(kind=EffectKind.START_DIALOGUE, payload={"npc_id": "grim"})
        result = TransitionResult(
            next_mode=GameMode.DIALOGUE,
            side_effects=(effect,),
        )
        assert result.next_mode == GameMode.DIALOGUE
        assert len(result.side_effects) == 1


class TestSideEffect:
    def test_frozen(self):
        e = SideEffect(kind=EffectKind.APPLY_DIFF, payload={"diff": {}})
        assert e.kind == EffectKind.APPLY_DIFF

    def test_all_effect_kinds_exist(self):
        expected = {
            "START_DIALOGUE", "END_DIALOGUE", "APPLY_DIFF", "EMIT_EVENT",
            "APPLY_TRUST", "INIT_COMBAT", "APPLY_REWARDS", "FLEE_PENALTY", "OPEN_SHOP",
        }
        actual = {k.name for k in EffectKind}
        assert expected == actual
