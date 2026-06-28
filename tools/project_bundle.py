#!/usr/bin/env python3
from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ROOT = REPO_ROOT / "bundle"
MANIFEST_PATH = BUNDLE_ROOT / "moonspec.bundle.yaml"


@dataclass(frozen=True)
class PlannedFile:
    source: Path
    target: Path


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def resolve_projection(name: str) -> Path:
    manifest = load_yaml(MANIFEST_PATH)
    projections = manifest.get("projections")
    if not isinstance(projections, dict) or name not in projections:
        raise ValueError(f"unknown projection {name!r}")
    projection = projections[name]
    if not isinstance(projection, dict) or not isinstance(projection.get("path"), str):
        raise ValueError(f"projection {name!r} must define path")
    return BUNDLE_ROOT / projection["path"]


def planned_files(projection_path: Path, target_root: Path) -> list[PlannedFile]:
    recipe = load_yaml(projection_path)
    mappings = recipe.get("mappings")
    if not isinstance(mappings, list):
        raise ValueError(f"{projection_path} must define mappings")

    files: list[PlannedFile] = []
    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise ValueError(f"{projection_path} mappings must be mappings")
        mode = mapping.get("mode")
        source = BUNDLE_ROOT / str(mapping.get("from", ""))
        target = target_root / str(mapping.get("to", ""))
        if mode == "file":
            files.append(PlannedFile(source=source, target=target))
        elif mode == "directory":
            for child in sorted(source.rglob("*")):
                if child.is_file():
                    files.append(
                        PlannedFile(
                            source=child,
                            target=target / child.relative_to(source),
                        )
                    )
        else:
            raise ValueError(f"unsupported mapping mode {mode!r}")
    return files


def check_projection(files: list[PlannedFile]) -> list[str]:
    drift: list[str] = []
    for item in files:
        if not item.target.is_file():
            drift.append(f"missing: {item.target}")
            continue
        if not filecmp.cmp(item.source, item.target, shallow=False):
            drift.append(f"stale: {item.target}")
    return drift


def write_projection(files: list[PlannedFile]) -> None:
    for item in files:
        item.target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item.source, item.target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project MoonSpec bundle assets")
    parser.add_argument("--projection", default="moonmind")
    parser.add_argument("--target", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    try:
        projection_path = resolve_projection(args.projection)
        files = planned_files(projection_path, args.target.resolve())
        if args.write:
            write_projection(files)
        drift = check_projection(files)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if drift:
        print("MoonSpec projection drift detected:", file=sys.stderr)
        for item in drift:
            print(f"  {item}", file=sys.stderr)
        return 1

    print("MoonSpec projection is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
