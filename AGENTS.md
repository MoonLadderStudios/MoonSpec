# Agent Instructions

MoonSpec is the canonical workflow bundle repository for MoonSpec assets.

## Source Of Truth

- Edit bundle assets in `bundle/`.
- Keep `bundle/moonspec.bundle.yaml` aligned with every exported asset.
- Keep `bundle/projections/*.yaml` aligned with consumer projection paths.
- Do not add parallel command names, skill aliases, or compatibility wrappers for old internal identities.

## Naming

- Agent skills use `moonspec-*`.
- User-facing commands use `/moonspec.*`.
- Python package identity is `moonspec-cli`.
- The console script is `moonspec`.

## MoonSpec Principles

### Portable Bundle, Repo-Specific Guidance Outside The Bundle

MoonSpec owns reusable workflow assets. Keep `bundle/` portable across consumers. Repo-specific project guidance belongs in `AGENTS.md` or consumer docs, not copied into reusable templates.

### One Canonical Identity

Use the canonical names listed above. Do not add aliases, compatibility wrappers, old internal names, or parallel identity systems.

### One-Story, Test-First Execution

MoonSpec specs, plans, and tasks describe one independently testable story. Plans identify unit and integration test strategy separately. Tasks put tests and red-first checks before implementation unless the user explicitly chooses otherwise.

### Disposable Execution Artifacts

`specs/` packets, `plan.md`, `tasks.md`, `research.md`, and quickstarts are execution scaffolding. Durable product, architecture, and workflow knowledge belongs in long-lived docs or agent guidance.

### Planning Exceptions Are Visible

When producing an implementation plan, identify relevant principle conflicts before task generation. A violation needs a concrete reason and mitigation; unnecessary aliases, duplicate paths, and speculative abstractions should be rejected.

### Keep Context Cheap

Prefer short rules that change behavior. Remove boilerplate, stale migration notes, fake formality, duplicated guidance, and generated context bulk.

## Validation

Before committing bundle changes, run:

```bash
python tools/validate_bundle.py
pytest
```

If a change affects projection behavior, also run a projection check against a temporary target:

```bash
python tools/project_bundle.py --target /tmp/moonspec-projection --projection moonmind --write
python tools/project_bundle.py --target /tmp/moonspec-projection --projection moonmind --check
```

## Consumer Boundaries

MoonMind-specific API, database, scheduler, UI, and provider-profile code belongs in MoonMind. This repository owns portable MoonSpec workflow bundle assets and projection recipes only.
