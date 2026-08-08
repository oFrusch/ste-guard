#!/usr/bin/env python3
"""Renders the rule text that the hooks inject. Every number comes from the active profile.

The brief runs once per session. The full contract runs per turn, and only after a block.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import ste_rules

RULE_LINES = [
    ("openers", "Lead with the answer or the call. No preamble, no warm-up."),
    ("closers", "Stop when the answer is done. No sign-off, no recap."),
    ("puffery", "Say the concrete thing. No marketing adjectives."),
    ("not_just", 'Do not use the "not just X, it is Y" construction.'),
    ("asides", "No parenthetical or em-dash interruption mid-sentence. Split it."),
    ("gerund", "Do not open a sentence with an -ing form. Name the actor first."),
    ("passive", "Active voice. Name the actor."),
    ("narration", "State the fact, not the discovery of the fact."),
    ("flourish", "No wordplay, no ironic understatement, no rhetorical symmetry."),
    ("prose_wall", "Bullets by default. One fact per bullet."),
]

ALWAYS_LINES = [
    "One instruction per sentence.",
    "Present tense unless the event is really past or future.",
    "One term per concept, always the same term. Synonym drift is a bug.",
    "No compound noun longer than three words. Keep the articles.",
    "Conditions and warnings go before the step they govern.",
]


def _enabled(profile):
    rules = profile.get("rules") or {}

    return [text for key, text in RULE_LINES if rules.get(key)]


def render_brief(profile):
    """The once-per-session card. Short, because the session prompt cache holds it."""
    budget = profile.get("budget") or {}
    lines = ["STE-GUARD — writing rules for every reply in this session.", ""]

    if budget.get("words"):
        lines.append(
            f"Word ceiling: {budget['words']} per reply. A markdown heading lifts the cap."
        )

    if budget.get("sentence_words"):
        lines.append(f"Sentence ceiling: {budget['sentence_words']} words, every sentence.")

    lines.append("")
    lines += [f"- {text}" for text in _enabled(profile) + ALWAYS_LINES]
    lines.append("")
    lines.append("A Stop hook checks each reply and blocks once when a rule fails.")

    return "\n".join(lines)


def render_contract(profile):
    """The post-block contract. Adds the exact strings, because the checker matches them."""
    lists = profile.get("lists") or {}
    rules = profile.get("rules") or {}

    parts = [render_brief(profile), "", "ENFORCED VALUES — the checker matches these exact strings:", ""]

    labels = [
        ("openers", "Banned openers"),
        ("closers", "Banned closers"),
        ("puffery", "Banned puffery"),
        ("narration", "Banned narration"),
        ("flourish", "Banned flourish"),
    ]

    for key, label in labels:
        if not rules.get(key) or not lists.get(key):
            continue

        joined = ", ".join(f'"{item}"' for item in sorted(lists[key]))
        parts.append(f"{label}: {joined}")
        parts.append("")

    return "\n".join(parts).rstrip()


def main():
    import sys

    profile = ste_rules.load_profile()

    if "--contract" in sys.argv:
        print(render_contract(profile))
    else:
        print(render_brief(profile))


if __name__ == "__main__":
    main()
