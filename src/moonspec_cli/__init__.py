from __future__ import annotations

import argparse
import sys
from importlib.resources import files
from pathlib import Path

from .project import main as project_main
from .validation import BundleValidationError, validate_bundle


def bundle_path() -> Path:
    packaged = Path(str(files(__package__) / "bundle"))
    if (packaged / "moonspec.bundle.yaml").is_file():
        return packaged
    source_checkout = Path(__file__).resolve().parents[2] / "bundle"
    return source_checkout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="moonspec")
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("bundle-path", help="Print the packaged bundle path")
    subcommands.add_parser("validate", help="Validate the packaged MoonSpec bundle")

    project_parser = subcommands.add_parser("project", help="Project bundle assets")
    project_parser.add_argument("--projection", default="moonmind")
    project_parser.add_argument("--target", type=Path, required=True)
    project_mode = project_parser.add_mutually_exclusive_group(required=True)
    project_mode.add_argument("--check", action="store_true")
    project_mode.add_argument("--write", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "bundle-path":
        print(bundle_path())
        return 0
    if args.command == "validate":
        try:
            validate_bundle(bundle_path())
        except BundleValidationError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print("MoonSpec bundle validation passed")
        return 0
    if args.command == "project":
        return project_main(
            [
                "--source",
                str(bundle_path().parent),
                "--projection",
                args.projection,
                "--target",
                str(args.target),
                "--write" if args.write else "--check",
            ]
        )
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
