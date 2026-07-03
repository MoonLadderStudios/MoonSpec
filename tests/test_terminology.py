from pathlib import Path

from tools.validate_bundle import FORBIDDEN_PATTERNS, validate_bundle

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "bundle"


def test_bundle_validator_passes() -> None:
    validate_bundle()


def test_active_bundle_files_use_moonspec_identity() -> None:
    forbidden = ("/speckit.", "speckit-", "speckit_", "/agentkit.", "agentkit-")
    for path in BUNDLE.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".yaml", ".yml", ".toml", ".sh"}:
            if path.relative_to(BUNDLE) == Path("projections/moonmind.yaml"):
                continue
            text = path.read_text()
            for token in forbidden:
                assert token not in text, f"{token} found in {path}"


def test_retired_doc_gate_patterns_catch_legacy_wording() -> None:
    samples = {
        "retired doc gate wording": (
            "factually wrong against the verified implementation",
            "the implementation deliberately and correctly diverged",
        ),
        "retired doc defect wording": (
            "the document is wrong, incomplete, or internally inconsistent",
            "the evidence shows that document is incomplete or wrong",
        ),
        "retired story-reconcile reference": (
            "doc-drift notes from a story-reconcile-implementation report",
        ),
    }
    for label, texts in samples.items():
        pattern = FORBIDDEN_PATTERNS[label]
        for text in texts:
            assert pattern.search(text), f"{label} should match: {text}"


def test_standalone_constitution_pattern_catches_legacy_path_forms() -> None:
    pattern = FORBIDDEN_PATTERNS["standalone constitution path"]
    legacy_paths = (
        ".specify/memory/constitution.md",
        ".specify/memory/constitution",
        r".specify\memory\constitution.md",
        r".specify\memory\constitution",
    )
    for legacy_path in legacy_paths:
        assert pattern.search(legacy_path)
