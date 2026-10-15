from pathlib import Path


BUNDLE = Path(__file__).resolve().parents[1] / "bundle"


def test_verify_skill_accepts_source_direct_baselines_without_feature_artifacts(
) -> None:
    text = (BUNDLE / "skills/moonspec-verify/SKILL.md").read_text(encoding="utf-8")

    assert "Treat the user's instructions as a valid verification baseline" in text
    assert "referenced declarative document as a valid verification baseline" in text
    assert "In source-direct verification mode" in text
    assert "Do not require a MoonSpec feature directory" in text
    assert "their absence is never by itself a verification gap" in text
    assert "--json --paths-only" in text
    assert "--require-tasks" not in text
    assert "rebuild every controlling" in text
    assert "classification from the current repository head" in text
    assert "results from a path the repository forbids" in text


def test_verify_command_does_not_preflight_require_feature_artifacts() -> None:
    text = (BUNDLE / "commands/markdown/moonspec.verify.md").read_text(
        encoding="utf-8"
    )

    assert "scripts:" not in text
    assert "original instructions or authoritative declarative source" in text
    assert "Do not require `spec.md`, `plan.md`, or `tasks.md`" in text
    assert "--require-tasks" not in text


def test_browser_exception_honors_applicable_agent_guidance_without_promoting_docs():
    for path in ("SKILL.md", "references/acceptance-policy.md"):
        text = " ".join((BUNDLE / "skills/moonspec-verify" / path).read_text().split())
        assert "applicable root or scoped `AGENTS.md` instructions" in text
        assert "Merely naming a browser suite" in text


def test_unverified_producer_contract_is_nonblocking_and_disclosed():
    assess = (BUNDLE / "skills/moonspec-assess/SKILL.md").read_text()
    verify = (BUNDLE / "skills/moonspec-verify/SKILL.md").read_text()
    policy = (BUNDLE / "skills/moonspec-verify/references/acceptance-policy.md").read_text()
    assert "required-unverified row" not in assess
    assert "Unverified criteria are disclosure-only" in assess
    statuses = verify.split("Use these statuses:", 1)[1].split("Rules:", 1)[0]
    assert "`UNVERIFIED`" in statuses and "reason" in statuses and "verifiableBy" in statuses
    assert "VERIFIED/PARTIAL/MISSING/CONFLICT/UNVERIFIED/NO_DETERMINATION" in verify
    assert "VERIFIED/PARTIAL/MISSING/CONFLICT/NO_DETERMINATION" not in verify
    assert "Unverified rows must not appear in `remainingWork`" in policy
    assert "Passed rows plus gap IDs" not in policy
    assert "valid Unverified rows, and source-linked remaining work" in " ".join(policy.split())


def test_assessment_unverified_disclosure_survives_task_generation_contract():
    assess = (BUNDLE / "skills/moonspec-assess/SKILL.md").read_text()
    tasks = (BUNDLE / "skills/moonspec-tasks/SKILL.md").read_text()
    assert "Unverified criteria are disclosure-only" in assess
    assert "Unverified criteria are disclosure-only" in tasks
    assert "required-unverified row must map" not in tasks
    assert "outside executable tasks" in tasks
    assert "reason and verifiableBy" in tasks


def test_unverified_evidence_does_not_waive_required_permission():
    verify = " ".join((BUNDLE / "skills/moonspec-verify/SKILL.md").read_text().split())
    policy = " ".join((BUNDLE / "skills/moonspec-verify/references/acceptance-policy.md").read_text().split())
    for text in (verify, policy):
        assert "Unverified does not grant permission" in text
        assert "actual missing authorization or operator decision needed to act" in text
        assert "Do not invent an authority gate" in text


def test_assessor_preserves_actual_authority_exception():
    assess = " ".join((BUNDLE / "skills/moonspec-assess/SKILL.md").read_text().split())
    assert "actual missing authorization or operator decision needed to act" in assess
    assert "`needs_human`" in assess
    assert "Do not invent an authority gate" in assess
    assert "Separately scoped release approvals do not gate implementation completion" in assess


def test_assess_plan_tasks_preserve_unverified_status_before_task_coverage():
    for skill in ("assess", "plan", "tasks"):
        text = (BUNDLE / f"skills/moonspec-{skill}/SKILL.md").read_text()
        assert "Unverified criteria are disclosure-only" in text
        assert "reason and verifiableBy" in text
    plan = (BUNDLE / "skills/moonspec-plan/SKILL.md").read_text()
    tasks = (BUNDLE / "skills/moonspec-tasks/SKILL.md").read_text()
    for text in (plan, tasks):
        assert "`unverified`: disclosure-only" in text
        assert "takes precedence over `implemented_unverified`" in text
        assert "no test, verification, or fallback implementation tasks" in text
        assert "Observed defects still require remediation" in text
    assert "`unverified` -> disclosure only" in plan
    assert "`unverified`: disclosure only" in plan
    assert "Coverage rules below apply only to executable rows" in tasks


def test_tasks_coverage_and_final_validation_exclude_disclosure_only_rows():
    text = (BUNDLE / "skills/moonspec-tasks/SKILL.md").read_text()
    validation = text.split("## Validation\n", 1)[1].split("## Report\n", 1)[0]
    assert "Every executable traceability inventory row has task coverage" in validation
    assert "Every traceability inventory row has task coverage" not in validation
    assert "For executable rows, acceptance scenarios" in text
    assert "Coverage rules below apply only to executable rows" in text
    assert "disclosure-only Unverified counts" in text


def test_all_unverified_task_contract_has_no_mandatory_test_or_setup_work():
    tasks = (BUNDLE / "skills/moonspec-tasks/SKILL.md").read_text()
    assert "When every row is `unverified`, retain disclosures and the final report verification task only" in tasks
    for obsolete in (
        "- Unit tests and integration tests are required.",
        "- Include red-first confirmation tasks.",
        "Include project initialization and tool configuration:",
        "- Red-first confirmation tasks exist before production code tasks.",
        "Create exactly one story phase. Include:",
    ):
        assert obsolete not in tasks
    assert "When production code tasks exist" in tasks
    assert "Remove unused sample tasks" in tasks


def test_assessment_status_and_metadata_contract_reaches_all_consumers():
    assess = (BUNDLE / "skills/moonspec-assess/SKILL.md").read_text()
    assert "`unverifiable` rows must include `unverified: {reason, verifiableBy}`" in assess
    assert "`UNVERIFIED` rows use the same disclosure object" in assess
    for skill in ("plan", "tasks", "verify"):
        text = (BUNDLE / f"skills/moonspec-{skill}/SKILL.md").read_text()
        assert "`unverifiable`" in text and "`UNVERIFIED`" in text
        assert "unverified.reason" in text and "unverified.verifiableBy" in text


def test_verify_binding_allows_disclosure_instead_of_evidence():
    text = (BUNDLE / "skills/moonspec-verify/SKILL.md").read_text()
    binding = text.split("## Evidence binding", 1)[1].split("## Report", 1)[0]
    assert "or a valid Unverified disclosure" in binding
    assert "no evidence refs" in binding
