from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "bundle"


def test_moonmind_projection_sources_exist() -> None:
    recipe = yaml.safe_load((BUNDLE / "projections" / "moonmind.yaml").read_text())

    for mapping in recipe["mappings"]:
        source = BUNDLE / mapping["from"]
        if mapping["mode"] == "file":
            assert source.is_file()
        else:
            assert mapping["mode"] == "directory"
            assert source.is_dir()


def test_moonmind_projection_targets_runtime_paths() -> None:
    recipe = yaml.safe_load((BUNDLE / "projections" / "moonmind.yaml").read_text())
    targets = {mapping["to"] for mapping in recipe["mappings"]}

    assert ".agents/skills/" in targets
    assert ".specify/templates/" in targets
    assert ".specify/scripts/bash/" in targets
    assert ".gemini/commands/" in targets
    assert "api_service/data/presets/moonspec-orchestrate.yaml" in targets
    assert "docs/Workflows/MoonSpecDocumentModel.md" in targets


def test_moonmind_projection_rejects_legacy_command_files() -> None:
    recipe = yaml.safe_load((BUNDLE / "projections" / "moonmind.yaml").read_text())

    assert ".gemini/commands/speckit.*.toml" in recipe["unexpectedLegacy"]
