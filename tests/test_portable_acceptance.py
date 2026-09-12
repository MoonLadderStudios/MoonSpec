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


@pytest.mark.parametrize(
    "refs", ["artifact:check", {}, None, [], [""], [" \t"], [17], [["check"]]]
)
def test_reuse_cli_rejects_malformed_evidence_refs(verified_candidate, tmp_path, refs):
    repo, current, report = verified_candidate
    git(repo, "add", ".")
    git(repo, "commit", "-m", "verified candidate")
    git(repo, "update-ref", "refs/heads/release", "HEAD")
    current.update(acceptance.capture(repo, "example/repo", "release"))
    assert acceptance.reuse(report, current)["completionEligible"]
    report["validatedRefs"]["acceptance"]["evidence"][0]["evidenceRefs"] = refs
    report_path = tmp_path / "report.json"
    current_path = tmp_path / "current.json"
    report_path.write_text(json.dumps(report))
    current_path.write_text(json.dumps(current))
    decision = json.loads(
        subprocess.check_output(
            [
                sys.executable,
                str(SCRIPT),
                "reuse",
                "--report",
                str(report_path),
                "--current",
                str(current_path),
            ],
            text=True,
        )
    )
    assert not decision["reusable"] and not decision["completionEligible"]
    assert decision["reasons"]


@pytest.mark.parametrize(
    "ids", [[], [""], [" \t"], ["AC-1", ""], ["AC-1", "AC-1"], [17], "AC-1"]
)
def test_scope_and_reuse_reject_invalid_mandatory_ids(verified_candidate, ids):
    _, current, report = verified_candidate
    with pytest.raises(ValueError, match="mandatory requirement IDs"):
        acceptance.scope(b"Print 42", "example/repo#1", ids, complete=True)
    current["scope"]["requirementIds"] = ids
    report["validatedRefs"]["acceptance"]["scope"] = copy.deepcopy(current["scope"])
    report["validatedRefs"]["acceptance"]["evidence"] = [
        {"requirementId": requirement_id, "evidenceRefs": ["artifact:check"]}
        for requirement_id in ids
    ]
    decision = acceptance.reuse(report, current)
    assert not decision["reusable"] and not decision["completionEligible"]
    assert decision["reasons"]


@pytest.mark.parametrize("requirement", ["", " \t"])
def test_capture_cli_rejects_blank_mandatory_id(
    verified_candidate, tmp_path, requirement
):
    repo, _, _ = verified_candidate
    source = tmp_path / "issue.txt"
    source.write_text("Print 42")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "capture",
            "--repo",
            str(repo),
            "--repository",
            "example/repo",
            "--target",
            "release",
            "--source",
            str(source),
            "--source-ref",
            "example/repo#1",
            "--requirement",
            requirement,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "mandatory requirement IDs" in result.stderr
    assert not result.stdout


@pytest.mark.parametrize("registered", [False, True])
@pytest.mark.parametrize("change", ["unstaged", "staged", "untracked"])
def test_capture_rejects_dirty_gitlinks_without_changing_staging(
    verified_candidate, registered, change
):
    repo, _, _ = verified_candidate
    nested = repo / "embedded repo"
    nested.mkdir()
    git(nested, "init", "-b", "main")
    git(nested, "config", "user.email", "fixture@example.test")
    git(nested, "config", "user.name", "Acceptance fixture")
    source = nested / "nested.py"
    source.write_text("print(1)\n")
    git(nested, "add", ".")
    git(nested, "commit", "-m", "nested baseline")
    if registered:
        git(repo, "submodule", "add", str(nested), nested.name)
        git(repo, "submodule", "absorbgitdirs")
        git(repo, "config", "submodule.embedded repo.ignore", "all")
    clean = acceptance.capture(repo, "example/repo", "release")
    git(repo, "add", "app.py")
    if change == "untracked":
        (nested / "new.py").write_text("print(2)\n")
    else:
        source.write_text("print(2)\n")
        if change == "staged":
            git(nested, "add", ".")
    parent_index = git(repo, "ls-files", "--stage")
    nested_index = git(nested, "ls-files", "--stage")
    nested_status = git(nested, "status", "--porcelain", "--untracked-files=all")
    objects_before = git(repo, "count-objects", "-v")
    with pytest.raises(ValueError, match="content-bound workspace checkpoint"):
        acceptance.capture(repo, "example/repo", "release")
    assert git(repo, "ls-files", "--stage") == parent_index
    assert git(nested, "ls-files", "--stage") == nested_index
    assert (
        git(nested, "status", "--porcelain", "--untracked-files=all") == nested_status
    )
    assert git(repo, "count-objects", "-v") == objects_before
    git(nested, "add", ".")
    git(nested, "commit", "-m", "nested verified change")
    changed = acceptance.capture(repo, "example/repo", "release")
    assert changed["subject"]["contentDigest"] != clean["subject"]["contentDigest"]
