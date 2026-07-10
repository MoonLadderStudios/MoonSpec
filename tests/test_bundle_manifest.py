from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "bundle"


def _manifest() -> dict:
    return yaml.safe_load((BUNDLE / "moonspec.bundle.yaml").read_text()) or {}


def test_manifest_exports_expected_skill_ids() -> None:
    manifest = _manifest()
    skills = {entry["id"] for entry in manifest["exports"]["skills"]}

    assert skills == {
        "moonspec-breakdown",
        "moonspec-specify",
        "moonspec-assess",
        "moonspec-plan",
        "moonspec-tasks",
        "moonspec-align",
        "moonspec-implement",
        "moonspec-verify",
        "moonspec-doc-reconcile",
        "moonspec-orchestrate",
    }


def test_every_exported_skill_has_front_matter_and_openai_wrapper() -> None:
    manifest = _manifest()

    for skill in manifest["exports"]["skills"]:
        skill_path = BUNDLE / skill["path"]
        wrapper_path = BUNDLE / skill["wrappers"]["openai"]
        text = skill_path.read_text()
        front_matter = yaml.safe_load(text.split("---", 2)[1]) or {}

        assert skill_path.exists()
        assert wrapper_path.exists()
        assert front_matter["name"] == skill["id"]
        assert front_matter["description"]


def test_preset_references_only_exported_skills() -> None:
    manifest = _manifest()
    skills = {entry["id"] for entry in manifest["exports"]["skills"]}
    preset = yaml.safe_load(
        (BUNDLE / "presets" / "moonspec-orchestrate.yaml").read_text()
    )

    preset_skills = {
        step["skill"]["id"]
        for step in preset["steps"]
        if isinstance(step.get("skill"), dict)
    }

    assert preset_skills <= skills
    assert "moonspec-doc-reconcile" in preset_skills


def test_commands_match_canonical_skills() -> None:
    manifest = _manifest()
    skills = {entry["id"] for entry in manifest["exports"]["skills"]}

    for command in manifest["exports"]["commands"]:
        assert command["id"].startswith("moonspec.")
        assert command["slashCommand"] == f"/{command['id']}"
        assert command["skill"] in skills
        assert (BUNDLE / command["markdown"]).exists()
        assert (BUNDLE / command["gemini"]).exists()
