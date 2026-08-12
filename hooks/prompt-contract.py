#!/usr/bin/env python3
"""UserPromptSubmit hook. Injects the full contract before the next reply.

In lazy mode the hook stays silent until the Stop hook blocks once in this session.
A clean session therefore pays nothing per turn. Set injection to "always" to opt out.
"""

import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import contract
import ste_rules


def main():
    if os.environ.get("STE_GUARD_OFF"):
        return 0

    profile = ste_rules.load_profile()
    mode = profile.get("injection", "lazy")

    if ste_rules.injection_off(profile):
        return 0

    if mode == "lazy":
        try:
            payload = json.load(sys.stdin)
        except ValueError:
            return 0

        state = ste_rules.load_state(payload.get("session_id", "unknown"))

        if not state.get("armed"):
            return 0

    print(contract.render_contract(profile))

    return 0


if __name__ == "__main__":
    sys.exit(main())
