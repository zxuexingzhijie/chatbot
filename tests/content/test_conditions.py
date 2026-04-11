from __future__ import annotations

import pytest

from tavern.content.conditions import evaluate_content_condition


class TestEvaluateContentCondition:
    def test_turn_greater_than_true(self):
        assert evaluate_content_condition("turn > 20", turn=25) is True

    def test_turn_greater_than_false(self):
        assert evaluate_content_condition("turn > 20", turn=15) is False

    def test_turn_greater_than_equal(self):
        assert evaluate_content_condition("turn > 20", turn=20) is False

    def test_turn_less_than(self):
        assert evaluate_content_condition("turn < 10", turn=5) is True

    def test_turn_greater_equal(self):
        assert evaluate_content_condition("turn >= 20", turn=20) is True

    def test_turn_less_equal(self):
        assert evaluate_content_condition("turn <= 5", turn=5) is True

    def test_invalid_expression_returns_false(self):
        assert evaluate_content_condition("invalid stuff", turn=10) is False

    def test_unknown_variable_returns_false(self):
        assert evaluate_content_condition("health > 50", turn=10) is False

    def test_empty_string_returns_false(self):
        assert evaluate_content_condition("", turn=0) is False

    def test_default_turn_zero(self):
        assert evaluate_content_condition("turn > 0", turn=0) is False
        assert evaluate_content_condition("turn >= 0") is True
