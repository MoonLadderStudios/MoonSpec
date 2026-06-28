# MoonSpec Bundle Integration

Status: Canonical
Owners: MoonLadder Studios
Last Updated: 2026-06-28

## Purpose

This document defines how a consuming repository should use the MoonSpec bundle without copying or re-owning the assets.

## Integration Contract

Consumers read:

- `bundle/moonspec.bundle.yaml`
- `bundle/projections/<consumer>.yaml`

The manifest lists exported skills, commands, templates, scripts, presets, docs, and projections. Projection recipes map bundle-relative paths to consumer-relative paths.

Consumers should pin this repository as a git submodule or another immutable source reference. The pinned revision is the source of truth for projected MoonSpec assets.

## Projection Rules

- Projection must be deterministic.
- Projected files should carry a generated-file header when the consumer keeps projected files committed.
- CI should fail when projected files drift from the pinned bundle.
- Consumers may keep runtime paths stable while changing ownership to the bundle.
- Consumers should not edit projected files directly; update MoonSpec and re-project instead.

## MoonMind Projection

The `moonmind` projection maps:

- `bundle/skills/` to `.agents/skills/`
- `bundle/templates/` to `.specify/templates/`
- `bundle/commands/markdown/` to `.specify/templates/commands/`
- `bundle/scripts/bash/` to `.specify/scripts/bash/`
- `bundle/presets/moonspec-orchestrate.yaml` to `api_service/data/presets/moonspec-orchestrate.yaml`
- `bundle/docs/MoonSpecDocumentModel.md` to `docs/Workflows/MoonSpecDocumentModel.md`
- `bundle/commands/gemini/` to `.gemini/commands/`

MoonMind owns the projection wrapper, preset seeding behavior, runtime scheduler behavior, database migrations, UI/API display behavior, and MoonMind-specific tests.

## Versioning

Bundle revisions are consumed by pinned commit. A consumer bump should include:

1. The submodule pointer update.
2. Re-projected files.
3. A passing projection check.
4. Consumer tests selected by the changed asset surface.
