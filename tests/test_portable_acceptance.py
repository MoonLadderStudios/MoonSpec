"""Exercise the shipped acceptance helper outside any orchestration host."""

import copy
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "bundle/skills/moonspec-verify/scripts/acceptance.py"
)
acceptance = ModuleType("acceptance")
exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), acceptance.__dict__)


def git(repo, *args):
    return (
        subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)
        .decode()
        .strip()
    )


@pytest.fixture
def verified_candidate(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "release")
    git(repo, "config", "user.email", "fixture@example.test")
    git(repo, "config", "user.name", "Acceptance fixture")
    app = repo / "app.py"
    app.write_text("print(0)\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "baseline")
    git(repo, "switch", "-c", "feature")
    app.write_text("print(42)\n")
    before = git(repo, "diff")
    objects_before = git(repo, "count-objects", "-v")
    current = acceptance.capture(repo, "example/repo", "release")
    assert git(repo, "count-objects", "-v") == objects_before
    current["scope"] = acceptance.scope(
        b"Print 42", "example/repo#1", ["AC-1"], complete=True
    )
    current["freshnessPolicy"] = "content"
    observed = subprocess.check_output([sys.executable, str(app)], text=True)
    assert observed == "42\n"
    evidence = tmp_path / "check.json"
    evidence.write_text(json.dumps({"output": observed, "subject": current["subject"]}))
    binding = {key: current[key] for key in ("subject", "scope", "completionTarget")}
    binding.update(
        schemaVersion="acceptance/v1",
        evidence=[{"requirementId": "AC-1", "evidenceRefs": [str(evidence)]}],
        freshness={"policy": "content"},
    )
    assert git(repo, "diff") == before
    return (
        repo,
        current,
        {"verdict": "FULLY_IMPLEMENTED", "validatedRefs": {"acceptance": binding}},
    )


def test_dirty_candidate_needs_publication_and_squash_target_can_reuse(
    verified_candidate,
):
    repo, current, report = verified_candidate
    assert acceptance.reuse(report, current) == {
        "reusable": True,
        "completionEligible": False,
        "reasons": [],
    }
    git(repo, "add", ".")
    tree = git(repo, "write-tree")
    squash = git(repo, "commit-tree", tree, "-p", "release", "-m", "squash")
    git(repo, "update-ref", "refs/heads/release", squash)
    current.update(
        acceptance.capture(repo, "example/repo", "release", target_mode=True)
    )
    assert acceptance.reuse(report, current)["completionEligible"]
    assert git(repo, "branch", "--show-current") == "feature"


@pytest.mark.parametrize(
    "change", ["candidate", "scope", "truncated", "expiry", "missing", "malformed"]
)
def test_changed_or_missing_mandatory_proof_invalidates_reuse(
    verified_candidate, change
):
    repo, original, report = verified_candidate
    current = copy.deepcopy(original)
    if change == "candidate":
        (repo / "app.py").write_text("print(-1)\n")
        current.update(acceptance.capture(repo, "example/repo", "release"))
    elif change == "scope":
        current["scope"] = acceptance.scope(
            b"Print 43", "example/repo#1", ["AC-1"], complete=True
        )
    elif change == "truncated":
        current["scope"]["complete"] = False
    elif change == "expiry":
        report["validatedRefs"]["acceptance"]["freshness"]["validUntil"] = (
            "2000-01-01T00:00:00Z"
        )
    elif change == "missing":
        report["validatedRefs"]["acceptance"]["evidence"] = []
    else:
        report["validatedRefs"]["acceptance"] = None
    decision = acceptance.reuse(report, current)
    assert not decision["reusable"] and not decision["completionEligible"]
    assert decision["reasons"]


def test_explicit_target_preserves_detached_dirty_checkout(verified_candidate):
    repo, current, _ = verified_candidate
    git(repo, "switch", "--detach")
    before = git(repo, "diff")
    target = acceptance.capture(repo, "example/repo", "release", target_mode=True)
    assert target["subject"]["contentDigest"] != current["subject"]["contentDigest"]
    assert git(repo, "diff") == before
    assert git(repo, "branch", "--show-current") == ""
