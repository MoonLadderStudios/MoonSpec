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
