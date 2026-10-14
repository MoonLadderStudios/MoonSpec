from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

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


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", ".specify/scripts/bash/update-agent-context.sh", *args],
        cwd=repo,
        env={**os.environ, "SPECIFY_FEATURE": "002-probe"},
        check=False,
        text=True,
        capture_output=True,
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

    result = _run(repo, "--write", "gemini")

    assert result.returncode == 0, result.stderr
    assert (repo / "GEMINI.md").is_symlink()
    assert "(002-probe)" in (repo / "guidance.md").read_text(encoding="utf-8")
    assert (repo / "AGENTS.md").read_text(encoding="utf-8") == AGENTS_TEXT


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
