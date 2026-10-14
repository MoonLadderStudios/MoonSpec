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
@pytest.mark.parametrize("agent", [(), ("claude",), ("gemini",)])
def test_shared_guidance_preserves_agents_identity(
    tmp_path, projected, logical_agents, agent
):
    root = consumer(tmp_path, projected)
    target = root / ("context.md" if logical_agents else "AGENTS.md")
    target.write_text(GUIDANCE)
    if logical_agents:
        (root / "AGENTS.md").symlink_to("context.md")
    (root / "CLAUDE.md").symlink_to(target.name)
    (root / "GEMINI.md").symlink_to(target.name)
    result = run(root, "update-agent-context.sh", "--write", *agent)
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


@pytest.mark.parametrize("existing", [True, False])
@pytest.mark.parametrize("fault", ["cycle", "unreadable"])
def test_agents_resolution_errors_fail_before_targeted_update(
    tmp_path, projected, existing, fault
):
    root = consumer(tmp_path, projected)
    target = root / "CLAUDE.md"
    if existing:
        target.write_text(GUIDANCE)
    environment = {}
    if fault == "cycle":
        (root / "AGENTS.md").symlink_to("agents-loop.md")
        (root / "agents-loop.md").symlink_to("AGENTS.md")
    else:
        (root / "AGENTS.md").symlink_to("context.md")
        commands = root / "fake-bin"
        commands.mkdir()
        (commands / "readlink").write_text("#!/usr/bin/env bash\nexit 72\n")
        (commands / "readlink").chmod(0o755)
        environment["PATH"] = f"{commands}:{os.environ['PATH']}"
    result = run(root, "update-agent-context.sh", "--write", "claude", env=environment)
    assert result.returncode != 0, result.stdout
    assert "completed successfully" not in result.stdout
    assert "symlink" in result.stderr
    assert target.read_text() == GUIDANCE if existing else not target.exists()
    assert not list(root.rglob(".agent_update.*"))


@pytest.mark.parametrize("suffix", ["\n", "\n\n"])
@pytest.mark.parametrize("parent", ["guidance", "guidance\n"])
@pytest.mark.parametrize("absolute", [True, False])
@pytest.mark.parametrize("existing", [True, False])
def test_symlink_destinations_preserve_trailing_newlines(
    tmp_path, projected, suffix, parent, absolute, existing
):
    root = consumer(tmp_path, projected)
    target = root / parent / ("context.md" + suffix)
    target.parent.mkdir()
    if existing:
        target.write_text(GUIDANCE)
    sibling = target.with_name("context.md")
    sibling.write_text("Do not overwrite the trimmed sibling\n")
    link = str(target) if absolute else str(target.relative_to(root))
    (root / "CLAUDE.md").symlink_to(link)
    result = run(root, "update-agent-context.sh", "--write", "claude")
    assert result.returncode == 0, result.stderr
    assert (root / "CLAUDE.md").is_symlink()
    assert os.readlink(root / "CLAUDE.md") == link
    assert "Python 3.12 + pytest" in target.read_text()
    assert sibling.read_text() == "Do not overwrite the trimmed sibling\n"
    assert not list(root.rglob(".agent_update.*"))


def test_new_parent_canonicalization_preserves_shared_agents_identity(
    tmp_path, projected
):
    root = consumer(tmp_path, projected)
    target = root / "context.md"
    target.write_text(GUIDANCE)
    (root / "AGENTS.md").symlink_to("missing/../context.md")
    (root / "CLAUDE.md").symlink_to("context.md")
    result = run(root, "update-agent-context.sh", "--write")
    assert result.returncode == 0, result.stderr
    assert (root / "AGENTS.md").is_symlink()
    assert (root / "CLAUDE.md").is_symlink()
    assert target.read_text() == GUIDANCE


def test_dedup_array_has_nounset_safe_initialization_for_older_bash():
    # Bash <=4.3 treats an empty array as unset under `set -u`. This static
    # guard complements runtime coverage where only a newer Bash is installed.
    script = (ROOT / "bundle/scripts/bash/update-agent-context.sh").read_text()
    assert 'UPDATED_AGENT_FILES=("")' in script


