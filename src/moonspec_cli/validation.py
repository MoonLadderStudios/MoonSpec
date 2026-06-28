from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml

FORBIDDEN_PATTERNS = {
    "speckit slash command": re.compile(r"/speckit\."),
    "speckit skill prefix": re.compile(r"\bspeckit-"),
    "speckit phase prefix": re.compile(r"\bspeckit_"),
    "agentkit slash command": re.compile(r"/agentkit\."),
    "agentkit skill prefix": re.compile(r"\bagentkit-"),
    "agentkit phase prefix": re.compile(r"\bagentkit_"),
    "specify package": re.compile(r"\bspecify-cli\b|\bspecify_cli\b"),
}
SCRIPT_REF_PATTERN = re.compile(
    r"(?:^|[`\"'\s])(?:\.specify/)?scripts/bash/([A-Za-z0-9_.-]+\.sh)"
)

TEXT_SUFFIXES = {".md", ".py", ".sh", ".toml", ".yaml", ".yml", ".txt"}


class BundleValidationError(Exception):
    pass


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise BundleValidationError(f"{path} must contain a YAML mapping")
    return data


def _parse_front_matter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise BundleValidationError(f"{path} is missing YAML front matter")
    end = text.find("\n---", 4)
    if end == -1:
        raise BundleValidationError(f"{path} has unterminated YAML front matter")
    data = yaml.safe_load(text[4:end]) or {}
    if not isinstance(data, dict):
        raise BundleValidationError(f"{path} front matter must be a YAML mapping")
    return data


def _iter_skill_ids(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        skill = value.get("skill")
        if isinstance(skill, Mapping) and isinstance(skill.get("id"), str):
            yield skill["id"]
        for child in value.values():
            yield from _iter_skill_ids(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_skill_ids(child)


def _iter_text_files(root: Path) -> Iterable[Path]:
    for child in root.rglob("*"):
        if child.is_file() and child.suffix in TEXT_SUFFIXES:
            yield child


def validate_bundle(bundle_root: Path) -> None:
    manifest_path = bundle_root / "moonspec.bundle.yaml"
    manifest = _load_yaml(manifest_path)
    if manifest.get("schemaVersion") != 1:
        raise BundleValidationError("schemaVersion must be 1")
    if manifest.get("name") != "moonspec":
        raise BundleValidationError("manifest name must be moonspec")

    exports = manifest.get("exports")
    if not isinstance(exports, dict):
        raise BundleValidationError("exports must be a mapping")

    skill_ids: set[str] = set()
    for skill in exports.get("skills", []):
        if not isinstance(skill, dict):
            raise BundleValidationError("skill exports must be mappings")
        skill_id = skill.get("id")
        if not isinstance(skill_id, str) or not skill_id.startswith("moonspec-"):
            raise BundleValidationError(f"invalid skill id: {skill_id!r}")
        skill_ids.add(skill_id)
        skill_path = bundle_root / str(skill.get("path", ""))
        if not skill_path.is_file():
            raise BundleValidationError(f"missing skill file: {skill_path}")
        front_matter = _parse_front_matter(skill_path)
        if front_matter.get("name") != skill_id:
            raise BundleValidationError(f"{skill_path} name must be {skill_id}")
        wrappers = skill.get("wrappers")
        if not isinstance(wrappers, dict) or "openai" not in wrappers:
            raise BundleValidationError(f"{skill_id} must export an OpenAI wrapper")
        if not (bundle_root / str(wrappers["openai"])).is_file():
            raise BundleValidationError(f"{skill_id} OpenAI wrapper is missing")

    exported_scripts: set[str] = set()
    for section in ("templates", "scripts", "docs"):
        for entry in exports.get(section, []):
            if not isinstance(entry, dict):
                raise BundleValidationError(f"{section} export has missing path")
            path = bundle_root / str(entry.get("path", ""))
            if not path.is_file():
                raise BundleValidationError(f"{section} export has missing path")
            if section == "scripts":
                exported_scripts.add(Path(str(entry["path"])).name)

    for command in exports.get("commands", []):
        if not isinstance(command, dict):
            raise BundleValidationError("command exports must be mappings")
        command_id = command.get("id")
        if not isinstance(command_id, str) or not command_id.startswith("moonspec."):
            raise BundleValidationError(f"invalid command id: {command_id!r}")
        if command.get("skill") not in skill_ids:
            raise BundleValidationError(f"{command_id} references a missing skill")
        for key in ("markdown", "gemini"):
            if not (bundle_root / str(command.get(key, ""))).is_file():
                raise BundleValidationError(f"{command_id} missing {key} file")

    for preset in exports.get("presets", []):
        if not isinstance(preset, dict):
            raise BundleValidationError("preset exports must be mappings")
        preset_path = bundle_root / str(preset.get("path", ""))
        preset_data = _load_yaml(preset_path)
        unknown_skills = sorted(set(_iter_skill_ids(preset_data)) - skill_ids)
        if unknown_skills:
            raise BundleValidationError(
                f"{preset_path} references non-exported skills: {unknown_skills}"
            )

    referenced_scripts: set[str] = set()
    for root in (bundle_root / "skills", bundle_root / "commands"):
        for text_file in _iter_text_files(root):
            text = text_file.read_text(encoding="utf-8")
            for match in SCRIPT_REF_PATTERN.finditer(text):
                referenced_scripts.add(match.group(1))
    missing_scripts = sorted(referenced_scripts - exported_scripts)
    if missing_scripts:
        raise BundleValidationError(
            f"referenced scripts are not exported: {missing_scripts}"
        )

    for text_file in _iter_text_files(bundle_root):
        rel = text_file.relative_to(bundle_root)
        text = text_file.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if (
                rel == Path("projections/moonmind.yaml")
                and line.strip().startswith("- ")
            ):
                continue
            for label, pattern in FORBIDDEN_PATTERNS.items():
                match = pattern.search(line)
                if match is None:
                    continue
                raise BundleValidationError(
                    f"{text_file}:{line_number}: forbidden {label}: {match.group(0)}"
                )
