#!/usr/bin/env python3
"""Wires the ste-guard hooks into ~/.codex/hooks.json.

Codex v0.147 installs a plugin's skills but does not load the hooks the plugin ships.
This script writes the three hook entries by absolute path instead. Remove them with
--uninstall. Run it again after a plugin update, because the version is in the path.
"""

import argparse
import json
import os
import pathlib
import shutil
import sys

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent
CODEX_HOOKS = pathlib.Path(os.path.expanduser("~/.codex/hooks.json"))

MARKER = "ste-guard"

EVENTS = [
    ("SessionStart", "session-brief.py", 5),
    ("UserPromptSubmit", "prompt-contract.py", 5),
    ("Stop", "stop-lint.py", 10),
]


# The predecessor scripts ran from ~/.claude/hooks under different names. Strip those too,
# or a migrating user ends up with two linters fighting over the same reply.
LEGACY_SCRIPTS = ["ste-lint.py", "style-contract.sh", "ste-check"]


def is_ours(hook):
    """A hook belongs to ste-guard when its command names one of our scripts."""
    command = hook.get("command", "")

    if MARKER in command:
        return True

    names = [script for _, script, _ in EVENTS] + LEGACY_SCRIPTS

    return any(name in command for name in names)


def strip_ours(config):
    """Remove every ste-guard entry, so a re-run never stacks duplicates."""
    events = config.get("hooks") or {}

    for event in list(events):
        kept_entries = []

        for entry in events[event]:
            entry["hooks"] = [h for h in entry.get("hooks", []) if not is_ours(h)]

            if entry["hooks"]:
                kept_entries.append(entry)

        if kept_entries:
            events[event] = kept_entries
        else:
            del events[event]

    config["hooks"] = events

    return config


def add_ours(config, root):
    events = config.setdefault("hooks", {})

    for event, script, timeout in EVENTS:
        hook = {
            "type": "command",
            "command": f"'{root / 'hooks' / script}'",
            "timeout": timeout,
        }
        events.setdefault(event, []).append({"hooks": [hook]})

    return config


def load():
    if not CODEX_HOOKS.exists():
        return {}

    try:
        return json.loads(CODEX_HOOKS.read_text())
    except ValueError:
        print(f"error: {CODEX_HOOKS} is not valid JSON. Fix it first.", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uninstall", action="store_true", help="remove the ste-guard entries")
    parser.add_argument("--root", default=str(PLUGIN_ROOT), help="plugin root to point the hooks at")
    args = parser.parse_args()

    config = load()

    if CODEX_HOOKS.exists():
        backup = CODEX_HOOKS.with_suffix(".json.bak")
        shutil.copy2(CODEX_HOOKS, backup)
        print(f"backed up to {backup}")

    config = strip_ours(config)

    if not args.uninstall:
        config = add_ours(config, pathlib.Path(args.root).resolve())

    CODEX_HOOKS.parent.mkdir(parents=True, exist_ok=True)
    CODEX_HOOKS.write_text(json.dumps(config, indent=2) + "\n")

    action = "removed" if args.uninstall else "installed"
    print(f"{action} the ste-guard hooks in {CODEX_HOOKS}")

    if not args.uninstall:
        print("Codex asks you to trust each new hook command on the next interactive run.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
