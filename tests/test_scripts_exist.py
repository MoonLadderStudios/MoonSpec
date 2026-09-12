from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "bundle"


def test_exported_scripts_exist_and_have_portable_interpreters() -> None:
    manifest = yaml.safe_load((BUNDLE / "moonspec.bundle.yaml").read_text())

    for script in manifest["exports"]["scripts"]:
        path = BUNDLE / script["path"]
        assert path.exists()
        interpreter = {".sh": "bash", ".py": "python3"}[path.suffix]
        assert path.read_text().startswith(f"#!/usr/bin/env {interpreter}")
