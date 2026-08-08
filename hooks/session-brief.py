#!/usr/bin/env python3
"""SessionStart hook. Injects the rule card one time.

The session prompt cache holds this, so the cost is paid once instead of once per turn.
"""

import pathlib
import os
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import contract
import ste_rules


def main():
    if os.environ.get("STE_GUARD_OFF"):
        return 0

    profile = ste_rules.load_profile()

    if profile.get("injection") == "off":
        return 0

    print(contract.render_brief(profile))

    return 0


if __name__ == "__main__":
    sys.exit(main())
