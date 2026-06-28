from pathlib import Path

from tools.validate_bundle import validate_bundle

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
