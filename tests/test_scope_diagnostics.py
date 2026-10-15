"""Legacy file counts must not override the canonical acceptance decision."""
from pathlib import Path
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'bundle/scripts/bash/validate-implementation-scope.sh'


@pytest.mark.parametrize('status', ['implemented_verified', 'unverified', 'needs_human'])
@pytest.mark.parametrize('check', ['tasks', 'diff'])
def test_file_counts_are_advisory_without_new_runtime_work(tmp_path, status, check):
    def git(*args):
        subprocess.run(['git', *args], cwd=tmp_path, check=True, capture_output=True)
    git('init', '-b', '001-story')
    git('config', 'user.name', 'Fixture')
    git('config', 'user.email', 'fixture@example.test')
    feature = tmp_path / 'specs/001-story'
    feature.mkdir(parents=True)
    (feature / 'plan.md').write_text(f'| ID | Status |\n| AC-1 | {status} |\n')
    (feature / 'tasks.md').write_text('- [ ] T001 Run /moonspec.verify for AC-1\n')
    git('add', '.')
    git('commit', '-m', 'existing implementation or non-executable work')
    result = subprocess.run(['bash', str(SCRIPT), '--check', check, '--mode', 'runtime', '--base-ref', 'HEAD'], cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert 'Advisory scope diagnostic' in result.stdout
    assert 'canonical status-based acceptance' in result.stdout


def test_scope_diagnostics_preserve_invalid_argument_errors(tmp_path):
    result = subprocess.run(['bash', str(SCRIPT), '--check', 'unknown', '--mode', 'runtime'], cwd=tmp_path, capture_output=True)
    assert result.returncode == 2
