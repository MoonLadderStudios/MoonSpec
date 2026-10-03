from __future__ import annotations

import subprocess

import pytest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMON_SH = ROOT / "bundle" / "scripts" / "bash" / "common.sh"


def _run_common(repo_root: Path, script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-lc", f"source {COMMON_SH}; {script}"],
        cwd=repo_root,
        check=False,
        text=True,
        capture_output=True,
    )


def test_get_current_branch_reads_feature_json_before_git(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    specify_dir = tmp_path / ".specify"
    specify_dir.mkdir()
    (specify_dir / "feature.json").write_text(
        '{\n  "feature_directory": "specs/003-user-auth"\n}\n',
        encoding="utf-8",
    )

    result = _run_common(tmp_path, "get_current_branch")

    assert result.returncode == 0
    assert result.stdout.strip() == "003-user-auth"


def test_check_feature_branch_accepts_timestamp_prefix(tmp_path: Path) -> None:
    result = _run_common(
        tmp_path,
        'check_feature_branch "20260319-143022-user-auth" true',
    )

    assert result.returncode == 0


def test_check_feature_branch_rejects_non_feature_names(tmp_path: Path) -> None:
    result = _run_common(tmp_path, 'check_feature_branch "main" true')

    assert result.returncode == 1
    assert "001-feature-name" in result.stderr
    assert "20260319-143022-feature-name" in result.stderr


@pytest.mark.parametrize("directory", ["repo", "repo's quoted workspace"])
@pytest.mark.parametrize("branch", [
    "001-normal",
    "001-spaces and 'quotes' and $dollars",
    "001-x'; : > marker; #",
    "001-newline\nand-tab\tvalue",
    "001-tail ",
    "001-tail\t",
])
def test_feature_assignments_round_trip_without_evaluating_values(tmp_path: Path, directory: str, branch: str) -> None:
    import os

    # Both repository paths and branch selectors can contain shell syntax.
    repo = tmp_path / directory
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; eval "$(get_feature_paths)"; printf "%s\\0" "$REPO_ROOT" "$CURRENT_BRANCH" "$HAS_GIT" "$FEATURE_DIR" "$FEATURE_SPEC" "$IMPL_PLAN" "$TASKS" "$RESEARCH" "$DATA_MODEL" "$QUICKSTART" "$CONTRACTS_DIR"', "bash", str(COMMON_SH)],
        cwd=repo, env={**os.environ, "SPECIFY_FEATURE": branch},
        capture_output=True, text=True, check=False,
    )
    assert not (repo / "marker").exists(), "branch data was executed as shell syntax"
    assert result.returncode == 0, result.stderr
    feature_dir = str(repo / "specs" / branch)
    expected = [str(repo), branch, "true", feature_dir]
    expected += [f"{feature_dir}/{name}" for name in ("spec.md", "plan.md", "tasks.md", "research.md", "data-model.md", "quickstart.md", "contracts")]
    assert result.stdout.split("\0") == expected + [""]


@pytest.mark.parametrize("script,args", [
    ("setup-plan.sh", ["--json"]),
    ("check-prerequisites.sh", ["--json", "--paths-only"]),
    ("check-prerequisites.sh", ["--json", "--include-tasks"]),
])
@pytest.mark.parametrize("branch", [
    "001-normal", "001-line\nbreak\tend", '001-quote"back\\slash',
    "001-tail ", "001-tail\t", "001-unicode-é-月-🚀",
    "001-controls-" + "".join(chr(code) for code in range(1, 32)),
])
@pytest.mark.parametrize("without_python", [False, True])
def test_script_json_outputs_escape_path_values(tmp_path, script, args, branch, without_python):
    import json
    import os
    import shutil

    repo = tmp_path / 'repo "quote"\nnew\tline'
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    feature = repo / "specs" / branch
    feature.mkdir(parents=True)
    for name in ("plan.md", "tasks.md", "research.md"):
        (feature / name).write_text("# Existing evidence\n")
    runtime_env = {**os.environ, "SPECIFY_FEATURE": branch}
    if without_python:
        # Projected workflows declare shell/Git, not a Python interpreter.
        runtime = tmp_path / "shell-runtime"
        runtime.mkdir()
        for command in ("bash", "git", "dirname", "basename", "mkdir", "cp", "touch", "ls", "sed", "head"):
            executable = shutil.which(command)
            assert executable is not None, command
            (runtime / command).symlink_to(executable)
        runtime_env["PATH"] = str(runtime)
        assert shutil.which("python3", path=str(runtime)) is None
    result = subprocess.run(
        [shutil.which("bash"), str(COMMON_SH.parent / script), *args],
        cwd=repo, env=runtime_env,
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload.get("FEATURE_DIR", payload.get("SPECS_DIR")) == str(feature)
    if "BRANCH" in payload:
        assert payload["BRANCH"] == branch
    if "AVAILABLE_DOCS" in payload:
        assert payload["AVAILABLE_DOCS"] == ["research.md", "tasks.md"]
