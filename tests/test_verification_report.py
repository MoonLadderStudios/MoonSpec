"""Producer preflight, evidence continuation, and resolved-bundle provenance.

These tests exercise the portable helper. They do not simulate a host scheduler
or claim to prove an agent's interpretation of natural-language scope.
"""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "bundle/skills/moonspec-verify/scripts/acceptance.py"
)
spec = importlib.util.spec_from_file_location("verification_acceptance", SCRIPT)
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


def pending(verdict="NO_DETERMINATION", action="reattempt_current_step"):
    return {
        "verdict": verdict,
        "recommendedNextAction": action,
        "recoverableInCurrentRuntime": False,
        "remainingWork": [{
            "requirement": "AC-1",
            "gapType": "verification",
            "remainingWork": "Retrieve the completed build job's evidence for this candidate.",
            "suggestedEvidence": ["ci:run-1/build"],
        }],
    }


@pytest.fixture
def completed():
    current = {
        "subject": {
            "repository": "example/game",
            "revision": "candidate-revision",
            "contentDigest": "git-tree:candidate-content",
        },
        "scope": acceptance.scope(
            b"Implement the output check. Physical event rehearsal is separate release work.",
            "example/game#1", ["AC-1"], complete=True,
        ),
        "completionTarget": {
            "ref": "refs/heads/main",
            "revision": "base-revision",
            "contentDigest": "git-tree:base-content",
        },
        "freshnessPolicy": "content",
    }
    binding = {key: copy.deepcopy(current[key]) for key in (
        "subject", "scope", "completionTarget"
    )}
    binding.update(
        schemaVersion="acceptance/v1",
        evidence=[{"requirementId": "AC-1", "evidenceRefs": ["ci:run-1/output"]}],
        freshness={"policy": "content"},
    )
    report = {
        "verdict": "FULLY_IMPLEMENTED",
        "recommendedNextAction": "advance",
        "recoverableInCurrentRuntime": False,
        "validatedRefs": {"acceptance": binding},
    }
    return report, current


