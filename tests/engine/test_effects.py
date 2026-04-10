from tavern.engine.effects import EFFECT_EXECUTORS
from tavern.engine.fsm import EffectKind


class TestEffectExecutors:
    def test_all_effect_kinds_have_executors(self):
        for kind in EffectKind:
            assert kind in EFFECT_EXECUTORS, f"Missing executor for {kind}"

    def test_all_executors_are_callable(self):
        for kind, executor in EFFECT_EXECUTORS.items():
            assert callable(executor), f"Executor for {kind} is not callable"
