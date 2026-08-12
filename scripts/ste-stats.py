#!/usr/bin/env python3
"""Summarises the ste-guard telemetry log.

Telemetry is off by default. Turn it on with `"telemetry": true` in your profile, or with
STE_GUARD_TELEMETRY=1. The log holds counts and rule numbers only, never message text.
"""

import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "hooks"))

import ste_rules

RULE_NAMES = {
    "Rule 0": "over the word ceiling",
    "Rule 2": "filler opener",
    "Rule 6": "prose wall, no bullets",
    "Rule 7": "hollow closer",
    "Rule 8": "puffery",
    "Rule 10": "passive voice",
    "Rule 11": "sentence too long",
    "Rule 12": "gerund opener",
    "Rule 17": "process narration",
    "Rule 18": "mid-sentence aside",
    "Rule 19": "literary flourish",
}


def read(path):
    rows = []

    try:
        with open(path) as handle:
            for line in handle:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []

    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", default=str(ste_rules.TELEMETRY_LOG))
    args = parser.parse_args()

    rows = read(args.log)

    if not rows:
        print(f"no telemetry at {args.log}")
        print('Turn it on with "telemetry": true in your profile, or STE_GUARD_TELEMETRY=1.')
        return 1

    scored = [r for r in rows if not r.get("too_short")]
    blocked = [r for r in scored if r.get("blocked")]
    words = sum(r.get("words", 0) for r in scored)

    print(f"log: {args.log}")
    print(f"turns recorded: {len(rows)}   scored: {len(scored)}   short-circuited: {len(rows) - len(scored)}")

    if not scored:
        return 0

    rate = 100 * len(blocked) / len(scored)
    print(f"blocked: {len(blocked)} of {len(scored)} scored turns ({rate:.0f}%)")
    print(f"words written: {words}   mean per scored turn: {words / len(scored):.0f}")

    counts = collections.Counter(rule for r in scored for rule in r.get("rules", []))

    if counts:
        per_100 = 100 * sum(counts.values()) / max(words, 1)
        print(f"violations per 100 words: {per_100:.2f}")
        print("\nrule                       hits   share")

        total = sum(counts.values())
        for rule, count in counts.most_common():
            name = RULE_NAMES.get(rule, "")
            label = f"{rule} {name}"[:26]
            print(f"  {label:26s} {count:4d}   {100 * count / total:4.0f}%")

    agents = collections.Counter(r.get("agent", "unknown") for r in scored)
    print("\nby agent: " + ", ".join(f"{a}={n}" for a, n in agents.most_common()))

    return 0


if __name__ == "__main__":
    sys.exit(main())
