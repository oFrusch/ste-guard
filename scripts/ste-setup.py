#!/usr/bin/env python3
"""Writes ~/.claude/ste-guard.json, so a user picks the features they want.

Run it with no flags from a terminal for the questions. Pass flags for a scripted run,
which is how the /ste-guard:setup command drives it. Every flag is optional, and an
absent flag leaves that setting as it stands.
"""

import argparse
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = pathlib.Path(os.environ.get("STE_GUARD_CONFIG") or os.path.expanduser("~/.claude/ste-guard.json"))

BASE_PROFILES = ["default", "peer-eng"]
RULES = [
    ("openers", "Filler openers such as \"Great question\""),
    ("closers", "Hollow closers such as \"Hope this helps\""),
    ("puffery", "Marketing words and phrases"),
    ("not_just", "The \"not just X, it is Y\" construction"),
    ("asides", "Mid-sentence parenthetical and em-dash asides"),
    ("gerund", "A sentence that opens with an -ing form"),
    ("passive", "Passive voice"),
    ("narration", "Process narration such as \"I found that\""),
    ("flourish", "Literary flourish and transition cliches"),
    ("prose_wall", "A paragraph where a bullet list belongs"),
]


def read_config():
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return {}


def write_config(cfg):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)

    if CONFIG.exists():
        CONFIG.with_suffix(".json.bak").write_text(CONFIG.read_text())

    CONFIG.write_text(json.dumps(cfg, indent=2) + "\n")


def show(cfg):
    if not cfg:
        print(f"No config at {CONFIG}. ste-guard runs the bundled default profile.")
        return

    print(f"{CONFIG}\n")
    print(json.dumps(cfg, indent=2))

    if os.environ.get("STE_GUARD_PROFILE"):
        print(
            "\nWarning: STE_GUARD_PROFILE is set in the environment. It wins over this file.",
            file=sys.stderr,
        )


def ask(question, options, current):
    """One question, one answer. The current value is the empty reply."""
    print(f"\n{question}")

    for index, (value, label) in enumerate(options, start=1):
        mark = " (current)" if value == current else ""
        print(f"  {index}. {label}{mark}")

    while True:
        reply = input(f"Choose 1-{len(options)}, or press enter to keep the current: ").strip()

        if not reply:
            return current

        if reply.isdigit() and 1 <= int(reply) <= len(options):
            return options[int(reply) - 1][0]

        print("That is not one of the numbers.")


def ask_yes(question, current):
    suffix = "Y/n" if current else "y/N"

    while True:
        reply = input(f"{question} [{suffix}] ").strip().lower()

        if not reply:
            return current

        if reply in ("y", "yes"):
            return True

        if reply in ("n", "no"):
            return False


def interactive(cfg):
    print("ste-guard setup. Press enter at any question to keep the current setting.")

    guard = dict(cfg.get("write_guard") or {})
    rules = dict(cfg.get("rules") or {})

    cfg["extends"] = ask(
        "Which register do you want?",
        [
            ("default", "default. Grammar only, 250-word ceiling, no voice rules."),
            ("peer-eng", "peer-eng. Blunt register, 130-word ceiling, every rule on."),
        ],
        cfg.get("extends", "default"),
    )

    cfg["injection"] = ask(
        "When should the hook inject the full rule text?",
        [
            ("lazy", "lazy. Stays silent until a reply fails one time."),
            ("always", "always. Every turn carries the rules."),
            ("never", "never. The hook still blocks, and it never injects."),
        ],
        cfg.get("injection", "lazy"),
    )

    mode = ask(
        "What should the write guard do with markdown a file tool writes?",
        [
            ("deny", "deny. Block the write and ask for a fix."),
            ("warn", "warn. Let the write land and report the violations."),
            ("off", "off. Never check a file. The reply guard stays on."),
        ],
        "off" if guard.get("enabled") is False else guard.get("mode", "deny"),
    )

    guard["enabled"] = mode != "off"

    if guard["enabled"]:
        guard["mode"] = mode

    cfg["write_guard"] = guard
    cfg["telemetry"] = ask_yes(
        "\nRecord one line per turn, with counts only and no message text?",
        cfg.get("telemetry", False),
    )

    if ask_yes("\nDo you want to turn individual rules off?", False):
        for name, label in RULES:
            on = rules.get(name, True)
            rules[name] = ask_yes(f"  {label}?", on)

        cfg["rules"] = rules

    return cfg


def apply_flags(cfg, args):
    if args.profile:
        cfg["extends"] = args.profile

    if args.injection:
        cfg["injection"] = args.injection

    if args.telemetry:
        cfg["telemetry"] = args.telemetry == "on"

    if args.write_guard:
        guard = dict(cfg.get("write_guard") or {})
        guard["enabled"] = args.write_guard != "off"

        if guard["enabled"]:
            guard["mode"] = args.write_guard

        cfg["write_guard"] = guard

    if args.write_suffixes:
        guard = dict(cfg.get("write_guard") or {})
        guard["suffixes"] = [s if s.startswith(".") else f".{s}" for s in args.write_suffixes.split(",")]
        cfg["write_guard"] = guard

    if args.rules_off:
        rules = dict(cfg.get("rules") or {})

        for name in args.rules_off.split(","):
            rules[name.strip()] = False

        cfg["rules"] = rules

    if args.rules_on:
        rules = dict(cfg.get("rules") or {})

        for name in args.rules_on.split(","):
            rules[name.strip()] = True

        cfg["rules"] = rules

    return cfg


def main():
    parser = argparse.ArgumentParser(description="Configure ste-guard.")
    parser.add_argument("--show", action="store_true", help="Print the current config and exit")
    parser.add_argument("--reset", action="store_true", help="Delete the config and use the bundled default")
    parser.add_argument("--profile", choices=BASE_PROFILES, help="The register to extend")
    parser.add_argument("--injection", choices=["lazy", "always", "never"], help="When to inject the rule text")
    parser.add_argument("--telemetry", choices=["on", "off"], help="Record one line per turn")
    parser.add_argument("--write-guard", choices=["deny", "warn", "off"], help="What the write guard does")
    parser.add_argument("--write-suffixes", help="Comma separated file suffixes the write guard reads")
    parser.add_argument("--rules-off", help="Comma separated rule names to turn off")
    parser.add_argument("--rules-on", help="Comma separated rule names to turn on")

    args = parser.parse_args()
    cfg = read_config()

    if args.show:
        show(cfg)
        return 0

    if args.reset:
        if CONFIG.exists():
            CONFIG.unlink()
            print(f"Removed {CONFIG}. ste-guard runs the bundled default profile.")
        else:
            print("No config to remove.")

        return 0

    flagged = any(
        [args.profile, args.injection, args.telemetry, args.write_guard, args.write_suffixes,
         args.rules_off, args.rules_on]
    )

    if flagged:
        cfg = apply_flags(cfg, args)
    elif sys.stdin.isatty():
        cfg = interactive(cfg)
    else:
        parser.print_help()
        return 1

    cfg.setdefault("extends", "default")
    write_config(cfg)

    print(f"\nWrote {CONFIG}")
    print(json.dumps(cfg, indent=2))

    if os.environ.get("STE_GUARD_PROFILE"):
        print(
            "\nWarning: STE_GUARD_PROFILE is set in the environment. It wins over this file.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
