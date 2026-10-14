"""Consumer safety contracts exercised through the ordinary bundle projection."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FEATURE = "001-shell-safety"
PLAN = """# Plan
**Language/Version**: Python 3.12
**Primary Dependencies**: pytest
**Storage**: N/A
**Project Type**: single
"""
GUIDANCE = """# Local guidance

## Active Technologies
- Existing language

## Recent Changes
- old one
- old two
- old three
<!-- MANUAL ADDITIONS START -->
- manual one
- manual two
- manual three
<!-- MANUAL ADDITIONS END -->
"""


@pytest.fixture(scope="module")
def projected(tmp_path_factory: pytest.TempPathFactory) -> Path:
    target = tmp_path_factory.mktemp("shell-projection")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/project_bundle.py"),
            "--target",
            str(target),
            "--projection",
            "moonmind",
            "--write",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return target / ".specify"


def consumer(tmp_path: Path, projected: Path, name: str = "consumer") -> Path:
    root = tmp_path / name
    root.mkdir()
    shutil.copytree(projected, root / ".specify")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    plan = root / "specs" / FEATURE / "plan.md"
    plan.parent.mkdir(parents=True)
    plan.write_text(PLAN)
    return root


def run(root: Path, script: str, *args: str, env: dict[str, str] | None = None):
    return subprocess.run(
        ["bash", str(root / ".specify/scripts/bash" / script), *args],
        cwd=root,
        env={**os.environ, "SPECIFY_FEATURE": FEATURE, **(env or {})},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("template", [True, False])
def test_setup_json_stdout_contains_only_one_json_document(
    tmp_path, projected, template
):
    root = consumer(tmp_path, projected)
    if not template:
        (root / ".specify/templates/plan-template.md").unlink()
    result = run(root, "setup-plan.sh", "--json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["IMPL_PLAN"] == str(root / "specs" / FEATURE / "plan.md")
    assert payload["BRANCH"] == FEATURE
    assert (
        "Copied plan template" in result.stderr
        if template
        else "Warning:" in result.stderr
    )


@pytest.mark.parametrize(
    "name", ['repo "quoted"', "repo\\backslash", "repo\ttab\nline", "repo-雪"]
)
def test_setup_json_escapes_paths_losslessly(tmp_path, projected, name):
    root = consumer(tmp_path, projected, name)
    result = run(root, "setup-plan.sh", "--json")
    assert result.returncode == 0, result.stderr
    # Decode the last line separately so a broken stdout diagnostic cannot hide
    # incorrect escaping of the machine-readable values.
    payload = json.loads(result.stdout.splitlines()[-1])
    assert payload == {
        "FEATURE_SPEC": str(root / "specs" / FEATURE / "spec.md"),
        "IMPL_PLAN": str(root / "specs" / FEATURE / "plan.md"),
        "SPECS_DIR": str(root / "specs" / FEATURE),
        "BRANCH": FEATURE,
        "HAS_GIT": "true",
    }


@pytest.mark.parametrize("tainted", ["root", "branch"])
def test_feature_assignments_treat_shell_syntax_as_data(tmp_path, projected, tainted):
    name = "repo';touch injected;#" if tainted == "root" else "consumer"
    root = consumer(tmp_path, projected, name)
    branch = "002-feature';touch injected;#" if tainted == "branch" else FEATURE
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source .specify/scripts/bash/common.sh; eval "$(get_feature_paths)"; printf "%s\\0%s\\0%s" "$REPO_ROOT" "$CURRENT_BRANCH" "$FEATURE_DIR"',
        ],
        cwd=root,
        env={**os.environ, "SPECIFY_FEATURE": branch},
        capture_output=True,
        text=True,
        check=False,
    )
    assert not (root / "injected").exists(), "Feature paths executed shell syntax"
    assert result.returncode == 0, result.stderr
    assert result.stdout.split("\0") == [
        str(root),
        branch,
        str(root / "specs" / branch),
    ]


@pytest.mark.parametrize("agent", [(), ("claude",), ("codex",)])
@pytest.mark.parametrize("has_plan", [True, False])
def test_guidance_updates_require_explicit_write(tmp_path, projected, agent, has_plan):
    root = consumer(tmp_path, projected)
    if not has_plan:
        shutil.rmtree(root / "specs")
    for name in ("CLAUDE.md", "AGENTS.md"):
        (root / name).write_text(GUIDANCE)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.glob("*.md")}
    result = run(root, "update-agent-context.sh", *agent)
    assert result.returncode == 0, result.stderr
    assert {
        p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.glob("*.md")
    } == before
    assert "--write" in result.stdout


def test_default_invocation_does_not_create_guidance(tmp_path, projected):
    root = consumer(tmp_path, projected)
    result = run(root, "update-agent-context.sh")
    assert result.returncode == 0, result.stderr
    assert not list(root.glob("*.md"))


def test_authorized_update_preserves_manual_additions(tmp_path, projected):
    root = consumer(tmp_path, projected)
    target = root / "CLAUDE.md"
    target.write_text(GUIDANCE)
    result = run(root, "update-agent-context.sh", "--write", "claude")
    assert result.returncode == 0, result.stderr
    content = target.read_text()
    assert "Python 3.12 + pytest" in content
    marker = "<!-- MANUAL ADDITIONS START -->"
    assert content[content.index(marker) :] == GUIDANCE[GUIDANCE.index(marker) :]
    assert "old three" not in content


@pytest.mark.parametrize("dangling", [False, True])
def test_authorized_update_preserves_symlink_and_target_metadata(
    tmp_path, projected, dangling
):
    root = consumer(tmp_path, projected)
    target = root / "guidance" / "context.md"
    target.parent.mkdir()
    if not dangling:
        target.write_text(GUIDANCE)
        target.chmod(0o640)
    (root / "CLAUDE.md").symlink_to("guidance/context.md")
    before = target.stat() if not dangling else None
    result = run(root, "update-agent-context.sh", "--write", "claude")
    assert result.returncode == 0, result.stderr
    assert (root / "CLAUDE.md").is_symlink()
    assert os.readlink(root / "CLAUDE.md") == "guidance/context.md"
    assert "Python 3.12 + pytest" in target.read_text()
    if before:
        after = target.stat()
        assert (after.st_uid, after.st_gid, stat.S_IMODE(after.st_mode)) == (
            before.st_uid,
            before.st_gid,
            stat.S_IMODE(before.st_mode),
        )
    assert not list(target.parent.glob(".agent_update.*"))


@pytest.mark.parametrize("logical_agents", [True, False])
def test_shared_guidance_preserves_agents_identity(tmp_path, projected, logical_agents):
    root = consumer(tmp_path, projected)
    target = root / ("context.md" if logical_agents else "AGENTS.md")
    target.write_text(GUIDANCE)
    if logical_agents:
        (root / "AGENTS.md").symlink_to("context.md")
    (root / "CLAUDE.md").symlink_to(target.name)
    result = run(root, "update-agent-context.sh", "--write")
    assert result.returncode == 0, result.stderr
    assert (root / "CLAUDE.md").is_symlink()
    assert target.read_text() == GUIDANCE


def test_symlink_cycles_fail_without_replacement(tmp_path, projected):
    root = consumer(tmp_path, projected)
    (root / "CLAUDE.md").symlink_to("loop.md")
    (root / "loop.md").symlink_to("CLAUDE.md")
    result = run(root, "update-agent-context.sh", "--write")
    assert result.returncode != 0
    assert "symlink cycle" in result.stderr
    assert (root / "CLAUDE.md").is_symlink()
    assert (root / "loop.md").is_symlink()


def test_update_all_propagates_atomic_publish_failure(tmp_path, projected):
    root = consumer(tmp_path, projected)
    target = root / "CLAUDE.md"
    target.write_text(GUIDANCE)
    (root / "GEMINI.md").write_text(GUIDANCE)
    commands = root / "fake-bin"
    commands.mkdir()
    (commands / "mv").write_text("#!/usr/bin/env bash\nexit 71\n")
    (commands / "mv").chmod(0o755)
    result = run(
        root,
        "update-agent-context.sh",
        "--write",
        env={"PATH": f"{commands}:{os.environ['PATH']}"},
    )
    assert result.returncode != 0
    assert "Failed to update target file" in result.stderr
    assert "completed successfully" not in result.stdout
    assert target.read_text() == GUIDANCE
    assert not list(root.rglob(".agent_update.*"))