@pytest.mark.parametrize("final_parent_exists", [True, False])
def test_parent_creation_reveals_symlink_before_atomic_write(
    tmp_path, projected, final_parent_exists
):
    root = consumer(tmp_path, projected)
    target = root / "guidance" / "context.md"
    if final_parent_exists:
        target.parent.mkdir()
    (root / "CLAUDE.md").symlink_to("missing/../alias.md")
    (root / "alias.md").symlink_to("guidance/context.md")
    commands = root / "fake-bin"
    commands.mkdir()
    (commands / "mv").write_text(
        '#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$MV_ARGS"\n'
        f'exec {shutil.which("mv")} "$@"\n'
    )
    (commands / "mv").chmod(0o755)
    record = root / "mv-args.txt"
    result = run(
        root,
        "update-agent-context.sh",
        "--write",
        "claude",
        env={
            "PATH": f"{commands}:{os.environ['PATH']}",
            "MV_ARGS": str(record),
        },
    )
    assert result.returncode == 0, result.stderr
    assert (root / "CLAUDE.md").is_symlink()
    assert (root / "alias.md").is_symlink()
    assert "Python 3.12 + pytest" in target.read_text()
    assert Path(record.read_text().splitlines()[-2]).parent == target.parent


@pytest.mark.parametrize("agent", [(), ("claude",), ("gemini",)])
@pytest.mark.parametrize(
    "spelling", ["missing/../context.md", "missing/child/../../context.md"]
)
@pytest.mark.parametrize("existing", [True, False])
def test_dangling_protected_alias_does_not_write_or_create_directories(
    tmp_path, projected, agent, spelling, existing
):
    root = consumer(tmp_path, projected)
    target = root / "context.md"
    if existing:
        target.write_text(GUIDANCE)
    (root / "AGENTS.md").symlink_to(spelling)
    (root / "CLAUDE.md").symlink_to("context.md")
    (root / "GEMINI.md").symlink_to("context.md")
    result = run(root, "update-agent-context.sh", "--write", *agent)
    assert result.returncode == 0, result.stderr
    assert target.read_text() == GUIDANCE if existing else not target.exists()
    assert not (root / "missing").exists()
    assert (root / "AGENTS.md").is_symlink()
    assert (root / "CLAUDE.md").is_symlink()
    assert (root / "GEMINI.md").is_symlink()
    assert not list(root.rglob(".agent_update.*"))


@pytest.mark.parametrize("agent", [(), ("codex",), ("claude",), ("gemini",)])
@pytest.mark.parametrize("alias", [True, False])
@pytest.mark.parametrize("existing", [True, False])
def test_protected_guidance_never_enters_plan_template_writer(
    tmp_path, projected, agent, alias, existing
):
    root = consumer(tmp_path, projected)
    target = root / ("policy/context.md" if alias else "AGENTS.md")
    if existing:
        target.parent.mkdir(exist_ok=True)
        target.write_text(GUIDANCE)
    if alias:
        (root / "AGENTS.md").symlink_to("policy/context.md")
    (root / "CLAUDE.md").symlink_to(str(target.relative_to(root)))
    (root / "GEMINI.md").symlink_to(str(target.relative_to(root)))
    result = run(root, "update-agent-context.sh", "--write", *agent)
    assert result.returncode == 0, result.stderr
    assert target.read_text() == GUIDANCE if existing else not target.exists()
    if alias and not existing:
        assert not target.parent.exists()
    assert "Skipping protected AGENTS guidance" in result.stdout


@pytest.mark.parametrize(
    "destination",
    [
        "context.md/",
        "context.md/.",
        "missing/../context.md/",
        "missing/..",
        "missing/../missing",
        "missing/child/../../missing",
        "alias",
    ],
)
@pytest.mark.parametrize("existing", [True, False])
def test_directory_required_symlink_destinations_fail_without_writes(
    tmp_path, projected, destination, existing
):
    root = consumer(tmp_path, projected)
    target = root / "context.md"
    if existing:
        target.write_text(GUIDANCE)
    if destination == "alias":
        (root / "alias").symlink_to("context.md/")
    (root / "CLAUDE.md").symlink_to(destination)
    result = run(root, "update-agent-context.sh", "--write", "claude")
    assert result.returncode != 0
    assert target.read_text() == GUIDANCE if existing else not target.exists()
    assert not (root / "missing").exists()
    assert (root / "CLAUDE.md").is_symlink()


