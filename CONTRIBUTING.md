# Contributing To MoonSpec

MoonSpec contributions should keep the bundle as the source of truth.

Before opening a pull request:

1. Update `bundle/moonspec.bundle.yaml` for every exported asset change.
2. Update projection recipes when consumer paths change.
3. Run `python tools/validate_bundle.py`.
4. Run `pytest`.
5. For projection changes, test `tools/project_bundle.py` against a temporary target.

Do not add compatibility aliases for retired internal command or skill identities. Rename by updating the manifest, commands, presets, tests, and projection recipes in the same change.
