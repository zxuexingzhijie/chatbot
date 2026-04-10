from tavern.engine.seeded_rng import SeededRNG, make_seed, generate_ambience, AmbienceDetails


class TestSeededRNG:
    def test_same_seed_same_sequence(self):
        rng1 = SeededRNG(42)
        rng2 = SeededRNG(42)
        assert [rng1.next() for _ in range(10)] == [rng2.next() for _ in range(10)]

    def test_different_seed_different_sequence(self):
        rng1 = SeededRNG(42)
        rng2 = SeededRNG(99)
        assert rng1.next() != rng2.next()

    def test_next_returns_float_in_range(self):
        rng = SeededRNG(42)
        for _ in range(100):
            val = rng.next()
            assert 0.0 <= val < 1.0

    def test_choice_deterministic(self):
        options = ["a", "b", "c", "d"]
        result1 = SeededRNG(42).choice(options)
        result2 = SeededRNG(42).choice(options)
        assert result1 == result2
        assert result1 in options

    def test_weighted_choice_deterministic(self):
        options = [("common", 0.9), ("rare", 0.1)]
        result1 = SeededRNG(42).weighted_choice(options)
        result2 = SeededRNG(42).weighted_choice(options)
        assert result1 == result2

    def test_weighted_choice_respects_weights(self):
        options = [("always", 1.0), ("never", 0.0)]
        rng = SeededRNG(42)
        assert rng.weighted_choice(options) == "always"


class TestMakeSeed:
    def test_deterministic(self):
        assert make_seed("tavern_hall", 5, "ambience") == make_seed("tavern_hall", 5, "ambience")

    def test_different_location_different_seed(self):
        assert make_seed("tavern_hall", 5) != make_seed("cellar", 5)

    def test_different_turn_different_seed(self):
        assert make_seed("tavern_hall", 5) != make_seed("tavern_hall", 6)

    def test_null_separator_prevents_collision(self):
        assert make_seed("bar", 10, "") != make_seed("bar", 1, "0")


class TestGenerateAmbience:
    def test_returns_ambience_details(self):
        result = generate_ambience("tavern_hall", 1)
        assert isinstance(result, AmbienceDetails)
        assert result.weather in ["晴朗", "阴沉", "微雨", "大雾"]
        assert result.crowd_level in ["冷清", "稍有人气", "热闹", "拥挤"]
        assert isinstance(result.background_sound, str)
        assert isinstance(result.smell, str)

    def test_deterministic_for_same_inputs(self):
        a = generate_ambience("tavern_hall", 1)
        b = generate_ambience("tavern_hall", 1)
        assert a == b

    def test_different_turn_may_differ(self):
        results = {generate_ambience("tavern_hall", t).weather for t in range(20)}
        assert len(results) > 1
