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


def unreachable_criterion(report, current, unverified):
    current["scope"]["requirementIds"].append("AC-2")
    binding = report["validatedRefs"]["acceptance"]
    binding["scope"]["requirementIds"].append("AC-2")
    binding["evidence"].append({"requirementId": "AC-2", "unverified": unverified})


def test_success_records_criterion_outside_verifier_reach_as_unverified(completed):
    report, current = completed
    unreachable_criterion(report, current, {
        "reason": "Requires a GPU render host this verifier does not have.",
        "verifiableBy": "the repository's GPU CI lane",
    })
    assert acceptance.validate_report(report, current)["valid"]
    assert acceptance.reuse(report, current)["reusable"]


@pytest.mark.parametrize("unverified", [
    {}, {"reason": " ", "verifiableBy": "ci"}, {"reason": "No GPU."},
    {"reason": "No GPU.", "verifiableBy": ""}, "No GPU.",
])
def test_unverified_criterion_needs_a_reason_and_who_can_verify_it(completed, unverified):
    report, current = completed
    unreachable_criterion(report, current, unverified)
    assert not acceptance.validate_report(report, current)["valid"]


def test_criterion_cannot_be_both_evidenced_and_unverified(completed):
    report, current = completed
    row = report["validatedRefs"]["acceptance"]["evidence"][0]
    row["unverified"] = {"reason": "No GPU.", "verifiableBy": "GPU CI"}
    assert not acceptance.validate_report(report, current)["valid"]


@pytest.mark.parametrize("change", ["revision", "contentDigest", "ref-only"])
def test_success_binding_requires_recorded_completion_target_identity(completed, change):
    report, current = completed
    binding = report["validatedRefs"]["acceptance"]
    if change == "revision":
        del binding["completionTarget"]["revision"]
    elif change == "contentDigest":
        del binding["completionTarget"]["contentDigest"]
    else:
        binding["completionTarget"] = {"ref": current["completionTarget"]["ref"]}
    assert not acceptance.validate_report(report, current)["valid"]
    assert not acceptance.reuse(report, current)["reusable"]


@pytest.mark.parametrize("work", [[{"x": 1}], [{"gapType": "implementation"}],
                                   [{"requirement": "AC-1", "gapType": " "}],
                                   [{"requirement": "AC-1", "gapType": "verification",
                                     "remainingWork": "  "}]])
def test_nonpassing_handoff_rejects_unactionable_remaining_work_items(work):
    report = pending()
    report["remainingWork"] = work
    assert not acceptance.validate_report(report)["valid"]


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


def test_null_unverified_is_absent_for_evidenced_row(completed):
    report, current = completed
    report["validatedRefs"]["acceptance"]["evidence"][0]["unverified"] = None
    assert acceptance.validate_report(report, current)["valid"]


@pytest.mark.parametrize("refs", [None, "", {}, False])
def test_unverified_does_not_accept_malformed_empty_refs(completed, refs):
    report, current = completed
    unreachable_criterion(report, current, {"reason": "No GPU.", "verifiableBy": "GPU CI"})
    report["validatedRefs"]["acceptance"]["evidence"][1]["evidenceRefs"] = refs
    assert not acceptance.validate_report(report, current)["valid"]


@pytest.mark.parametrize("status", ["FAILED", "VERIFIED", "MISSING", "UNKNOWN", None])
def test_legacy_unverified_metadata_cannot_mask_explicit_status(completed, status):
    report, current = completed
    unreachable_criterion(report, current, {"reason": "No GPU.", "verifiableBy": "GPU CI"})
    report["validatedRefs"]["acceptance"]["evidence"][1]["status"] = status
    assert not acceptance.validate_report(report, current)["valid"]
    assert not acceptance.reuse(report, current)["reusable"]


def test_legacy_unverified_status_requires_disclosure_even_with_refs(completed):
    report, current = completed
    report["validatedRefs"]["acceptance"]["evidence"][0]["status"] = "UNVERIFIED"
    assert not acceptance.validate_report(report, current)["valid"]
    assert not acceptance.reuse(report, current)["reusable"]


