from __future__ import annotations

import subprocess
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
