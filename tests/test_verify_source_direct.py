from pathlib import Path


BUNDLE = Path(__file__).resolve().parents[1] / "bundle"


def test_verify_skill_accepts_source_direct_baselines_without_feature_artifacts(
) -> None:
    text = (BUNDLE / "skills/moonspec-verify/SKILL.md").read_text(encoding="utf-8")

    assert "Treat the user's instructions as a valid verification baseline" in text
    assert "referenced declarative document as a valid verification baseline" in text
    assert "In source-direct verification mode" in text
    assert "Do not require a MoonSpec feature directory" in text
    assert "their absence is never by itself a verification gap" in text
    assert "--json --include-tasks" in text
    assert "--require-tasks" not in text


def test_verify_command_does_not_preflight_require_feature_artifacts() -> None:
    text = (BUNDLE / "commands/markdown/moonspec.verify.md").read_text(
        encoding="utf-8"
    )

    assert "scripts:" not in text
    assert "original instructions or authoritative declarative source" in text
    assert "Do not require `spec.md`, `plan.md`, or `tasks.md`" in text
    assert "--require-tasks" not in text
