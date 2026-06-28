from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "bundle"


def test_exported_scripts_exist_and_are_bash() -> None:
    manifest = yaml.safe_load((BUNDLE / "moonspec.bundle.yaml").read_text())

    for script in manifest["exports"]["scripts"]:
        path = BUNDLE / script["path"]
        assert path.exists()
        assert path.read_text().startswith("#!/usr/bin/env bash")
