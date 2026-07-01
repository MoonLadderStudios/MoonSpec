#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ROOT = REPO_ROOT / "bundle"
MANIFEST_PATH = BUNDLE_ROOT / "moonspec.bundle.yaml"

FORBIDDEN_PATTERNS = {
    "speckit slash command": re.compile(r"/speckit\."),
    "speckit skill prefix": re.compile(r"\bspeckit-"),
    "speckit phase prefix": re.compile(r"\bspeckit_"),
    "agentkit slash command": re.compile(r"/agentkit\."),
    "agentkit skill prefix": re.compile(r"\bagentkit-"),
    "agentkit phase prefix": re.compile(r"\bagentkit_"),
    "specify package": re.compile(r"\bspecify-cli\b|\bspecify_cli\b"),
    "standalone constitution path": re.compile(
        r"\.specify[/\\]memory[/\\]constitution(?:\.md)?"
    ),
}
SCRIPT_REF_PATTERN = re.compile(
    r"(?:^|[`\"'\s])(?:\.specify/)?scripts/bash/([A-Za-z0-9_.-]+\.sh)"
)

TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".yaml",
    ".yml",
    ".txt",
}


class ValidationError(Exception):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValidationError(f"{path} must contain a YAML mapping")
    return data


def parse_front_matter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValidationError(f"{path} is missing YAML front matter")
    end = text.find("\n---", 4)
    if end == -1:
        raise ValidationError(f"{path} has unterminated YAML front matter")
    data = yaml.safe_load(text[4:end]) or {}
    if not isinstance(data, dict):
        raise ValidationError(f"{path} front matter must be a YAML mapping")
    return data


def iter_text_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            yield path
        elif path.is_dir():
            for child in path.rglob("*"):
                if child.is_file() and child.suffix in TEXT_SUFFIXES:
                    yield child


