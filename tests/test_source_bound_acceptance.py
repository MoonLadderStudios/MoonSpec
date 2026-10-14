"""Binding regressions; artifact semantics remain the verifier's responsibility."""

import copy
import hashlib
import json
import subprocess
import sys

import pytest

from test_verification_report import acceptance, completed


@pytest.fixture
def bound(completed):
    report, current = completed
    row = {
        "id": "AC-1",
        "sourceRef": current["scope"]["sourceRef"],
        "sourceDigest": current["scope"]["sourceDigest"],
        "sourceLocator": "acceptance[0]",
        "classification": "mandatory",
        "requiredBehavior": "Print 42",
        "executableChecks": ["python app.py"],
        "proofMethods": ["automated_test"],
        "owner": "existing CI build",
    }
    current = acceptance.bind_verification_map(
        current,
        {
            "scope": copy.deepcopy(current["scope"]),
            "verificationMap": [row],
        },
    )
    current = acceptance.bind_evidence(current, {"ci:run-1/output": b"42\n"})
    binding = report["validatedRefs"]["acceptance"]
    binding["verificationMap"] = copy.deepcopy(current["verificationMap"])
    binding["evidenceSet"] = copy.deepcopy(current["evidenceSet"])
    binding["evidenceSetDigest"] = current["evidenceSetDigest"]
    binding["evidence"][0].update(
        status="VERIFIED",
        obligationDigest=acceptance.obligation_digest(row),
        proofMethod="automated_test",
        testedSubject=copy.deepcopy(current["subject"]),
    )
    return report, current


def waiting(report):
    report = copy.deepcopy(report)
    report.update(
        verdict="BLOCKED",
        recommendedNextAction="blocked",
        remainingWork=[
            {
                "requirement": "AC-1",
                "gapType": "verification",
                "remainingWork": "Read exact-head report bytes from the existing CI owner.",
            }
        ],
    )
    report["validatedRefs"]["acceptance"]["evidence"][0]["status"] = "UNVERIFIED"
    return report


def test_plan_is_source_bound_and_never_mutates_assessment(bound):
    _, current = bound
    assessment = {
        "scope": copy.deepcopy(current["scope"]),
        "verificationMap": copy.deepcopy(current["verificationMap"]),
    }
    before = copy.deepcopy(assessment)
    result = acceptance.bind_verification_map(current, assessment)
    result["verificationMap"][0]["requiredBehavior"] = "changed"
    assert assessment == before


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "digest",
        "locator",
        "duplicate",
        "missing",
        "expansion",
        "waiver",
        "checks",
        "owner",
        "methods",
    ],
)
def test_plan_rejects_unbound_or_inherited_obligations(bound, change):
    _, current = bound
    assessment = {
        "scope": copy.deepcopy(current["scope"]),
        "verificationMap": copy.deepcopy(current["verificationMap"]),
    }
    row = assessment["verificationMap"][0]
    if change == "source":
        row["sourceRef"] = "parent/epic#9"
    elif change == "digest":
        row["sourceDigest"] = "sha256:old"
    elif change == "locator":
        row["sourceLocator"] = " "
    elif change == "duplicate":
        assessment["verificationMap"].append(copy.deepcopy(row))
    elif change == "missing":
        assessment["verificationMap"] = []
    elif change == "expansion":
        row["id"] = "PHYSICAL-EPIC"
    elif change == "waiver":
        row["classification"] = "optional"
    elif change == "checks":
        row["executableChecks"] = []
    elif change == "owner":
        row["owner"] = " "
    elif change == "methods":
        row["proofMethods"] = []
    with pytest.raises(ValueError):
        acceptance.bind_verification_map(current, assessment)


def test_current_success_requires_resolved_inventory(bound):
    report, current = bound
    assert acceptance.validate_report(report, current)["valid"]
    current["evidenceSet"] = {}
    assert not acceptance.validate_report(report, current)["valid"]


@pytest.mark.parametrize(
    "verdict,action",
    [
        ("FULLY_IMPLEMENTED", "advance"),
        ("BLOCKED", "blocked"),
        ("ADDITIONAL_WORK_NEEDED", "reattempt_current_step"),
        ("NO_DETERMINATION", "reattempt_current_step"),
    ],
)
@pytest.mark.parametrize(
    "change", ["revision", "content", "source", "inventory", "policy", "obligation"]
)
def test_every_current_judgment_binds_same_source_candidate_and_evidence(
    bound, verdict, action, change
):
    report, current = bound
    if verdict != "FULLY_IMPLEMENTED":
        report = waiting(report)
    report.update(verdict=verdict, recommendedNextAction=action)
    if change == "revision":
        current["subject"]["revision"] = "new-head"
    elif change == "content":
        current["subject"]["contentDigest"] = "git-tree:new"
    elif change == "source":
        current["scope"]["sourceDigest"] = "sha256:new"
    elif change == "inventory":
        current = acceptance.bind_evidence(current, {"ci:run-1/output": b"new bytes"})
    elif change == "policy":
        current["freshnessPolicy"] = "new-policy"
    elif change == "obligation":
        current["verificationMap"][0]["requiredBehavior"] = "Print 43"
    result = acceptance.validate_report(report, current)
    assert not result["valid"], result


