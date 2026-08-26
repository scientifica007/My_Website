#!/usr/bin/env python3
"""Validate autonomous-experiment invariants without calling an AI provider."""
from __future__ import annotations

import sys

from core import bootstrap_errors


def main() -> int:
    errors = bootstrap_errors()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Autonomy bootstrap validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