@pytest.mark.parametrize("protected", [True, False])
def test_directory_symlinks_precede_dotdot_identity_normalization(
    tmp_path, projected, protected
):
    root = consumer(tmp_path, projected)
    outside = tmp_path / "outside"
    (outside / "deep").mkdir(parents=True)
    target = outside / "context.md"
    target.write_text(GUIDANCE)
    canary = root / "context.md"
    canary.write_text("Not the same target\n")
    (root / "directory-alias").symlink_to(outside / "deep", target_is_directory=True)
    spelling = "directory-alias/missing/../../context.md"
    if protected:
        (root / "AGENTS.md").symlink_to(spelling)
        (root / "CLAUDE.md").symlink_to(target)
    else:
        (root / "CLAUDE.md").symlink_to(spelling)
    result = run(root, "update-agent-context.sh", "--write", "claude")
    assert result.returncode == 0, result.stderr
    assert canary.read_text() == "Not the same target\n"
    if protected:
        assert target.read_text() == GUIDANCE
        assert not (outside / "deep/missing").exists()
    else:
        assert "Python 3.12 + pytest" in target.read_text()
        assert (root / "CLAUDE.md").read_text() == target.read_text()


@pytest.mark.parametrize("agent", [(), ("claude",), ("gemini",)])
@pytest.mark.parametrize("existing", ["neither", "protected", "candidate"])
@pytest.mark.parametrize("directory", [False, True])
def test_case_ambiguous_protected_alias_is_skipped_without_creating_paths(
    tmp_path, projected, agent, existing, directory
):
    root = consumer(tmp_path, projected)
    protected = root / ("policy/context.md" if directory else "context.md")
    candidate = root / ("POLICY/CONTEXT.md" if directory else "CONTEXT.md")
    if existing != "neither":
        target = protected if existing == "protected" else candidate
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(GUIDANCE)
    (root / "AGENTS.md").symlink_to(protected.relative_to(root))
    (root / "CLAUDE.md").symlink_to(candidate.relative_to(root))
    (root / "GEMINI.md").symlink_to(candidate.relative_to(root))
    before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
    result = run(root, "update-agent-context.sh", "--write", *agent)
    assert result.returncode == 0, result.stderr
    assert "Skipping protected AGENTS guidance" in result.stdout
    assert sorted(str(path.relative_to(root)) for path in root.rglob("*")) == before
    for path in (protected, candidate):
        if path.exists():
            assert path.read_text() == GUIDANCE


@pytest.mark.parametrize("agent", [(), ("claude",), ("gemini",)])
@pytest.mark.parametrize("same_file", [True, False])
@pytest.mark.parametrize("names", [("context.md", "CONTEXT.md"), ("AGENTS.md", "agents.md")])
def test_existing_protected_aliases_use_filesystem_identity(
    tmp_path, projected, agent, same_file, names
):
    root = consumer(tmp_path, projected)
    protected = root / names[0]
    candidate = root / names[1]
    protected.write_text(GUIDANCE)
    if candidate.exists():
        if not same_file:
            pytest.skip("Distinct case-only files require a case-sensitive filesystem")
    elif same_file:
        candidate.hardlink_to(protected)
    else:
        candidate.write_text(GUIDANCE)
    if protected.name != "AGENTS.md":
        (root / "AGENTS.md").symlink_to(protected.name)
    (root / "CLAUDE.md").symlink_to(candidate.name)
    (root / "GEMINI.md").symlink_to(candidate.name)
    before = protected.stat()
    result = run(root, "update-agent-context.sh", "--write", *agent)
    assert result.returncode == 0, result.stderr
    assert protected.read_text() == GUIDANCE
    after = protected.stat()
    for attribute in ("st_dev", "st_ino", "st_nlink", "st_mode", "st_mtime_ns"):
        assert getattr(after, attribute) == getattr(before, attribute)
    if same_file:
        assert candidate.samefile(protected)
        assert candidate.read_text() == GUIDANCE
        assert "Skipping protected AGENTS guidance" in result.stdout
    else:
        assert "Python 3.12 + pytest" in candidate.read_text()
    assert (root / "CLAUDE.md").is_symlink()
    assert (root / "GEMINI.md").is_symlink()


@pytest.mark.parametrize("agent", [(), ("claude",), ("gemini",)])
def test_existing_lowercase_target_without_root_guidance_is_writable(tmp_path, projected, agent):
    root = consumer(tmp_path, projected)
    candidate = root / "agents.md"
    candidate.write_text(GUIDANCE)
    if (root / "AGENTS.md").exists():
        pytest.skip("Absent uppercase guidance requires a case-sensitive filesystem")
    for name in ("CLAUDE.md", "GEMINI.md"):
        (root / name).symlink_to(candidate.name)
    result = run(root, "update-agent-context.sh", "--write", *agent)
    assert result.returncode == 0, result.stderr
    assert "Python 3.12 + pytest" in candidate.read_text()
    assert not (root / "AGENTS.md").exists()