@pytest.mark.parametrize("change", ["optional", "opaque", "candidate", "unknown"])
def test_current_nonpass_requires_inline_mandatory_source_work(bound, change):
    report, current = bound
    report = waiting(report)
    if change == "opaque":
        del report["remainingWork"]
        report["remainingWorkRef"] = "artifact:opaque"
    elif change == "candidate":
        report["remainingWork"][0]["candidate"] = {
            **current["subject"],
            "revision": "old",
        }
    else:
        report["remainingWork"][0]["requirement"] = (
            "OPTIONAL-BROWSER" if change == "optional" else "UNSOURCED"
        )
    assert not acceptance.validate_report(report, current)["valid"]


def test_free_form_suggestions_are_advisory_and_do_not_change_obligation(bound):
    report, current = bound
    original = acceptance.obligation_digest(current["verificationMap"][0])
    current["verificationMap"][0]["suggestedEvidence"] = [
        "Try a physical rehearsal and full export"
    ]
    current["verificationMap"][0]["capability"] = {
        "status": "unavailable",
        "evidenceRefs": ["probe:new"],
    }
    report["suggestions"] = ["Consider browser screenshots"]
    assert acceptance.obligation_digest(current["verificationMap"][0]) == original
    assert acceptance.validate_report(report, current)["valid"]


def test_optional_missing_browser_does_not_become_remaining_requirement(bound):
    report, current = bound
    optional = {
        **current["verificationMap"][0],
        "id": "BROWSER",
        "classification": "optional",
        "requiredBehavior": "Optional screenshot",
        "proofMethods": ["rendered_artifact"],
    }
    current["verificationMap"].append(optional)
    report["validatedRefs"]["acceptance"]["verificationMap"].append(
        copy.deepcopy(optional)
    )
    assert acceptance.validate_report(report, current)["valid"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("proofMethod", "fake_backend"),
        ("profile", "different-gpu"),
        ("status", "UNVERIFIED"),
        ("status", "FAILED"),
    ],
)
def test_explicit_live_rendered_profile_proof_cannot_be_replaced(bound, field, value):
    report, current = bound
    plan = current["verificationMap"][0]
    plan.update(proofMethods=["live_render"], profile="NVIDIA/Vulkan")
    binding = report["validatedRefs"]["acceptance"]
    binding["verificationMap"] = copy.deepcopy(current["verificationMap"])
    row = binding["evidence"][0]
    row.update(
        obligationDigest=acceptance.obligation_digest(plan),
        proofMethod="live_render",
        profile="NVIDIA/Vulkan",
    )
    assert acceptance.validate_report(report, current)["valid"]
    row[field] = value
    assert not acceptance.validate_report(report, current)["valid"]


def test_eleven_passed_rows_survive_twelfth_missing_gpu_and_new_artifacts(bound):
    report, current = bound
    plan = current["verificationMap"][0]
    current["scope"]["requirementIds"] = [f"AC-{n}" for n in range(1, 13)]
    current["verificationMap"] = [
        {**plan, "id": rid} for rid in current["scope"]["requirementIds"]
    ]
    current = acceptance.bind_evidence(
        current, {f"test:{n}": f"{n} passed".encode() for n in range(1, 12)}
    )
    binding = report["validatedRefs"]["acceptance"]
    binding.update(
        scope=copy.deepcopy(current["scope"]),
        verificationMap=copy.deepcopy(current["verificationMap"]),
        evidenceSet=copy.deepcopy(current["evidenceSet"]),
        evidenceSetDigest=current["evidenceSetDigest"],
    )
    binding["evidence"] = [
        {
            "requirementId": row["id"],
            "status": "VERIFIED",
            "proofMethod": "automated_test",
            "obligationDigest": acceptance.obligation_digest(row),
            "evidenceRefs": [f"test:{i}"],
            "testedSubject": copy.deepcopy(current["subject"]),
        }
        for i, row in enumerate(current["verificationMap"][:11], 1)
    ]
    report.update(
        verdict="BLOCKED",
        recommendedNextAction="blocked",
        remainingWork=[
            {
                "requirement": "AC-12",
                "gapType": "verification",
                "remainingWork": "Collect required GPU proof.",
            }
        ],
    )
    assert acceptance.validate_report(report, current)["valid"]
    result = acceptance.reuse(report, current)
    assert not result["reusable"] and not result["completionEligible"]
    assert len(result["reusableRows"]) == 11
    # Added evidence makes the historical aggregate stale, not the passed rows.
    current = acceptance.bind_evidence(
        current,
        {
            **{f"test:{n}": f"{n} passed".encode() for n in range(1, 12)},
            "gpu": b"new report",
        },
    )
    assert not acceptance.validate_report(report, current)["valid"]
    assert len(acceptance.reuse(report, current)["reusableRows"]) == 11
    current["subject"]["contentDigest"] = "git-tree:changed-production"
    assert acceptance.reuse(report, current).get("reusableRows", []) == []


