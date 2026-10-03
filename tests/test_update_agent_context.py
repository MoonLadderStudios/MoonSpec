from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "bundle"

AGENTS_TEXT = "# Agent Instructions\n\nRepository guidance.\n"
GEMINI_TEXT = """# probe Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-01-01

## Active Technologies

- Python 3.12 (001-old)

## Recent Changes

- 001-old: Added Python 3.12

<!-- MANUAL ADDITIONS START -->
Keep these operator notes:
- first manual note
- second manual note
- third manual note
<!-- MANUAL ADDITIONS END -->
"""
PLAN_TEXT = """# Implementation Plan

**Language/Version**: Rust 1.80
**Primary Dependencies**: Tokio
**Storage**: N/A
"""


def _consumer_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "probe"
    scripts = repo / ".specify" / "scripts" / "bash"
    scripts.mkdir(parents=True)
    for name in ("common.sh", "update-agent-context.sh"):
        shutil.copy2(BUNDLE / "scripts" / "bash" / name, scripts / name)
    template = repo / ".specify" / "templates" / "agent-file-template.md"
    template.parent.mkdir()
    shutil.copy2(BUNDLE / "templates" / template.name, template)
    plan = repo / "specs" / "002-probe" / "plan.md"
    plan.parent.mkdir(parents=True)
    plan.write_text(PLAN_TEXT, encoding="utf-8")
    (repo / "AGENTS.md").write_text(AGENTS_TEXT, encoding="utf-8")
    (repo / "CLAUDE.md").symlink_to("AGENTS.md")
    (repo / "GEMINI.md").write_text(GEMINI_TEXT, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    return repo


def _run(
    repo: Path, *args: str, extra_env: dict[str, str] | None = None,
    creation_umask: int = -1,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", ".specify/scripts/bash/update-agent-context.sh", *args],
        cwd=repo,
        env={**os.environ, "SPECIFY_FEATURE": "002-probe", **(extra_env or {})},
        check=False,
        text=True,
        capture_output=True,
        timeout=5,
        umask=creation_umask,
    )


def _manual_block(text: str) -> str:
    start = text.index("<!-- MANUAL ADDITIONS START -->")
    end = text.index("<!-- MANUAL ADDITIONS END -->")
    return text[start:end]


def test_planning_run_without_authorization_leaves_agent_guidance_untouched(
    tmp_path: Path,
) -> None:
    repo = _consumer_repo(tmp_path)

    for args in ((), ("gemini",)):
        result = _run(repo, *args)

        assert result.returncode == 0, result.stderr
        assert (repo / "CLAUDE.md").is_symlink()
        assert (repo / "AGENTS.md").read_text(encoding="utf-8") == AGENTS_TEXT
        assert (repo / "GEMINI.md").read_text(encoding="utf-8") == GEMINI_TEXT
        assert "--write" in result.stdout


def test_authorized_update_records_plan_and_preserves_manual_guidance(
    tmp_path: Path,
) -> None:
    repo = _consumer_repo(tmp_path)
    (repo / "GEMINI.md").chmod(0o644)

    result = _run(repo, "--write")

    assert result.returncode == 0, result.stderr
    gemini = (repo / "GEMINI.md").read_text(encoding="utf-8")
    assert "- Rust 1.80 + Tokio (002-probe)" in gemini
    assert "- 002-probe: Added Rust 1.80 + Tokio" in gemini
    assert _manual_block(gemini) == _manual_block(GEMINI_TEXT)
    assert (repo / "GEMINI.md").stat().st_mode & 0o777 == 0o644
    assert (repo / "CLAUDE.md").is_symlink()
    assert os.readlink(repo / "CLAUDE.md") == "AGENTS.md"
    assert (repo / "AGENTS.md").read_text(encoding="utf-8") == AGENTS_TEXT


def test_authorized_update_writes_through_symlinked_agent_file(
    tmp_path: Path,
) -> None:
    repo = _consumer_repo(tmp_path)
    (repo / "GEMINI.md").rename(repo / "guidance.md")
    (repo / "GEMINI.md").symlink_to("guidance.md")
    (repo / "guidance.md").chmod(0o640)
    before = (repo / "guidance.md").stat()

    result = _run(repo, "--write", "gemini")

    assert result.returncode == 0, result.stderr
    assert (repo / "GEMINI.md").is_symlink()
    assert "(002-probe)" in (repo / "guidance.md").read_text(encoding="utf-8")
    assert (repo / "AGENTS.md").read_text(encoding="utf-8") == AGENTS_TEXT
    after = (repo / "guidance.md").stat()
    assert (after.st_mode, after.st_uid, after.st_gid) == (
        before.st_mode, before.st_uid, before.st_gid
    )


def test_authorized_update_keeps_technologies_listed_after_recent_changes(
    tmp_path: Path,
) -> None:
    repo = _consumer_repo(tmp_path)
    technologies = "- Python 3.12 (001-a)\n- Go 1.22 (001-b)\n- Node 20 (001-c)\n"
    (repo / "GEMINI.md").write_text(
        "## Recent Changes\n- 001-a: Added Python 3.12\n\n"
        f"## Active Technologies\n{technologies}",
        encoding="utf-8",
    )

    result = _run(repo, "--write", "gemini")

    assert result.returncode == 0, result.stderr
    gemini = (repo / "GEMINI.md").read_text(encoding="utf-8")
    assert technologies in gemini
    assert "- 002-probe: Added Rust 1.80 + Tokio" in gemini


@pytest.mark.parametrize("agent", ["codex", None])
def test_authorized_update_keeps_symlinked_agents_free_of_plan_history(
    tmp_path: Path, agent: str | None
) -> None:
    repo = _consumer_repo(tmp_path)
    (repo / "AGENTS.md").rename(repo / "instructions.md")
    (repo / "AGENTS.md").symlink_to("instructions.md")

    result = _run(repo, "--write", *([agent] if agent else []))

    assert result.returncode == 0, result.stderr
    assert (repo / "AGENTS.md").is_symlink()
    assert (repo / "instructions.md").read_text(encoding="utf-8") == AGENTS_TEXT


@pytest.mark.parametrize("cycle", ["self", "pair"])
def test_authorized_update_rejects_agent_symlink_cycles(
    tmp_path: Path, cycle: str
) -> None:
    repo = _consumer_repo(tmp_path)
    (repo / "GEMINI.md").unlink()
    if cycle == "self":
        (repo / "GEMINI.md").symlink_to("GEMINI.md")
    else:
        (repo / "GEMINI.md").symlink_to("other-guidance.md")
        (repo / "other-guidance.md").symlink_to("GEMINI.md")

    result = _run(repo, "--write", "gemini")

    assert result.returncode == 1
    assert "symlink" in result.stderr.lower()
    assert "cycle" in result.stderr.lower()
    assert (repo / "GEMINI.md").is_symlink()
    assert (repo / "AGENTS.md").read_text(encoding="utf-8") == AGENTS_TEXT


def test_interrupted_agent_copy_never_leaves_partial_guidance(tmp_path: Path) -> None:
    repo = _consumer_repo(tmp_path)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    interrupted_cat = fake_bin / "cat"
    interrupted_cat.write_text("#!/bin/sh\nprintf '# interrupted copy\\n'\nexit 1\n")
    interrupted_cat.chmod(0o755)

    result = _run(
        repo, "--write", "gemini",
        extra_env={"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"},
    )

    guidance = (repo / "GEMINI.md").read_text(encoding="utf-8")
    if result.returncode == 0:
        assert "- Rust 1.80 + Tokio (002-probe)" in guidance
        assert _manual_block(guidance) == _manual_block(GEMINI_TEXT)
    else:
        assert result.returncode == 1
        assert guidance == GEMINI_TEXT


def test_failed_atomic_replacement_preserves_existing_guidance(tmp_path: Path) -> None:
    repo = _consumer_repo(tmp_path)
    target = repo / "GEMINI.md"
    target.chmod(0o640)
    before = target.stat()
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    failed_mv = fake_bin / "mv"
    failed_mv.write_text("#!/bin/sh\nexit 1\n")
    failed_mv.chmod(0o755)

    result = _run(
        repo, "--write", "gemini",
        extra_env={"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"},
    )

    assert result.returncode == 1
    assert target.read_text(encoding="utf-8") == GEMINI_TEXT
    after = target.stat()
    assert (after.st_mode, after.st_uid, after.st_gid) == (
        before.st_mode, before.st_uid, before.st_gid
    )
    assert not list(repo.glob(".agent_update.*"))


@pytest.mark.parametrize("agent", ["gemini", None])
def test_partial_generation_failure_preserves_existing_guidance(
    tmp_path: Path, agent: str | None
) -> None:
    repo = _consumer_repo(tmp_path)
    fault_env = tmp_path / "generation-fault.sh"
    fault_env.write_text(
        "printf() {\n"
        "    if [[ $1 == '%s\\n' ]]; then\n"
        "        builtin printf '# interrupted generation\\n'\n"
        "        return 1\n"
        "    fi\n"
        '    builtin printf "$@"\n'
        "}\n"
    )

    result = _run(
        repo, "--write", *([agent] if agent else []),
        extra_env={"BASH_ENV": str(fault_env)},
    )

    assert result.returncode == 1
    assert (repo / "GEMINI.md").read_text(encoding="utf-8") == GEMINI_TEXT
    assert not list(repo.glob(".agent_update.*"))


@pytest.mark.parametrize("foreign_metadata", ["owner", "group", "both"])
def test_foreign_ownership_cannot_be_silently_replaced(
    tmp_path: Path, foreign_metadata: str
) -> None:
    repo = _consumer_repo(tmp_path)
    target = repo / "GEMINI.md"
    before = target.stat()
    uid = before.st_uid + (foreign_metadata in ("owner", "both"))
    gid = before.st_gid + (foreign_metadata in ("group", "both"))
    metadata_env = tmp_path / "foreign-metadata.sh"
    # Exercise both uid and gid mismatches without privileged CI setup. The
    # real cp succeeds; this supplies the foreign target's numeric metadata.
    metadata_env.write_text(
        "ls() {\n"
        '    if [[ ${@: -1} == */GEMINI.md ]]; then\n'
        f"        builtin printf '%s\\n' '-rw-r--r-- 1 {uid} {gid} 1 Jan 1 00:00 GEMINI.md'\n"
        "    else\n"
        '        command ls "$@"\n'
        "    fi\n"
        "}\n"
    )

    result = _run(
        repo, "--write", "gemini", extra_env={"BASH_ENV": str(metadata_env)}
    )

    assert result.returncode == 1
    assert "ownership" in result.stderr.lower()
    assert target.read_text(encoding="utf-8") == GEMINI_TEXT
    after = target.stat()
    assert (after.st_uid, after.st_gid) == (before.st_uid, before.st_gid)
    assert not list(repo.glob(".agent_update.*"))


@pytest.mark.parametrize("template_mode", [0o444, 0o644])
@pytest.mark.parametrize(
    "creation_umask,expected_mode", [(0o022, 0o644), (0o002, 0o664), (0o077, 0o600)]
)
def test_new_guidance_uses_consumer_umask(
    tmp_path: Path, template_mode: int, creation_umask: int, expected_mode: int
) -> None:
    repo = _consumer_repo(tmp_path)
    (repo / "CLAUDE.md").unlink()
    (repo / ".specify/templates/agent-file-template.md").chmod(template_mode)

    result = _run(repo, "--write", "claude", creation_umask=creation_umask)

    assert result.returncode == 0, result.stderr
    assert (repo / "CLAUDE.md").stat().st_mode & 0o777 == expected_mode
    assert "Rust 1.80" in (repo / "CLAUDE.md").read_text(encoding="utf-8")
    followup = _run(repo, "--write", "claude", creation_umask=creation_umask)
    assert followup.returncode == 0, followup.stderr


@pytest.mark.parametrize("probe", ["failed", "empty", "malformed"])
def test_unavailable_ownership_evidence_preserves_guidance(
    tmp_path: Path, probe: str
) -> None:
    repo = _consumer_repo(tmp_path)
    metadata_env = tmp_path / "unavailable-metadata.sh"
    probe_body = {
        "failed": "return 1",
        "empty": "return 0",
        "malformed": "builtin printf '%s\\n' 'invalid ownership evidence'",
    }[probe]
    metadata_env.write_text(f"ls() {{ {probe_body}; }}\n")

    result = _run(
        repo, "--write", "gemini", extra_env={"BASH_ENV": str(metadata_env)}
    )

    assert result.returncode == 1
    assert "ownership" in result.stderr.lower()
    assert (repo / "GEMINI.md").read_text(encoding="utf-8") == GEMINI_TEXT
    assert not list(repo.glob(".agent_update.*"))


@pytest.mark.parametrize("target_kind", ["directory", "symlink-directory", "fifo", "symlink-fifo"])
@pytest.mark.parametrize("agent", ["gemini", None])
def test_nonregular_guidance_targets_are_rejected_without_artifacts(
    tmp_path: Path, target_kind: str, agent: str | None
) -> None:
    repo = _consumer_repo(tmp_path)
    target = repo / "GEMINI.md"
    target.unlink()
    resolved_target = repo / "unsupported-target" if target_kind.startswith("symlink-") else target
    if target_kind.endswith("directory"):
        resolved_target.mkdir()
    else:
        os.mkfifo(resolved_target)
    if target_kind.startswith("symlink-"):
        target.symlink_to(resolved_target.name)
    before = resolved_target.stat()

    result = _run(repo, "--write", *([agent] if agent else []))

    assert result.returncode == 1
    assert "non-regular" in result.stderr.lower()
    after = resolved_target.stat()
    assert (after.st_mode, after.st_ino) == (before.st_mode, before.st_ino)
    if target_kind.startswith("symlink-"):
        assert target.is_symlink()
    if target_kind.endswith("directory"):
        assert not list(resolved_target.iterdir())
    assert not list(repo.rglob(".agent_update.*"))
