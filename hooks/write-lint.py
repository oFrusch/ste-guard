#!/usr/bin/env python3
"""PreToolUse hook. Lints the markdown a Write or an Edit is about to put on disk.

The Stop hook reads chat text only, so a README or a spec written through a file tool
never meets a rule. This hook closes that gap. It judges markdown, never code.

Set STE_GUARD_OFF=1 or STE_GUARD_WRITE_OFF=1 to disable. The write_guard block in the
active profile controls the rest: the switch, the file types, the lint profile, and
whether a failure denies the write or only warns.
"""

import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import ste_rules

DEFAULTS = {
    "enabled": True,
    "mode": "deny",
    "profile": "docs",
    "suffixes": [".md", ".markdown", ".mdx"],
}


def allow():
    sys.exit(0)


def new_text(tool, payload):
    """Read only the text the tool adds. An Edit's old_string leaves the file, so it is moot."""
    if tool == "Write":
        return payload.get("content") or ""

    if tool == "Edit":
        return payload.get("new_string") or ""

    if tool == "MultiEdit":
        edits = payload.get("edits") or []
        return "\n\n".join(e.get("new_string", "") for e in edits if isinstance(e, dict))

    return ""


def main():
    if os.environ.get("STE_GUARD_OFF") or os.environ.get("STE_GUARD_WRITE_OFF"):
        allow()

    try:
        payload = json.load(sys.stdin)
    except ValueError:
        allow()

    # The session profile carries the settings. The lint itself runs a profile it names.
    settings = dict(DEFAULTS, **(ste_rules.load_profile().get("write_guard") or {}))

    if not settings.get("enabled"):
        allow()

    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}

    path = tool_input.get("file_path") or ""
    suffixes = {s.lower() for s in settings.get("suffixes") or []}

    if pathlib.Path(path).suffix.lower() not in suffixes:
        allow()

    text = new_text(tool, tool_input)
    if not text.strip():
        allow()

    profile = ste_rules.load_profile(settings.get("profile") or "docs")
    result = ste_rules.verdict(profile, text)
    violations = result["violations"]

    if os.environ.get("STE_GUARD_DEBUG"):
        print(f"ste-guard write: {len(violations)} violations in {path}", file=sys.stderr)

    if not violations:
        ste_rules.record(profile, result, "claude-code-write", blocked=False)
        allow()

    warn_only = settings.get("mode") == "warn"
    ste_rules.record(profile, result, "claude-code-write", blocked=not warn_only)

    if warn_only:
        listed = "\n".join(f"  - {item}" for item in violations[:8])
        print(
            json.dumps(
                {
                    "systemMessage": f"ste-guard: {len(violations)} STE violations in {path}.\n{listed}",
                    "suppressOutput": True,
                }
            )
        )
        sys.exit(0)

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": ste_rules.write_prompt(violations, path),
                }
            }
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
