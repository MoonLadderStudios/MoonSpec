#!/usr/bin/env python3
from __future__ import annotations

from validate_bundle import ValidationError, validate_terminology


def main() -> int:
    try:
        validate_terminology()
    except ValidationError as exc:
        print(f"ERROR: {exc}")
        return 1
    print("MoonSpec terminology validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
