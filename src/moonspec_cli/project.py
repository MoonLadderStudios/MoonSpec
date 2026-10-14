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


@dataclass(frozen=True)
class Projection:
    files: list[PlannedFile]
    owned_scopes: dict[Path, tuple[str, str]]


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def _target_path(target_root: Path, path: Path, *, file: bool = False) -> Path:
    if not path.resolve().is_relative_to(target_root):
        raise ValueError(f"projection target escapes consumer: {path}")
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            raise ValueError(f"projection target contains a symlink: {ancestor}")
        if ancestor == target_root:
            break
    if file and path.is_dir():
        raise ValueError(f"directory blocks projected file: {path}")
    return path


def _planned_files(
    bundle_root: Path, projection_name: str, target_root: Path
) -> Projection:
    manifest = _load_yaml(bundle_root / "moonspec.bundle.yaml")
    projection = manifest.get("projections", {}).get(projection_name)
    if not isinstance(projection, dict) or not isinstance(projection.get("path"), str):
        raise ValueError(f"unknown projection {projection_name!r}")
    recipe = _load_yaml(bundle_root / projection["path"])
    mappings = recipe.get("mappings")
    if not isinstance(mappings, list):
        raise ValueError(f"{projection_name} projection has no mappings")

    files: list[PlannedFile] = []
    owned_scopes: dict[Path, tuple[str, str]] = {}
    identity = manifest.get("identity", {})
    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise ValueError("projection mappings must be mappings")
        source = bundle_root / str(mapping.get("from", ""))
        if not source.resolve().is_relative_to(bundle_root):
            raise ValueError(f"projection source escapes bundle: {source}")
        target = _target_path(target_root, target_root / str(mapping.get("to", "")))
        if mapping.get("mode") == "file":
            files.append(
                PlannedFile(
                    source=source, target=_target_path(target_root, target, file=True)
                )
            )
        elif mapping.get("mode") == "directory":
            if not source.is_dir():
                raise ValueError(f"missing projection source directory: {source}")
            source_rel = source.relative_to(bundle_root)
            if source_rel == Path("skills"):
                prefix = identity.get("skillPrefix")
                kind = "skill-directory"
            elif source_rel.parts[0] == "commands":
                prefix = str(identity.get("commandPrefix", "")).removeprefix("/")
                kind = "command-file"
            else:
                prefix = None
                kind = ""
            if kind:
                if not isinstance(prefix, str) or not prefix or prefix in {".", ".."}:
                    raise ValueError(f"missing owned namespace for {source_rel}")
                owned_scopes[target] = (kind, prefix)
            for child in sorted(source.rglob("*")):
                if child.is_file():
                    if not child.resolve().is_relative_to(bundle_root):
                        raise ValueError(f"projection source escapes bundle: {child}")
                    files.append(
                        PlannedFile(
                            source=child,
                            target=_target_path(
                                target_root,
                                target / child.relative_to(source),
                                file=True,
                            ),
                        )
                    )
        else:
            raise ValueError(f"unsupported projection mode {mapping.get('mode')!r}")
    return Projection(files, owned_scopes)


def _owned(path: Path, scope: Path, kind: str, prefix: str) -> bool:
    relative = path.relative_to(scope)
    if kind == "skill-directory":
        return relative.parts[0].startswith(prefix)
    return len(relative.parts) == 1 and relative.name.startswith(prefix)


def _stale_files(plan: Projection):
    expected = {item.target for item in plan.files}
    for scope, (kind, prefix) in plan.owned_scopes.items():
        if not scope.is_dir():
            continue
        for path in sorted(scope.rglob("*")):
            if path.is_dir() and not path.is_symlink():
                continue
            if path not in expected and _owned(path, scope, kind, prefix):
                yield path


def _write_projection(plan: Projection) -> None:
    for item in plan.files:
        item.target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item.source, item.target)
    for path in _stale_files(plan):
        path.unlink()
    for scope, (kind, prefix) in plan.owned_scopes.items():
        for path in sorted(scope.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if (
                path.is_dir()
                and not path.is_symlink()
                and _owned(path, scope, kind, prefix)
            ):
                try:
                    path.rmdir()
                except OSError:
                    pass


def main(argv: list[str] | None = None, *, default_source: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description="Project MoonSpec bundle assets")
    parser.add_argument(
        "--source", type=Path, default=default_source, required=default_source is None
    )
    parser.add_argument("--projection", default="moonmind")
    parser.add_argument("--target", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    bundle_root = args.source.resolve() / "bundle"
    target_root = args.target.resolve()
    try:
        plan = _planned_files(bundle_root, args.projection, target_root)
        if args.write:
            _write_projection(plan)
        drift = [
            str(item.target)
            for item in plan.files
            if not item.target.is_file()
            or not filecmp.cmp(item.source, item.target, shallow=False)
        ]
        drift.extend(f"stale owned asset: {path}" for path in _stale_files(plan))
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