def test_reuse_retains_original_tested_identity_for_identical_tree(bound):
    report, current = bound
    original = copy.deepcopy(current["subject"])
    current["subject"]["revision"] = "report-only-commit"
    result = acceptance.reuse(report, current)
    assert result["reusable"]
    assert result["reusableRows"][0]["testedSubject"] == original
    assert not acceptance.validate_report(report, current)["valid"]


def test_inventory_hashes_actual_bytes_and_does_not_trust_forged_digest(bound):
    report, current = bound
    assert current["evidenceSet"] == {
        "ci:run-1/output": "sha256:" + hashlib.sha256(b"42\n").hexdigest()
    }
    current["evidenceSetDigest"] = "sha256:forged"
    report["validatedRefs"]["acceptance"]["evidenceSetDigest"] = "sha256:forged"
    assert not acceptance.validate_report(report, current)["valid"]


def test_stale_failed_report_gets_rejected_after_success_bytes_arrive(bound):
    report, current = bound
    historical = waiting(report)
    current = acceptance.bind_evidence(
        current, {"ci:run-1/output": b"42\n", "ci:late-output": b"verified late bytes"}
    )
    assert not acceptance.validate_report(historical, current)["valid"]
    report["validatedRefs"]["acceptance"]["evidenceSet"] = copy.deepcopy(
        current["evidenceSet"]
    )
    report["validatedRefs"]["acceptance"]["evidenceSetDigest"] = current[
        "evidenceSetDigest"
    ]
    assert acceptance.validate_report(report, current)["valid"]
    assert historical["verdict"] == "BLOCKED"


def test_changed_artifact_bytes_cannot_reuse_previously_passed_row(bound):
    report, current = bound
    current = acceptance.bind_evidence(
        current, {"ci:run-1/output": b"failed assertion"}
    )
    assert acceptance.reuse(report, current).get("reusableRows", []) == []


def test_scoped_plan_change_preserves_only_unchanged_rows(bound):
    report, current = bound
    current["verificationMap"][0]["proofMethods"] = ["live_provider"]
    assert acceptance.reuse(report, current).get("reusableRows", []) == []


def test_admission_routes_independent_work_without_repeating_unavailable_setup(bound):
    _, current = bound
    row = current["verificationMap"][0]
    row["capability"] = {
        "status": "unavailable",
        "evidenceRefs": ["probe:gpu"],
        "resumeCheck": "Probe GPU owner",
    }
    current["scope"]["requirementIds"].append("AC-2")
    current["verificationMap"].append(
        {
            **copy.deepcopy(row),
            "id": "AC-2",
            "capability": {
                "status": "ready",
                "evidenceRefs": ["probe:cpu"],
                "resumeCheck": "Run tests",
            },
        }
    )
    current = acceptance.bind_evidence(
        current, {"probe:gpu": b"GPU unavailable", "probe:cpu": b"CPU ready"}
    )
    first = acceptance.admission(current)
    assert first["readyRequirementIds"] == ["AC-2"]
    assert first["blockedRequirementIds"] == ["AC-1"]
    current["verificationMap"][0]["suggestedEvidence"] = ["Different free-form advice"]
    assert not acceptance.admission(current, previous=first)["madeProgress"]
    current["verificationMap"][0]["capability"]["status"] = "ready"
    current = acceptance.bind_evidence(
        current, {"probe:gpu": b"GPU ready", "probe:cpu": b"CPU ready"}
    )
    latest = acceptance.admission(current, previous=first)
    assert latest["madeProgress"] and latest["readyRequirementIds"] == ["AC-1", "AC-2"]


def test_missing_readiness_probe_is_not_assumed_ready(bound):
    _, current = bound
    result = acceptance.admission(current)
    assert result["readyRequirementIds"] == []
    assert result["blockedRequirementIds"] == ["AC-1"]
    assert result["errors"]


def test_legacy_partial_coverage_is_only_an_inspection_candidate(bound):
    _, current = bound
    report = {
        "verdict": "BLOCKED",
        "subject": copy.deepcopy(current["subject"]),
        "scope": copy.deepcopy(current["scope"]),
        "verificationMap": copy.deepcopy(current["verificationMap"]),
        "requirementCoverage": [
            {
                "id": "AC-1",
                "verificationStatus": "VERIFIED",
                "testEvidenceRefs": ["ci:run-1/output"],
            }
        ],
    }
    result = acceptance.reuse(report, current)
    assert not result["reusable"]
    assert result["reusableRows"] == []
    assert result["candidateRows"] == [
        {"requirementId": "AC-1", "evidenceRefs": ["ci:run-1/output"]}
    ]


def test_nonpassing_report_cannot_omit_required_rows_or_call_passed_row_a_gap(bound):
    report, current = bound
    report = waiting(report)
    report["validatedRefs"]["acceptance"]["evidence"][0]["status"] = "VERIFIED"
    assert not acceptance.validate_report(report, current)["valid"]
    report["validatedRefs"]["acceptance"]["evidence"] = []
    current["scope"]["requirementIds"].append("AC-2")
    plan = {**copy.deepcopy(current["verificationMap"][0]), "id": "AC-2"}
    current["verificationMap"].append(plan)
    binding = report["validatedRefs"]["acceptance"]
    binding.update(
        scope=copy.deepcopy(current["scope"]),
        verificationMap=copy.deepcopy(current["verificationMap"]),
    )
    assert not acceptance.validate_report(report, current)["valid"]