def test_legacy_explicit_unverified_with_disclosure_is_nonblocking(completed):
    report, current = completed
    unreachable_criterion(report, current, {"reason": "No GPU.", "verifiableBy": "GPU CI"})
    report["validatedRefs"]["acceptance"]["evidence"][1]["status"] = "UNVERIFIED"
    assert acceptance.validate_report(report, current)["valid"]
    assert acceptance.reuse(report, current)["reusable"]


@pytest.mark.parametrize("with_current", [False, True])
@pytest.mark.parametrize("row_update", [
    {"status": "UNVERIFIED"},
    {"status": "FAILED", "unverified": {"reason": "No GPU.", "verifiableBy": "GPU CI"}},
    {"status": "UNVERIFIED", "unverified": {"reason": "No GPU."}},
])
def test_legacy_nonpass_validates_unverified_declarations(completed, with_current, row_update):
    report, current = completed
    report.update(pending())
    row = report["validatedRefs"]["acceptance"]["evidence"][0]
    row.update(row_update)
    assert not acceptance.validate_report(report, current if with_current else None)["valid"]


@pytest.mark.parametrize("with_current", [False, True])
@pytest.mark.parametrize("explicit_status", [False, True])
@pytest.mark.parametrize("gap_field", ["requirement", "requirementIds"])
def test_legacy_nonpass_unverified_cannot_overlap_remaining_work(completed, with_current, explicit_status, gap_field):
    report, current = completed
    report.update(pending())
    unreachable_criterion(report, current, {"reason": "No GPU.", "verifiableBy": "GPU CI"})
    row = report["validatedRefs"]["acceptance"]["evidence"][1]
    if explicit_status:
        row["status"] = "UNVERIFIED"
    assert acceptance.validate_report(report, current if with_current else None)["valid"]
    report["remainingWork"][0][gap_field] = "AC-2" if gap_field == "requirement" else ["AC-1", "AC-2"]
    result = acceptance.validate_report(report, current if with_current else None)
    assert "unverified requirement cannot also remain a blocking gap" in result["errors"]


def test_legacy_nonpass_without_acceptance_binding_still_valid():
    assert acceptance.validate_report(pending())["valid"]


@pytest.mark.parametrize("requirement_id", [None, "", " ", 42, [], {}])
@pytest.mark.parametrize("with_current", [False, True])
def test_nonpass_unverified_disclosure_requires_source_id(completed, requirement_id, with_current):
    report, current = completed
    report.update(pending())
    unreachable_criterion(report, current, {"reason": "No GPU.", "verifiableBy": "GPU CI"})
    row = report["validatedRefs"]["acceptance"]["evidence"][1]
    if requirement_id is None:
        del row["requirementId"]
    else:
        row["requirementId"] = requirement_id
    result = acceptance.validate_report(report, current if with_current else None)
    assert not result["valid"]
    assert "unverified requirement needs a nonblank requirementId" in result["errors"]


@pytest.mark.parametrize("ids", ["AC-2", None, 42, {}, False])
@pytest.mark.parametrize("with_binding", [False, True])
def test_legacy_nonpass_rejects_nonlist_requirement_ids(completed, ids, with_binding):
    report, current = completed
    report.update(pending())
    unreachable_criterion(report, current, {"reason": "No GPU.", "verifiableBy": "GPU CI"})
    report["remainingWork"][0]["requirementIds"] = ids
    if not with_binding:
        del report["validatedRefs"]
    assert not acceptance.validate_report(report)["valid"]


@pytest.mark.parametrize("rows", [None, {}, "rows", 42, False])
@pytest.mark.parametrize("with_current", [False, True])
def test_legacy_nonpass_rejects_malformed_present_evidence(completed, rows, with_current):
    report, current = completed
    report.update(pending())
    report["validatedRefs"]["acceptance"]["evidence"] = rows
    result = acceptance.validate_report(report, current if with_current else None)
    assert not result["valid"]
    assert "acceptance evidence must be a list" in result["errors"]
