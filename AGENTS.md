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
