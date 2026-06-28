# MoonSpec Authoring Guide

Status: Canonical
Owners: MoonLadder Studios
Last Updated: 2026-06-28

## Add Or Update A Skill

1. Edit or add `bundle/skills/<skill-name>/SKILL.md`.
2. Use a `moonspec-*` skill name in front matter.
3. Add or update `bundle/skills/<skill-name>/agents/openai.yaml`.
4. Register the skill in `bundle/moonspec.bundle.yaml`.
5. Update presets or commands that intentionally use the skill.
6. Run `python tools/validate_bundle.py`.

Every exported skill must have:

- YAML front matter.
- `name` matching the exported skill ID.
- `description`.
- an OpenAI wrapper.

## Add Or Update A Command

1. Add Markdown command content under `bundle/commands/markdown/moonspec.<name>.md`.
2. Add Gemini command content under `bundle/commands/gemini/moonspec.<name>.toml`.
3. Register both files in `bundle/moonspec.bundle.yaml`.
4. Reference the owning `moonspec-*` skill.

Command files must use `/moonspec.*` command names and must not introduce old command aliases.

## Add Or Update Templates

Templates live under `bundle/templates/`.

Keep templates runtime-neutral where possible. If a template references a MoonSpec command, use `/moonspec.*`.

## Add Or Update Scripts

Scripts live under `bundle/scripts/bash/`.

Scripts must be executable in ordinary Bash environments and should resolve paths relative to the consumer repository root. Register exported scripts in the bundle manifest.

## Update Projection Recipes

Projection recipes live under `bundle/projections/`.

When adding a consumer mapping:

- use bundle-relative `from` paths,
- use consumer-relative `to` paths,
- choose `file` or `directory` mode,
- document consumer-owned behavior in `bundle/docs/BundleIntegration.md`.

## Validation Rules

Run:

```bash
python tools/validate_bundle.py
pytest
```

Validation fails for missing exported files, missing wrappers, preset references to non-exported skills, command/skill mismatches, invalid projection sources, and legacy terminology in active bundle files.
