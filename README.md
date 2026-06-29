# MoonSpec

MoonSpec is a fork of GitHub Spec Kit with an opinionated approach to Spec-Driven Development:

1. Maintain declarative, desired-state documents as the primary source of truth
2. Generate imperative plans and tasks as temporary artifacts to assist implementation
3. Implement code using Test-Driven Development (TDD)
4. Breakdown declarative documents into one or more stories
5. Implement one story at a time (not 3+)
6. Add a verify step to enable a corrective loop
7. Keep the constitution equivalent in AGENTS.md

## Workflow Identity

Canonical skill IDs use `moonspec-*`.

Canonical slash commands use `/moonspec.*`.

The main lifecycle is:

1. `/moonspec.breakdown` when a broad design must be split into one-story candidates.
2. `/moonspec.specify` for one-story specs.
3. `/moonspec.plan` for planning artifacts.
4. `/moonspec.tasks` for TDD-first implementation tasks.
5. `/moonspec.align` for artifact consistency repair.
6. `/moonspec.implement` for implementation.
7. `/moonspec.verify` as the final read-only completion gate.
8. `/moonspec.doc-reconcile` after successful verification when canonical docs need updates.
9. `/moonspec.orchestrate` to coordinate the lifecycle for a preselected one-story request.

## Bundle Layout

The repository packages the assets that consumers need to run the MoonSpec lifecycle:

- agent skills under `bundle/skills/`
- command wrappers under `bundle/commands/`
- spec, plan, task, checklist, and agent templates under `bundle/templates/`
- helper scripts under `bundle/scripts/`
- portable preset definitions under `bundle/presets/`
- bundle docs and projection recipes under `bundle/docs/` and `bundle/projections/`

```text
bundle/
  moonspec.bundle.yaml
  skills/
  templates/
  commands/
    gemini/
    markdown/
  scripts/
    bash/
  presets/
  docs/
  projections/
```

`bundle/moonspec.bundle.yaml` is the authoritative manifest. Consumers should read the manifest and the relevant projection recipe instead of hardcoding individual files.

## Validation

Run:

```bash
python tools/validate_bundle.py
pytest
```

The validator checks exported file existence, skill front matter, OpenAI wrappers, preset skill references, command/skill consistency, projection recipes, script references, and legacy terminology.

## Projection

MoonMind consumes this repository as a pinned git submodule at `vendor/moonspec`.

For a consumer checkout, project the bundle with:

```bash
python tools/project_bundle.py --target /path/to/consumer --projection moonmind --write
python tools/project_bundle.py --target /path/to/consumer --projection moonmind --check
```

MoonMind has its own wrapper around this projection so it can add generated-file headers and enforce consumer-specific drift checks.

## CLI

The Python package is intentionally thin. The bundle is the product.

```bash
moonspec bundle-path
moonspec validate
moonspec project --target /path/to/consumer --projection moonmind --check
```

## Authoring

See `bundle/docs/AuthoringGuide.md` for adding or changing bundle assets and `bundle/docs/BundleIntegration.md` for consumer integration rules.
