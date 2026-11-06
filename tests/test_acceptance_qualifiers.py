"""Exercise reporting acceptance and disclosures through the portable contract.

The verifier classifies the source; these checks exercise its resulting handoff,
not a natural-language classifier or a specialist assurance claim.
"""

import copy
import json
import subprocess
import sys

import pytest

from test_portable_acceptance import acceptance, git


@pytest.fixture
def reporting_candidate(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Reporting fixture")
    git(repo, "config", "user.email", "fixture@example.test")
    (repo / "report.py").write_text("print('not implemented')\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "baseline")
    git(repo, "switch", "-c", "implementation")
    (repo / "report.py").write_text(
        "import json\n"
        "print(json.dumps({'observations': ['reviewed'], "
        "'statistics': ['diagnostics passed'], 'externalAssurance': "
        "{'status': 'Unverified', 'reason': 'No specialist report supplied', "
        "'verifiableBy': 'Accredited specialist'}}))\n"
    )
    git(repo, "commit", "-am", "separate report evidence")
    observed = subprocess.check_output([sys.executable, str(repo / "report.py")])
    result = json.loads(observed)
    assert result["observations"] == ["reviewed"]
    assert result["statistics"] == ["diagnostics passed"]
    assert result["externalAssurance"]["status"] == "Unverified"

    source = (
        b"Reports keep observations, statistics and external assurance separate. "
        b"Unavailable specialist verification remains Unverified rather than "
        b"blocking implementation completion."
    )
    current = acceptance.capture(repo, "example/reports", "main")
    current["scope"] = acceptance.scope(
        source, "example/reports#42", ["REPORT-1"], complete=True
    )
    current["freshnessPolicy"] = "content"
    plan = {
        "id": "REPORT-1",
        "sourceRef": current["scope"]["sourceRef"],
        "sourceDigest": current["scope"]["sourceDigest"],
        "sourceLocator": "acceptance[0]",
        "sourceQuote": source.decode(),
        "classification": "mandatory",
        "requiredBehavior": "Separate evidence and disclose unavailable assurance",
        "executableChecks": ["python report.py"],
        "proofMethods": ["public_fixture"],
        "owner": "existing automated runner",
    }
    previous = copy.deepcopy(current["scope"])
    previous["requirementIds"].append("REPORT-1-EXT")
    assessment = {
        "scope": copy.deepcopy(current["scope"]),
        "verificationMap": [plan],
        "scopeReconciliation": {
            "previousScope": previous,
            "currentScope": copy.deepcopy(current["scope"]),
            "removedRequirements": [
                {
                    "id": "REPORT-1-EXT",
                    "reason": "Source requires disclosure, not obtaining assurance",
                    "sourceLocator": "acceptance[0]",
                }
            ],
        },
    }
    current = acceptance.bind_verification_map(current, assessment, source=source)
    current = acceptance.bind_evidence(current, {"fixture:report": observed})
    binding = {
        key: copy.deepcopy(current[key])
        for key in (
            "subject",
            "scope",
            "completionTarget",
            "verificationMap",
            "scopeReconciliation",
            "evidenceSet",
            "evidenceSetDigest",
        )
    }
    binding.update(
        schemaVersion="acceptance/v1",
        freshness={"policy": "content"},
        evidence=[
            {
                "requirementId": "REPORT-1",
                "status": "VERIFIED",
                "obligationDigest": acceptance.obligation_digest(plan),
                "evidenceRefs": ["fixture:report"],
                "proofMethod": "public_fixture",
            }
        ],
    )
    report = {
        "verdict": "FULLY_IMPLEMENTED",
        "recommendedNextAction": "advance",
        "recoverableInCurrentRuntime": True,
        "validatedRefs": {"acceptance": binding},
        "unverifiedCriteria": [result["externalAssurance"]],
    }
    return repo, current, report


def test_disclosed_external_assurance_does_not_veto_implementation_or_landing(
    reporting_candidate,
):
    repo, current, report = reporting_candidate
    assert acceptance.validate_report(report, current) == {"valid": True, "errors": []}
    assert not acceptance.reuse(report, current)["completionEligible"]
    assert report["unverifiedCriteria"][0]["status"] == "Unverified"
    # Closing remains downstream of actual landing, not specialist signoff.
    git(repo, "update-ref", "refs/heads/main", current["subject"]["revision"])
    current.update(
        acceptance.capture(repo, "example/reports", "main", target_mode=True)
    )
    assert acceptance.reuse(report, current)["completionEligible"]


@pytest.mark.parametrize("defect", ["invented_external_gate", "failed_reporting"])
def test_disclosures_do_not_restore_invented_gates_or_hide_report_defects(
    reporting_candidate, defect
):
    _, current, report = reporting_candidate
    if defect == "invented_external_gate":
        report.update(verdict="BLOCKED", recommendedNextAction="blocked")
        report["remainingWork"] = [
            {
                "requirement": "REPORT-1-EXT",
                "gapType": "verification",
                "remainingWork": "Obtain a specialist report",
            }
        ]
    else:
        report["validatedRefs"]["acceptance"]["evidence"][0]["status"] = "FAILED"
    assert not acceptance.validate_report(report, current)["valid"]