def iter_skill_ids(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        skill = value.get("skill")
        if isinstance(skill, Mapping) and isinstance(skill.get("id"), str):
            yield skill["id"]
        for child in value.values():
            yield from iter_skill_ids(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_skill_ids(child)


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schemaVersion") != 1:
        raise ValidationError("schemaVersion must be 1")
    if manifest.get("name") != "moonspec":
        raise ValidationError("manifest name must be moonspec")
    identity = manifest.get("identity")
    if not isinstance(identity, dict):
        raise ValidationError("identity must be a mapping")
    if identity.get("canonicalPrefix") != "moonspec":
        raise ValidationError("identity.canonicalPrefix must be moonspec")

    exports = manifest.get("exports")
    if not isinstance(exports, dict):
        raise ValidationError("exports must be a mapping")

    skill_ids: set[str] = set()
    for skill in exports.get("skills", []):
        if not isinstance(skill, dict):
            raise ValidationError("skill export entries must be mappings")
        skill_id = skill.get("id")
        if not isinstance(skill_id, str) or not skill_id.startswith("moonspec-"):
            raise ValidationError(f"invalid skill id: {skill_id!r}")
        skill_ids.add(skill_id)
        skill_path = BUNDLE_ROOT / str(skill.get("path", ""))
        if not skill_path.is_file():
            raise ValidationError(f"missing skill file: {skill_path}")
        front_matter = parse_front_matter(skill_path)
        if front_matter.get("name") != skill_id:
            raise ValidationError(f"{skill_path} front matter name must be {skill_id}")
        if not isinstance(front_matter.get("description"), str):
            raise ValidationError(f"{skill_path} front matter needs description")
        wrappers = skill.get("wrappers")
        if not isinstance(wrappers, dict) or "openai" not in wrappers:
            raise ValidationError(f"{skill_id} must export an OpenAI wrapper")
        wrapper_path = BUNDLE_ROOT / str(wrappers["openai"])
        if not wrapper_path.is_file():
            raise ValidationError(f"missing OpenAI wrapper: {wrapper_path}")

    if not skill_ids:
        raise ValidationError("manifest exports no skills")

    exported_scripts: set[str] = set()
    for section_name in ("templates", "scripts", "docs"):
        for entry in exports.get(section_name, []):
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise ValidationError(f"{section_name} entries need path")
            path = BUNDLE_ROOT / entry["path"]
            if not path.is_file():
                raise ValidationError(f"missing exported {section_name} file: {path}")
            if section_name == "scripts":
                exported_scripts.add(Path(entry["path"]).name)

    command_ids: set[str] = set()
    for command in exports.get("commands", []):
        if not isinstance(command, dict):
            raise ValidationError("command export entries must be mappings")
        command_id = command.get("id")
        slash_command = command.get("slashCommand")
        skill_id = command.get("skill")
        if not isinstance(command_id, str) or not command_id.startswith("moonspec."):
            raise ValidationError(f"invalid command id: {command_id!r}")
        if slash_command != f"/{command_id}":
            raise ValidationError(f"{command_id} has mismatched slashCommand")
        if skill_id not in skill_ids:
            raise ValidationError(f"{command_id} references missing skill {skill_id!r}")
        command_ids.add(command_id)
        for key in ("markdown", "gemini"):
            path = BUNDLE_ROOT / str(command.get(key, ""))
            if not path.is_file():
                raise ValidationError(f"missing {key} command for {command_id}: {path}")

    expected_commands = {
        f"moonspec.{name}"
        for name in (
            "breakdown",
            "specify",
            "plan",
            "tasks",
            "align",
            "implement",
            "verify",
            "doc-reconcile",
            "orchestrate",
        )
    }
    missing_commands = expected_commands - command_ids
    if missing_commands:
        raise ValidationError(f"missing command exports: {sorted(missing_commands)}")

    for preset in exports.get("presets", []):
        if not isinstance(preset, dict) or not isinstance(preset.get("path"), str):
            raise ValidationError("preset entries need path")
        preset_path = BUNDLE_ROOT / preset["path"]
        if not preset_path.is_file():
            raise ValidationError(f"missing preset file: {preset_path}")
        preset_data = load_yaml(preset_path)
        unknown_skills = sorted(set(iter_skill_ids(preset_data)) - skill_ids)
        if unknown_skills:
            raise ValidationError(
                f"{preset_path} references non-exported skills: {unknown_skills}"
            )

    referenced_scripts: set[str] = set()
    for path in iter_text_files([BUNDLE_ROOT / "skills", BUNDLE_ROOT / "commands"]):
        for match in SCRIPT_REF_PATTERN.finditer(path.read_text(encoding="utf-8")):
            referenced_scripts.add(match.group(1))
    missing_scripts = sorted(referenced_scripts - exported_scripts)
    if missing_scripts:
        raise ValidationError(f"referenced scripts are not exported: {missing_scripts}")

    projections = manifest.get("projections")
    if not isinstance(projections, dict):
        raise ValidationError("projections must be a mapping")
    for name, projection in projections.items():
        if not isinstance(projection, dict) or not isinstance(
            projection.get("path"),
            str,
        ):
            raise ValidationError(f"projection {name!r} needs path")
        projection_path = BUNDLE_ROOT / projection["path"]
        if not projection_path.is_file():
            raise ValidationError(f"missing projection recipe: {projection_path}")
        validate_projection(projection_path)


def validate_projection(path: Path) -> None:
    data = load_yaml(path)
    if data.get("schemaVersion") != 1:
        raise ValidationError(f"{path} schemaVersion must be 1")
    mappings = data.get("mappings")
    if not isinstance(mappings, list) or not mappings:
        raise ValidationError(f"{path} must define mappings")
    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise ValidationError(f"{path} mappings must be mappings")
        source = mapping.get("from")
        target = mapping.get("to")
        mode = mapping.get("mode")
        if mode not in {"file", "directory"}:
            raise ValidationError(f"{path} mapping mode must be file or directory")
        if not isinstance(source, str) or not isinstance(target, str):
            raise ValidationError(f"{path} mappings need from and to strings")
        source_path = BUNDLE_ROOT / source
        if mode == "file" and not source_path.is_file():
            raise ValidationError(f"{path} missing mapped file source: {source_path}")
        if mode == "directory" and not source_path.is_dir():
            raise ValidationError(
                f"{path} missing mapped directory source: {source_path}"
            )


def validate_terminology() -> None:
    roots = [
        BUNDLE_ROOT,
        REPO_ROOT / "README.md",
        REPO_ROOT / "AGENTS.md",
        REPO_ROOT / "CONTRIBUTING.md",
        REPO_ROOT / "SUPPORT.md",
        REPO_ROOT / "pyproject.toml",
    ]
    violations: list[str] = []
    for path in iter_text_files(roots):
        rel = path.relative_to(REPO_ROOT)
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if (
                rel == Path("bundle/projections/moonmind.yaml")
                and line.strip().startswith("- ")
            ):
                continue
            for label, pattern in FORBIDDEN_PATTERNS.items():
                match = pattern.search(line)
                if match is None:
                    continue
                violations.append(
                    f"{rel}:{line_number}: forbidden {label}: {match.group(0)}"
                )
    if violations:
        raise ValidationError("legacy terminology found:\n" + "\n".join(violations))


def validate_bundle() -> None:
    manifest = load_yaml(MANIFEST_PATH)
    validate_manifest(manifest)
    validate_terminology()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the MoonSpec bundle")
    parser.parse_args(argv)
    try:
        validate_bundle()
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("MoonSpec bundle validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