def cli(tmp_path, text, current=None):
    path = tmp_path / "report.json"
    path.write_text(text, encoding="utf-8")
    command = [sys.executable, str(SCRIPT), "validate-report", "--report", str(path)]
    if current is not None:
        current_path = tmp_path / "current.json"
        current_path.write_text(json.dumps(current), encoding="utf-8")
        command += ["--current", str(current_path)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert path.read_text(encoding="utf-8") == text
    return result, json.loads(result.stdout)


@pytest.mark.parametrize("payload", [None, [], "FULLY_IMPLEMENTED", 1, {}])
def test_missing_or_nonobject_report_is_not_a_verdict(payload):
    result = acceptance.validate_report(payload)
    assert result["valid"] is False
    assert result["errors"]
    assert "verdict" not in result  # No fallback verdict or human escalation.


@pytest.mark.parametrize("field,value", [
    ("verdict", None),
    ("verdict", "PASS"),
    ("verdict", ["NO_DETERMINATION"]),
    ("recommendedNextAction", None),
    ("recommendedNextAction", "advance"),
    ("recommendedNextAction", ["reattempt_current_step"]),
    ("recoverableInCurrentRuntime", "false"),
    ("recoverableInCurrentRuntime", 0),
    ("invalid", True),
    ("degraded", True),
    ("invalid", "false"),
    ("remainingWork", []),
    ("remainingWork", [{}]),
])
def test_incomplete_or_contradictory_report_is_repairable_not_coerced(field, value):
    report = pending()
    report[field] = value
    before = copy.deepcopy(report)
    result = acceptance.validate_report(report)
    assert result["valid"] is False
    assert result["errors"]
    assert report == before


@pytest.mark.parametrize("verdict,action", [
    ("ADDITIONAL_WORK_NEEDED", "reattempt_current_step"),
    ("NO_DETERMINATION", "reattempt_current_step"),
    ("BLOCKED", "blocked"),
    ("NO_DETERMINATION", "needs_human"),
])
def test_truthful_nonpassing_handoff_does_not_need_local_test_tools(verdict, action):
    report = pending(verdict, action)
    if action == "needs_human":
        report["remainingWork"] = [{
            "requirement": "AUTH-1",
            "gapType": "verification",
            "remainingWork": "Obtain the explicitly required production-deployment authorization.",
        }]
    assert acceptance.validate_report(report) == {"valid": True, "errors": []}
    assert report["recoverableInCurrentRuntime"] is False
    assert report["verdict"] == verdict


def test_bound_remaining_work_reference_is_supported_without_new_envelope():
    report = pending()
    del report["remainingWork"]
    report["remainingWorkRef"] = "artifact:existing-handoff"
    assert acceptance.validate_report(report)["valid"]
    report["remainingWorkRef"] = "  "
    assert not acceptance.validate_report(report)["valid"]


@pytest.mark.parametrize("work", [{"remainingWork": [{"gapType": "implementation"}]},
                                   {"remainingWorkRef": "artifact:unresolved"}])
def test_success_cannot_retain_unresolved_remaining_work(completed, work):
    report, current = completed
    report.update(work)
    assert not acceptance.validate_report(report, current)["valid"]


def test_candidate_pass_is_not_landing_and_requires_current_binding(completed):
    report, current = completed
    assert not acceptance.validate_report(report)["valid"]
    assert acceptance.validate_report(report, current)["valid"]
    assert not acceptance.reuse(report, current)["completionEligible"]
    del report["validatedRefs"]
    assert not acceptance.validate_report(report, current)["valid"]


@pytest.mark.parametrize("change", [
    "candidate", "source", "scope-expansion", "scope-waiver", "incomplete", "missing", "expired"
])
def test_late_evidence_cannot_change_selected_scope_or_candidate(completed, change):
    report, current = completed
    binding = report["validatedRefs"]["acceptance"]
    if change == "candidate":
        current["subject"]["contentDigest"] = "git-tree:new-candidate"
    elif change == "source":
        current["scope"]["sourceDigest"] = "sha256:changed-source"
    elif change == "scope-expansion":
        binding["scope"]["requirementIds"].append("EPIC-PHYSICAL-REHEARSAL")
    elif change == "scope-waiver":
        current["scope"]["requirementIds"].append("AC-2-REQUIRED-RENDER")
    elif change == "incomplete":
        current["scope"]["complete"] = False
    elif change == "missing":
        binding["evidence"] = []
    else:
        binding["freshness"]["validUntil"] = "2000-01-01T00:00:00Z"
    assert not acceptance.validate_report(report, current)["valid"]


@pytest.mark.parametrize("text", [
    '{"verdict":',
    '{"verdict":"FULLY_IMPLEMENTED","verdict":"NO_DETERMINATION"}',
    '{"confidence":NaN}',
    '"a Markdown report is not a structured result"',
])
def test_cli_reports_malformed_json_without_a_fabricated_gate(tmp_path, text):
    result, payload = cli(tmp_path, text)
    assert result.returncode == 1
    assert payload["valid"] is False and payload["errors"]
    assert "verdict" not in payload


def test_delayed_executed_evidence_repairs_report_without_changing_candidate(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(repo), *args], stderr=subprocess.PIPE, text=True
        ).strip()

    git("init", "-b", "main")
    git("config", "user.email", "fixture@example.test")
    git("config", "user.name", "Verification fixture")
    app = repo / "app.py"
    app.write_text("print(0)\n")
    git("add", ".")
    git("commit", "-m", "baseline")
    git("switch", "-c", "candidate")
    app.write_text("print(42)\n")
    git("add", ".")
    git("commit", "-m", "candidate")
    current = acceptance.capture(repo, "example/game", "main")
    current["scope"] = acceptance.scope(b"Print 42", "example/game#1", ["AC-1"], complete=True)
    current["freshnessPolicy"] = "content"
    before = git("rev-parse", "HEAD"), git("status", "--porcelain")
    waiting = pending()
    assert acceptance.validate_report(waiting)["valid"]
    # An actual external command supplies later evidence. This is a local
    # consumer-boundary test, not a claim that a CI scheduler ran here.
    observed = subprocess.check_output([sys.executable, str(app)], text=True)
    assert observed == "42\n"
    evidence_path = tmp_path / "output.json"
    evidence_path.write_text(json.dumps({"subject": current["subject"], "output": observed}))
    binding = {key: current[key] for key in ("subject", "scope", "completionTarget")}
    binding.update(schemaVersion="acceptance/v1",
                   evidence=[{"requirementId": "AC-1", "evidenceRefs": [str(evidence_path)]}],
                   freshness={"policy": "content"})
    repaired = {
        "recommendedNextAction": "advance", "recoverableInCurrentRuntime": False,
        "validatedRefs": {"acceptance": binding},
    }
    result, diagnostic = cli(tmp_path, json.dumps(repaired), current)
    assert result.returncode == 1 and not diagnostic["valid"]
    repaired["verdict"] = "FULLY_IMPLEMENTED"
    result, diagnostic = cli(tmp_path, json.dumps(repaired), current)
    assert result.returncode == 0 and diagnostic["valid"]
    assert waiting["verdict"] == "NO_DETERMINATION"
    assert before == (git("rev-parse", "HEAD"), git("status", "--porcelain"))
    assert not acceptance.reuse(repaired, current)["completionEligible"]


def test_identity_uses_executed_skill_copy_not_upstream_or_working_directory(tmp_path):
    records = []
    for name in ("older installed skill", "new active skill"):
        root = tmp_path / name
        (root / "scripts").mkdir(parents=True)
        (root / "references").mkdir()
        (root / "SKILL.md").write_text(f"# moonspec-verify\n{name}\n")
        (root / "references/acceptance-policy.md").write_text(f"Policy {name}\n")
        installed = root / "scripts/acceptance.py"
        shutil.copyfile(SCRIPT, installed)
        record = json.loads(subprocess.check_output(
            [sys.executable, str(installed), "identity"], cwd=tmp_path, text=True
        ))
        assert record["skillPath"] == str(root.resolve())
        for relative, digest in record["files"].items():
            assert digest == "sha256:" + hashlib.sha256((root / relative).read_bytes()).hexdigest()
        records.append(record)
    assert records[0]["files"]["SKILL.md"] != records[1]["files"]["SKILL.md"]
    assert records[0]["files"]["scripts/acceptance.py"] == records[1]["files"]["scripts/acceptance.py"]
