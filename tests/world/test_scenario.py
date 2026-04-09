from __future__ import annotations

from pathlib import Path
import pytest
import yaml


class TestValidateScenario:
    def test_valid_scenario_returns_no_errors(self, tmp_path):
        from tavern.world.scenario import validate_scenario
        _create_valid_scenario(tmp_path)
        errors = validate_scenario(tmp_path)
        assert errors == []

    def test_missing_scenario_yaml(self, tmp_path):
        from tavern.world.scenario import validate_scenario
        _create_valid_scenario(tmp_path)
        (tmp_path / "scenario.yaml").unlink()
        errors = validate_scenario(tmp_path)
        assert any("scenario.yaml" in e for e in errors)

    def test_missing_required_field_in_scenario_yaml(self, tmp_path):
        from tavern.world.scenario import validate_scenario
        _create_valid_scenario(tmp_path)
        (tmp_path / "scenario.yaml").write_text(
            yaml.dump({"name": "Test", "description": "D"}), encoding="utf-8"
        )
        errors = validate_scenario(tmp_path)
        assert any("author" in e for e in errors)

    def test_missing_world_yaml(self, tmp_path):
        from tavern.world.scenario import validate_scenario
        _create_valid_scenario(tmp_path)
        (tmp_path / "world.yaml").unlink()
        errors = validate_scenario(tmp_path)
        assert any("world.yaml" in e for e in errors)

    def test_missing_characters_yaml(self, tmp_path):
        from tavern.world.scenario import validate_scenario
        _create_valid_scenario(tmp_path)
        (tmp_path / "characters.yaml").unlink()
        errors = validate_scenario(tmp_path)
        assert any("characters.yaml" in e for e in errors)

    def test_invalid_yaml_syntax(self, tmp_path):
        from tavern.world.scenario import validate_scenario
        _create_valid_scenario(tmp_path)
        (tmp_path / "world.yaml").write_text("{ invalid yaml: [", encoding="utf-8")
        errors = validate_scenario(tmp_path)
        assert any("解析失败" in e for e in errors)

    def test_cross_ref_invalid_location_id(self, tmp_path):
        from tavern.world.scenario import validate_scenario
        _create_valid_scenario(tmp_path)
        chars = yaml.safe_load((tmp_path / "characters.yaml").read_text())
        chars["player"]["location_id"] = "nonexistent_room"
        (tmp_path / "characters.yaml").write_text(yaml.dump(chars), encoding="utf-8")
        errors = validate_scenario(tmp_path)
        assert any("nonexistent_room" in e for e in errors)

    def test_cross_ref_invalid_npc_in_location(self, tmp_path):
        from tavern.world.scenario import validate_scenario
        _create_valid_scenario(tmp_path)
        world = yaml.safe_load((tmp_path / "world.yaml").read_text())
        world["locations"]["room"]["npcs"] = ["ghost"]
        (tmp_path / "world.yaml").write_text(yaml.dump(world), encoding="utf-8")
        errors = validate_scenario(tmp_path)
        assert any("ghost" in e for e in errors)

    def test_cross_ref_invalid_exit_target(self, tmp_path):
        from tavern.world.scenario import validate_scenario
        _create_valid_scenario(tmp_path)
        world = yaml.safe_load((tmp_path / "world.yaml").read_text())
        world["locations"]["room"]["exits"]["north"] = {"target": "void"}
        (tmp_path / "world.yaml").write_text(yaml.dump(world), encoding="utf-8")
        errors = validate_scenario(tmp_path)
        assert any("void" in e for e in errors)


class TestLoadScenarioMeta:
    def test_loads_all_fields(self, tmp_path):
        from tavern.world.scenario import load_scenario_meta
        _create_valid_scenario(tmp_path)
        meta = load_scenario_meta(tmp_path)
        assert meta.name == "测试场景"
        assert meta.author == "Test"
        assert meta.version == "1.0"
        assert meta.path == tmp_path


def _create_valid_scenario(path: Path) -> None:
    (path / "scenario.yaml").write_text(yaml.dump({
        "name": "测试场景",
        "description": "一个测试用的场景",
        "author": "Test",
        "version": "1.0",
    }), encoding="utf-8")
    (path / "world.yaml").write_text(yaml.dump({
        "locations": {
            "room": {
                "name": "房间",
                "description": "一个简单的房间",
                "exits": {},
                "items": [],
                "npcs": [],
            },
        },
        "items": {},
    }), encoding="utf-8")
    (path / "characters.yaml").write_text(yaml.dump({
        "player": {
            "id": "player",
            "name": "玩家",
            "role": "player",
            "traits": [],
            "stats": {"hp": 100},
            "inventory": [],
            "location_id": "room",
        },
        "npcs": {},
    }), encoding="utf-8")


class TestScaffoldScenario:
    def test_creates_directory_structure(self, tmp_path):
        from tavern.world.scenario import scaffold_scenario
        result = scaffold_scenario("my_story", tmp_path)
        assert result == tmp_path / "my_story"
        assert (result / "scenario.yaml").exists()
        assert (result / "world.yaml").exists()
        assert (result / "characters.yaml").exists()
        assert (result / "story.yaml").exists()
        assert (result / "skills").is_dir()

    def test_generated_scenario_passes_validation(self, tmp_path):
        from tavern.world.scenario import scaffold_scenario, validate_scenario
        result = scaffold_scenario("valid_test", tmp_path)
        errors = validate_scenario(result)
        assert errors == [], f"Scaffold should produce valid scenario: {errors}"

    def test_raises_if_directory_exists(self, tmp_path):
        from tavern.world.scenario import scaffold_scenario
        (tmp_path / "existing").mkdir()
        with pytest.raises(FileExistsError):
            scaffold_scenario("existing", tmp_path)

    def test_scenario_yaml_contains_name(self, tmp_path):
        from tavern.world.scenario import scaffold_scenario, load_scenario_meta
        scaffold_scenario("my_story", tmp_path)
        meta = load_scenario_meta(tmp_path / "my_story")
        assert meta.name == "my_story"