@pytest.mark.parametrize("agent", [(), ("copilot",)])
@pytest.mark.parametrize("scope", ["logical", "logical_parent", "physical", "physical_parent"])
@pytest.mark.parametrize("alias", ["symlink", "hardlink", "dangling"])
@pytest.mark.parametrize("root_guidance", [False, True])
def test_scoped_guidance_aliases_are_read_only(tmp_path, projected, agent, scope, alias, root_guidance):
    root = consumer(tmp_path, projected)
    logical = root / ".github/agents/copilot-instructions.md"
    logical.parent.mkdir(parents=True)
    physical = root / "policy/nested/context.md"
    physical.parent.mkdir(parents=True)
    scoped_dir = {
        "logical": logical.parent,
        "logical_parent": logical.parent.parent,
        "physical": physical.parent,
        "physical_parent": physical.parent.parent,
    }[scope]
    protected = scoped_dir / "AGENTS.md"
    if alias != "dangling":
        physical.write_text(GUIDANCE)
    if alias == "hardlink":
        protected.hardlink_to(physical)
    else:
        protected.symlink_to(os.path.relpath(physical, scoped_dir))
    logical.symlink_to(os.path.relpath(physical, logical.parent))
    if root_guidance:
        (root / "AGENTS.md").write_text("Independent root guidance\n")
    before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
    result = run(root, "update-agent-context.sh", "--write", *agent)
    assert result.returncode == 0, result.stderr
    assert "Skipping protected AGENTS guidance" in result.stdout
    assert sorted(str(path.relative_to(root)) for path in root.rglob("*")) == before
    assert logical.is_symlink()
    if alias == "dangling":
        assert not physical.exists()
    else:
        assert physical.read_text() == GUIDANCE
        assert protected.read_text() == GUIDANCE


def test_unrelated_scoped_guidance_does_not_block_selected_target(tmp_path, projected):
    root = consumer(tmp_path, projected)
    unrelated = root / "unrelated/AGENTS.md"
    unrelated.parent.mkdir()
    unrelated.symlink_to("AGENTS.md")  # An irrelevant cycle must not be traversed.
    (root / "CLAUDE.md").write_text(GUIDANCE)
    result = run(root, "update-agent-context.sh", "--write", "claude")
    assert result.returncode == 0, result.stderr
    assert "Python 3.12 + pytest" in (root / "CLAUDE.md").read_text()
    assert unrelated.is_symlink()


def test_selected_scoped_guidance_resolution_failure_prevents_write(tmp_path, projected):
    root = consumer(tmp_path, projected)
    directory = root / ".github/agents"
    directory.mkdir(parents=True)
    (directory / "AGENTS.md").symlink_to("AGENTS.md")
    candidate = directory / "copilot-instructions.md"
    candidate.write_text(GUIDANCE)
    result = run(root, "update-agent-context.sh", "--write", "copilot")
    assert result.returncode != 0
    assert "symlink cycle" in result.stderr
    assert candidate.read_text() == GUIDANCE


@pytest.mark.parametrize("intermediate", ["AGENTS.md", "link.md"])
@pytest.mark.parametrize("agent", [(), ("claude",)])
def test_traversed_scoped_guidance_alias_remains_read_only(tmp_path, projected, intermediate, agent):
    root = consumer(tmp_path, projected)
    policy = root / "policy"
    policy.mkdir()
    target = root / "context.md"
    target.write_text(GUIDANCE)
    (policy / "AGENTS.md").symlink_to("../context.md")
    if intermediate != "AGENTS.md":
        (policy / intermediate).symlink_to("../context.md")
    (root / "CLAUDE.md").symlink_to(f"policy/{intermediate}")
    result = run(root, "update-agent-context.sh", "--write", *agent)
    assert result.returncode == 0, result.stderr
    assert "Skipping protected AGENTS guidance" in result.stdout
    assert target.read_text() == GUIDANCE
    assert (policy / "AGENTS.md").is_symlink()
    assert (root / "CLAUDE.md").is_symlink()
