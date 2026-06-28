from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PlannedFile:
    source: Path
    target: Path


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def _planned_files(bundle_root: Path, projection_name: str, target_root: Path) -> list[PlannedFile]:
    manifest = _load_yaml(bundle_root / "moonspec.bundle.yaml")
    projection = manifest.get("projections", {}).get(projection_name)
    if not isinstance(projection, dict) or not isinstance(projection.get("path"), str):
        raise ValueError(f"unknown projection {projection_name!r}")
    recipe = _load_yaml(bundle_root / projection["path"])
    mappings = recipe.get("mappings")
    if not isinstance(mappings, list):
        raise ValueError(f"{projection_name} projection has no mappings")

    files: list[PlannedFile] = []
    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise ValueError("projection mappings must be mappings")
        source = bundle_root / str(mapping.get("from", ""))
        target = target_root / str(mapping.get("to", ""))
        if mapping.get("mode") == "file":
            files.append(PlannedFile(source=source, target=target))
        elif mapping.get("mode") == "directory":
            for child in sorted(source.rglob("*")):
                if child.is_file():
                    files.append(
                        PlannedFile(source=child, target=target / child.relative_to(source))
                    )
        else:
            raise ValueError(f"unsupported projection mode {mapping.get('mode')!r}")
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project MoonSpec bundle assets")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--projection", default="moonmind")
    parser.add_argument("--target", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    bundle_root = args.source.resolve() / "bundle"
    target_root = args.target.resolve()
    try:
        files = _planned_files(bundle_root, args.projection, target_root)
        if args.write:
            for item in files:
                item.target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item.source, item.target)
        drift = [
            str(item.target)
            for item in files
            if not item.target.is_file()
            or not filecmp.cmp(item.source, item.target, shallow=False)
        ]
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if drift:
        print("MoonSpec projection drift detected:", file=sys.stderr)
        for path in drift:
            print(f"  {path}", file=sys.stderr)
        return 1
    print("MoonSpec projection is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
