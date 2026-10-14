from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def projection_command(entrypoint, target):
    command = [sys.executable]
    if entrypoint == "tool":
        command.append(str(ROOT / "tools/project_bundle.py"))
    else:
        command.extend(
            [str(ROOT / "src/moonspec_cli/project.py"), "--source", str(ROOT)]
        )
    command.extend(["--target", str(target), "--projection", "moonmind"])
    return command


@pytest.mark.parametrize("entrypoint", ["tool", "package"])
def test_projection_detects_and_removes_retired_owned_assets(tmp_path, entrypoint):
    target = tmp_path / "consumer"
    command = projection_command(entrypoint, target)
    subprocess.run([*command, "--write"], check=True, capture_output=True, text=True)

    retired = [
        target / ".agents/skills/moonspec-doc-reconcile/SKILL.md",
        target / ".agents/skills/moonspec-doc-reconcile/agents/openai.yaml",
        target / ".specify/templates/commands/moonspec.doc-reconcile.md",
        target / ".gemini/commands/moonspec.doc-reconcile.toml",
    ]
    foreign = [
        target / ".agents/skills/user-guidance/SKILL.md",
        target / ".specify/templates/commands/local-command.md",
        target / ".gemini/commands/local-command.toml",
    ]
    for path in [*retired, *foreign]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Retained consumer content\n")

    checked = subprocess.run([*command, "--check"], capture_output=True, text=True)
    assert checked.returncode == 1, "stale owned assets must fail a projection check"
    assert all(path.exists() for path in retired), "checks must not modify the consumer"

    subprocess.run([*command, "--write"], check=True, capture_output=True, text=True)
    assert all(not path.exists() for path in retired)
    assert all(path.read_text() == "Retained consumer content\n" for path in foreign)
    subprocess.run([*command, "--check"], check=True, capture_output=True, text=True)


@pytest.mark.parametrize("entrypoint", ["tool", "package"])
def test_projection_rejects_output_scope_symlink(tmp_path, entrypoint):
    target = tmp_path / "consumer"
    outside = tmp_path / "user-files"
    outside.mkdir()
    user_file = outside / "moonspec-align/SKILL.md"
    user_file.parent.mkdir()
    user_file.write_text("User edits\n")
    (target / ".agents").mkdir(parents=True)
    (target / ".agents/skills").symlink_to(outside, target_is_directory=True)

    result = subprocess.run(
        [*projection_command(entrypoint, target), "--write"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert user_file.read_text() == "User edits\n"


@pytest.mark.parametrize("entrypoint", ["tool", "package"])
def test_retired_skill_symlink_cleanup_preserves_its_target(tmp_path, entrypoint):
    target = tmp_path / "consumer"
    command = projection_command(entrypoint, target)
    subprocess.run([*command, "--write"], check=True, capture_output=True, text=True)
    outside = tmp_path / "user-files"
    outside.mkdir()
    user_file = outside / "SKILL.md"
    user_file.write_text("User edits\n")
    retired = target / ".agents/skills/moonspec-doc-reconcile"
    retired.symlink_to(outside, target_is_directory=True)

    subprocess.run([*command, "--write"], check=True, capture_output=True, text=True)
    assert not retired.is_symlink()
    assert user_file.read_text() == "User edits\n"


@pytest.mark.parametrize("entrypoint", ["tool", "package"])
def test_projection_preserves_directory_blocking_a_planned_file(tmp_path, entrypoint):
    target = tmp_path / "consumer"
    blocked = target / ".agents/skills/moonspec-align/SKILL.md"
    blocked.mkdir(parents=True)
    user_file = blocked / "user.txt"
    user_file.write_text("User edits\n")

    result = subprocess.run(
        [*projection_command(entrypoint, target), "--write"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert user_file.read_text() == "User edits\n"