def test_current_target_movement_needs_new_judgment_not_new_content_execution(bound):
    report, current = bound
    current["completionTarget"]["revision"] = "new-target-head"
    assert not acceptance.validate_report(report, current)["valid"]
    assert acceptance.reuse(report, current)["reusable"]


def test_new_report_ids_and_probe_bytes_do_not_restart_unchanged_blocked_setup(bound):
    _, current = bound
    current["verificationMap"][0]["capability"] = {
        "status": "unavailable",
        "evidenceRefs": ["probe:1"],
        "resumeCheck": "Probe GPU",
    }
    current = acceptance.bind_evidence(current, {"probe:1": b"unavailable at 1"})
    prior = acceptance.admission(current)
    current["verificationMap"][0]["capability"]["evidenceRefs"] = ["probe:2"]
    current = acceptance.bind_evidence(current, {"probe:2": b"unavailable at 2"})
    assert not acceptance.admission(current, previous=prior)["madeProgress"]


def test_capture_and_admission_cli_bind_executed_bytes_without_reexecuting(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        return subprocess.check_output(
            ["git", "-C", str(repo), *args], stderr=subprocess.PIPE, text=True
        ).strip()

    git("init", "-b", "main")
    git("config", "user.email", "fixture@example.test")
    git("config", "user.name", "Source binding fixture")
    (repo / "app.py").write_text("print(42)\n")
    git("add", ".")
    git("commit", "-m", "candidate")
    source = tmp_path / "source.txt"
    source.write_text("Print 42")
    from test_verification_report import SCRIPT

    capture = [
        sys.executable,
        str(SCRIPT),
        "capture",
        "--repo",
        str(repo),
        "--repository",
        "example/game",
        "--target",
        "main",
        "--source",
        str(source),
        "--source-ref",
        "example/game#1",
        "--requirement",
        "AC-1",
    ]
    current = json.loads(subprocess.check_output(capture, text=True))
    plan = {
        "id": "AC-1",
        "sourceRef": current["scope"]["sourceRef"],
        "sourceDigest": current["scope"]["sourceDigest"],
        "sourceLocator": "line:1",
        "classification": "mandatory",
        "requiredBehavior": "Print 42",
        "executableChecks": ["python app.py"],
        "proofMethods": ["automated_test"],
        "owner": "existing test owner",
        "capability": {
            "status": "ready",
            "evidenceRefs": ["probe:python"],
            "resumeCheck": "Run output assertion",
        },
    }
    assessment = tmp_path / "assessment.json"
    assessment.write_text(
        json.dumps({"scope": current["scope"], "verificationMap": [plan]})
    )
    probe = tmp_path / "probe.txt"
    probe.write_text(subprocess.check_output([sys.executable, "--version"], text=True))
    command = capture + [
        "--assessment",
        str(assessment),
        "--evidence",
        "probe:python",
        str(probe),
    ]
    old = json.loads(subprocess.check_output(command, text=True))
    binding = {
        key: copy.deepcopy(old[key])
        for key in (
            "subject",
            "scope",
            "completionTarget",
            "verificationMap",
            "evidenceSet",
            "evidenceSetDigest",
        )
    }
    binding.update(
        schemaVersion="acceptance/v1", evidence=[], freshness={"policy": "content"}
    )
    report = {
        "verdict": "BLOCKED",
        "recommendedNextAction": "blocked",
        "recoverableInCurrentRuntime": False,
        "validatedRefs": {"acceptance": binding},
        "remainingWork": [
            {
                "requirement": "AC-1",
                "gapType": "verification",
                "remainingWork": "Run the existing output assertion",
            }
        ],
    }
    assert acceptance.validate_report(report, old)["valid"]
    observed = subprocess.check_output(
        [sys.executable, str(repo / "app.py")], text=True
    )
    assert observed == "42\n"
    artifact = tmp_path / "actual-output.txt"
    artifact.write_text(observed)
    current = json.loads(
        subprocess.check_output(
            command + ["--evidence", "test:output", str(artifact)], text=True
        )
    )
    assert not acceptance.validate_report(report, current)["valid"]
    binding.update(
        evidenceSet=current["evidenceSet"],
        evidenceSetDigest=current["evidenceSetDigest"],
    )
    binding["evidence"] = [
        {
            "requirementId": "AC-1",
            "status": "VERIFIED",
            "obligationDigest": acceptance.obligation_digest(plan),
            "proofMethod": "automated_test",
            "evidenceRefs": ["test:output"],
        }
    ]
    report.update(
        verdict="FULLY_IMPLEMENTED", recommendedNextAction="advance", remainingWork=[]
    )
    assert acceptance.validate_report(report, current)["valid"]
    snapshot = tmp_path / "current.json"
    snapshot.write_text(json.dumps(current))
    admission = json.loads(
        subprocess.check_output(
            [sys.executable, str(SCRIPT), "admission", "--current", str(snapshot)],
            text=True,
        )
    )
    assert admission["readyRequirementIds"] == ["AC-1"]
    previous = tmp_path / "admission.json"
    previous.write_text(json.dumps(admission))
    again = json.loads(
        subprocess.check_output(
            [
                sys.executable,
                str(SCRIPT),
                "admission",
                "--current",
                str(snapshot),
                "--previous",
                str(previous),
            ],
            text=True,
        )
    )
    assert again["madeProgress"] is False
    assert git("status", "--porcelain") == ""


def test_prerequisite_identity_and_order_are_normalized(bound):
    _, current = bound
    row = current["verificationMap"][0]
    probe = {
        "status": "ready",
        "evidenceRefs": ["ci:run-1/output"],
        "resumeCheck": "Check capability",
    }
    row["capability"] = copy.deepcopy(probe)
    row["prerequisites"] = [
        {**probe, "id": "gpu", "owner": "GPU owner", "status": "unavailable"},
        {**probe, "id": "content", "owner": "Content owner", "status": "busy"},
    ]
    first = acceptance.admission(current)
    row["prerequisites"].reverse()
    assert not acceptance.admission(current, previous=first)["madeProgress"]
    row["prerequisites"][0]["owner"] = "Alternate authorized owner"
    assert acceptance.admission(current, previous=first)["madeProgress"]


@pytest.mark.parametrize("change", ["id", "owner", "resumeCheck", "duplicate"])
def test_malformed_prerequisite_cannot_be_ready(bound, change):
    _, current = bound
    probe = {
        "status": "ready",
        "evidenceRefs": ["ci:run-1/output"],
        "resumeCheck": "Check capability",
    }
    row = current["verificationMap"][0]
    row["capability"] = copy.deepcopy(probe)
    row["prerequisites"] = [{**probe, "id": "gpu", "owner": "GPU owner"}]
    if change == "duplicate":
        row["prerequisites"] *= 2
    else:
        del row["prerequisites"][0][change]
    result = acceptance.admission(current)
    assert not result["readyRequirementIds"] and result["errors"]


@pytest.mark.parametrize(
    "bad", [None, {"requirementId": []}, {"requirementId": 42}, {"status": []}]
)
def test_malformed_unrelated_row_does_not_discard_bound_passed_row(bound, bad):
    report, current = bound
    report["validatedRefs"]["acceptance"]["evidence"].append(bad)
    result = acceptance.reuse(report, current)
    assert not result["reusable"]
    assert [row["requirementId"] for row in result["reusableRows"]] == ["AC-1"]


def test_strict_report_cannot_downgrade_by_omitting_current_map(bound):
    report, current = bound
    del current["verificationMap"]
    assert not acceptance.validate_report(report, current)["valid"]
    assert not acceptance.reuse(report, current)["reusable"]


@pytest.mark.parametrize("current", [False, 1, [], "bad current"])
def test_scalar_current_is_report_diagnostic_not_crash(bound, current):
    report, _ = bound
    result = acceptance.validate_report(report, current)
    assert not result["valid"] and result["errors"]


def test_scope_reconciliation_preserves_history_and_retires_invented_ids(bound):
    _, current = bound
    previous = copy.deepcopy(current["scope"])
    previous["requirementIds"].append("PARENT-PHYSICAL")
    provenance = {
        "previousScope": previous,
        "currentScope": copy.deepcopy(current["scope"]),
        "removedRequirements": [
            {
                "id": "PARENT-PHYSICAL",
                "reason": "Physical rehearsal belongs to separate release work",
                "sourceLocator": "exclusions[0]",
            }
        ],
    }
    plan = {
        "scope": copy.deepcopy(current["scope"]),
        "verificationMap": copy.deepcopy(current["verificationMap"]),
        "scopeReconciliation": provenance,
    }
    result = acceptance.bind_verification_map(current, plan)
    assert result["scopeReconciliation"] == provenance
    assert previous["requirementIds"] == ["AC-1", "PARENT-PHYSICAL"]
    plan["scopeReconciliation"]["removedRequirements"] = []
    with pytest.raises(ValueError):
        acceptance.bind_verification_map(current, plan)


def test_source_quote_checks_original_bytes_without_inventing_source_format(bound):
    _, current = bound
    source = b"Implement the output check. Physical event rehearsal is separate release work."
    plan = {
        "scope": copy.deepcopy(current["scope"]),
        "verificationMap": copy.deepcopy(current["verificationMap"]),
    }
    plan["verificationMap"][0]["sourceQuote"] = "Implement the output check."
    result = acceptance.bind_verification_map(current, plan, source=source)
    assert result["verificationMap"][0]["sourceQuote"] == "Implement the output check."
    with pytest.raises(ValueError):
        acceptance.bind_verification_map(current, plan, source=b"different source")
    plan["verificationMap"][0][
        "sourceQuote"
    ] = "The child requires a physical rehearsal."
    with pytest.raises(ValueError):
        acceptance.bind_verification_map(current, plan, source=source)


@pytest.mark.parametrize(
    "pointer,expected",
    [
        ("", None),
        ("/description", "quoted source"),
        ("/a~1b/~0field", "nested source"),
        ("/parts/0", "first"),
    ],
)
def test_source_selector_uses_only_explicit_original_text(tmp_path, pointer, expected):
    path = tmp_path / "brief.json"
    raw = json.dumps(
        {
            "description": "quoted source",
            "a/b": {"~field": "nested source"},
            "parts": ["first"],
        }
    ).encode()
    path.write_bytes(raw)
    assert acceptance.source_bytes(path, pointer) == (
        raw if expected is None else expected.encode()
    )


@pytest.mark.parametrize(
    "pointer", ["description", "/parts", "/parts/00", "/bad~2escape"]
)
def test_source_selector_rejects_ambiguous_format(tmp_path, pointer):
    path = tmp_path / "brief.json"
    path.write_text(
        json.dumps({"description": "source", "parts": ["first"], "bad~2escape": "bad"})
    )
    with pytest.raises((ValueError, KeyError)):
        acceptance.source_bytes(path, pointer)


def test_current_reconciliation_cannot_be_omitted_from_report(bound):
    report, current = bound
    previous = copy.deepcopy(current["scope"])
    previous["requirementIds"].append("PARENT")
    current["scopeReconciliation"] = {
        "previousScope": previous,
        "currentScope": copy.deepcopy(current["scope"]),
        "removedRequirements": [
            {
                "id": "PARENT",
                "reason": "Separate release",
                "sourceLocator": "exclusions",
            }
        ],
    }
    assert not acceptance.validate_report(report, current)["valid"]
    report["validatedRefs"]["acceptance"]["scopeReconciliation"] = copy.deepcopy(
        current["scopeReconciliation"]
    )
    assert acceptance.validate_report(report, current)["valid"]


@pytest.mark.parametrize(
    "status,field",
    [("busy", "waitingRequirementIds"), ("unauthorized", "blockedRequirementIds")],
)
def test_busy_or_unauthorized_capability_is_never_ready(bound, status, field):
    _, current = bound
    current["verificationMap"][0]["capability"] = {
        "status": status,
        "evidenceRefs": ["ci:run-1/output"],
        "resumeCheck": "Probe existing owner",
    }
    result = acceptance.admission(current)
    assert result[field] == ["AC-1"] and result["readyRequirementIds"] == []


def two_bound_rows(bound):
    report, current = bound
    current["scope"]["requirementIds"].append("AC-2")
    current["verificationMap"].append(
        {**copy.deepcopy(current["verificationMap"][0]), "id": "AC-2"}
    )
    binding = report["validatedRefs"]["acceptance"]
    binding.update(
        scope=copy.deepcopy(current["scope"]),
        verificationMap=copy.deepcopy(current["verificationMap"]),
    )
    binding["evidence"].append(
        {
            **copy.deepcopy(binding["evidence"][0]),
            "requirementId": "AC-2",
            "obligationDigest": acceptance.obligation_digest(
                current["verificationMap"][1]
            ),
        }
    )
    return report, current


def test_partial_reuse_excludes_contradictory_gap_and_keeps_unrelated_pass(bound):
    report, current = two_bound_rows(bound)
    report.update(
        verdict="BLOCKED",
        recommendedNextAction="blocked",
        remainingWork=[
            {
                "requirement": "AC-1",
                "gapType": "implementation",
                "remainingWork": "Actual production output fails",
            }
        ],
    )
    assert not acceptance.validate_report(report, current)["valid"]
    result = acceptance.reuse(report, current)
    assert not result["reusable"] and not result["completionEligible"]
    assert [row["requirementId"] for row in result["reusableRows"]] == ["AC-2"]


def test_conflicting_gap_id_fields_cannot_hide_defect(bound):
    report, current = two_bound_rows(bound)
    binding = report["validatedRefs"]["acceptance"]
    binding["evidence"] = binding["evidence"][:1]
    report.update(
        verdict="BLOCKED",
        recommendedNextAction="blocked",
        remainingWork=[
            {
                "requirement": "AC-1",
                "requirementIds": ["AC-2"],
                "gapType": "implementation",
                "remainingWork": "Actual AC-1 production output fails",
            }
        ],
    )
    assert not acceptance.validate_report(report, current)["valid"]
    assert acceptance.reuse(report, current)["reusableRows"] == []


def test_opaque_only_gap_handoff_cannot_certify_individual_passes(bound):
    report, current = bound
    report.update(
        verdict="BLOCKED",
        recommendedNextAction="blocked",
        remainingWorkRef="artifact:unknown-gaps",
    )
    assert acceptance.reuse(report, current)["reusableRows"] == []


def reconciled_rows(bound):
    report, current = two_bound_rows(bound)
    previous = copy.deepcopy(current["scope"])
    current["scope"]["requirementIds"] = ["AC-1"]
    current["verificationMap"] = current["verificationMap"][:1]
    current["scopeReconciliation"] = {
        "previousScope": previous,
        "currentScope": copy.deepcopy(current["scope"]),
        "removedRequirements": [
            {
                "id": "AC-2",
                "reason": "Inherited parent epic gate is outside child scope",
                "sourceLocator": "exclusions",
            }
        ],
    }
    return report, current


def test_valid_scope_retirement_keeps_unchanged_passed_row_not_old_aggregate(bound):
    report, current = reconciled_rows(bound)
    before = copy.deepcopy(report)
    result = acceptance.reuse(report, current)
    assert not result["reusable"] and not result["completionEligible"]
    assert [row["requirementId"] for row in result["reusableRows"]] == ["AC-1"]
    assert report == before
    assert not acceptance.validate_report(report, current)["valid"]
    binding = report["validatedRefs"]["acceptance"]
    legacy = {
        "verdict": "BLOCKED",
        "subject": binding["subject"],
        "scope": binding["scope"],
        "verificationMap": binding["verificationMap"],
        "requirementCoverage": [
            {
                "id": "AC-1",
                "verificationStatus": "VERIFIED",
                "testEvidenceRefs": ["ci:run-1/output"],
            }
        ],
    }
    assert acceptance.reuse(legacy, current)["candidateRows"] == [
        {"requirementId": "AC-1", "evidenceRefs": ["ci:run-1/output"]}
    ]


@pytest.mark.parametrize(
    "change",
    ["missing", "previous", "current", "removed", "source", "obligation", "bytes"],
)
def test_scope_retirement_needs_exact_lineage_and_unchanged_row_proof(bound, change):
    report, current = reconciled_rows(bound)
    if change == "missing":
        del current["scopeReconciliation"]
    elif change == "previous":
        current["scopeReconciliation"]["previousScope"]["requirementIds"].append("AC-3")
    elif change == "current":
        current["scopeReconciliation"]["currentScope"]["requirementIds"] = ["WRONG"]
    elif change == "removed":
        current["scopeReconciliation"]["removedRequirements"] = []
    elif change == "source":
        current["scope"]["sourceDigest"] = "sha256:changed"
    elif change == "obligation":
        current["verificationMap"][0]["proofMethods"] = ["live_provider"]
    else:
        current = acceptance.bind_evidence(
            current, {"ci:run-1/output": b"changed bytes"}
        )
    assert acceptance.reuse(report, current).get("reusableRows", []) == []


@pytest.mark.parametrize(
    "extra",
    [
        ["--evidence", "test:ref", "/missing/evidence"],
        ["--source-artifact-ref", "artifact:brief"],
    ],
)
def test_capture_rejects_strict_inputs_without_map_before_git_work(tmp_path, extra):
    from test_verification_report import SCRIPT

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "capture",
            "--repo",
            str(tmp_path / "not-a-repo"),
            "--repository",
            "example/game",
            "--target",
            "main",
            "--source",
            str(tmp_path / "missing-source"),
            "--source-ref",
            "example/game#1",
            "--requirement",
            "AC-1",
            *extra,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "--assessment" in result.stderr
    assert not result.stdout


def test_success_with_blocking_gap_cannot_reuse_aggregate_or_contradicted_row(bound):
    report, current = two_bound_rows(bound)
    report["remainingWork"] = [
        {
            "requirement": "AC-1",
            "gapType": "implementation",
            "remainingWork": "Production assertion fails",
        }
    ]
    result = acceptance.reuse(report, current)
    assert not result["reusable"]
    assert [row["requirementId"] for row in result["reusableRows"]] == ["AC-2"]


def test_consistent_multiple_gap_ids_remain_valid(bound):
    report, current = two_bound_rows(bound)
    binding = report["validatedRefs"]["acceptance"]
    binding["evidence"] = []
    report.update(
        verdict="BLOCKED",
        recommendedNextAction="blocked",
        remainingWork=[
            {
                "requirement": "AC-1",
                "requirementIds": ["AC-1", "AC-2"],
                "gapType": "verification",
                "remainingWork": "Collect shared proof",
            }
        ],
    )
    assert acceptance.validate_report(report, current)["valid"]


def test_malformed_verified_neighbor_does_not_discard_unrelated_pass(bound):
    report, current = bound
    report["validatedRefs"]["acceptance"]["evidence"].append(
        {"requirementId": [], "status": "VERIFIED"}
    )
    assert [
        row["requirementId"]
        for row in acceptance.reuse(report, current)["reusableRows"]
    ] == ["AC-1"]


@pytest.mark.parametrize(
    "verdict", ["BLOCKED", "NO_DETERMINATION", "ADDITIONAL_WORK_NEEDED", "UNKNOWN"]
)
@pytest.mark.parametrize("work", ["absent", None, [], {}])
def test_unexplained_nonpass_cannot_certify_partial_rows(bound, verdict, work):
    report, current = bound
    report.update(verdict=verdict, recommendedNextAction="blocked")
    if work != "absent":
        report["remainingWork"] = work
    assert not acceptance.validate_report(report, current)["valid"]
    result = acceptance.reuse(report, current)
    assert not result["reusable"] and not result["completionEligible"]
    assert result["reusableRows"] == []


@pytest.mark.parametrize(
    "change",
    [
        "unknown",
        "optional",
        "separate_release",
        "unknown_in_list",
        "conflicting_ids",
        "duplicate_ids",
        "empty_ids",
        "scalar_ids",
        "missing_primary",
        "narrative_primary",
        "missing_gap_type",
        "blank_gap_type",
        "missing_work",
        "blank_work",
        "malformed_item",
        "wrong_candidate",
        "mixed_unknown",
        "unknown_verdict",
    ],
)
def test_invalid_source_linked_handoff_never_certifies_partial_rows(bound, change):
    report, current = two_bound_rows(bound)
    binding = report["validatedRefs"]["acceptance"]
    binding["evidence"] = binding["evidence"][:1]
    gap = {
        "requirement": "AC-2",
        "gapType": "verification",
        "remainingWork": "Collect the required second proof",
    }
    report.update(
        verdict="BLOCKED", recommendedNextAction="blocked", remainingWork=[gap]
    )
    if change == "unknown":
        gap["requirement"] = "UNSOURCED"
    elif change in {"optional", "separate_release"}:
        plan = {
            **copy.deepcopy(current["verificationMap"][0]),
            "id": "DIAGNOSTIC",
            "classification": change,
        }
        current["verificationMap"].append(plan)
        binding["verificationMap"].append(copy.deepcopy(plan))
        gap["requirement"] = "DIAGNOSTIC"
    elif change == "unknown_in_list":
        gap["requirementIds"] = ["AC-2", "UNSOURCED"]
    elif change == "conflicting_ids":
        gap["requirementIds"] = ["AC-1"]
    elif change == "duplicate_ids":
        gap["requirementIds"] = ["AC-2", "AC-2"]
    elif change == "empty_ids":
        gap["requirementIds"] = []
    elif change == "scalar_ids":
        gap["requirementIds"] = "AC-2"
    elif change == "missing_primary":
        del gap["requirement"]
    elif change == "narrative_primary":
        gap.update(requirement="AC-2 is the missing check", requirementIds=["AC-2"])
    elif change == "missing_gap_type":
        del gap["gapType"]
    elif change == "blank_gap_type":
        gap["gapType"] = " "
    elif change == "missing_work":
        del gap["remainingWork"]
    elif change == "blank_work":
        gap["remainingWork"] = " "
    elif change == "malformed_item":
        report["remainingWork"].append(None)
    elif change == "wrong_candidate":
        gap["candidate"] = {**current["subject"], "revision": "different-head"}
    elif change == "mixed_unknown":
        report["remainingWork"].append({**gap, "requirement": "UNSOURCED"})
    else:
        report["verdict"] = "UNKNOWN"
    assert not acceptance.validate_report(report, current)["valid"]
    result = acceptance.reuse(report, current)
    assert not result["reusable"] and not result["completionEligible"]
    assert result["reusableRows"] == []


def test_source_linked_partial_handoff_retains_only_valid_passed_row(bound):
    report, current = two_bound_rows(bound)
    binding = report["validatedRefs"]["acceptance"]
    binding["evidence"] = binding["evidence"][:1]
    report.update(
        verdict="BLOCKED",
        recommendedNextAction="blocked",
        remainingWork=[
            {
                "requirement": "AC-2",
                "requirementIds": ["AC-2"],
                "gapType": "verification",
                "remainingWork": "Collect the required second proof",
                "candidate": copy.deepcopy(current["subject"]),
            }
        ],
    )
    assert acceptance.validate_report(report, current)["valid"]
    assert [
        r["requirementId"] for r in acceptance.reuse(report, current)["reusableRows"]
    ] == ["AC-1"]


def test_reconciled_removed_gap_uses_historical_source_scope_not_unknown_scope(bound):
    report, current = reconciled_rows(bound)
    report["validatedRefs"]["acceptance"]["evidence"] = report["validatedRefs"][
        "acceptance"
    ]["evidence"][:1]
    report.update(
        verdict="BLOCKED",
        recommendedNextAction="blocked",
        remainingWork=[
            {
                "requirement": "AC-2",
                "gapType": "environment",
                "remainingWork": "Inherited physical event unavailable",
            }
        ],
    )
    assert not acceptance.validate_report(report, current)["valid"]
    result = acceptance.reuse(report, current)
    assert not result["reusable"] and not result["completionEligible"]
    assert [row["requirementId"] for row in result["reusableRows"]] == ["AC-1"]
    del current["scopeReconciliation"]
    assert acceptance.reuse(report, current)["reusableRows"] == []


@pytest.mark.parametrize("reference", ["", " ", [], {}, 0, False])
def test_malformed_gap_reference_is_never_an_empty_success_or_valid_partial_handoff(
    bound, reference
):
    report, current = bound
    report["remainingWorkRef"] = reference
    assert not acceptance.validate_report(report, current)["valid"]
    result = acceptance.reuse(report, current)
    assert not result["reusable"] and result["reusableRows"] == []
