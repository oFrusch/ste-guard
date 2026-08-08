---
name: ste
description: Use before you send any reply longer than about five bullets, and before you write a spec, plan, ADR, or customer document. Checks a draft against the active STE profile so the Stop hook does not have to block. Also use when the user asks to check, lint, or tighten prose, or asks what the STE rules are.
---

# STE pre-flight

Check the draft before you send it. The Stop hook is the enforcement. This skill is the
pre-flight that keeps the hook quiet.

## When to run the checker

Run it when any of these is true:

1. The draft runs longer than about five bullets.
2. The draft is a specification, a plan, a decision record, or a customer document.
3. The Stop hook already blocked one reply in this session.
4. The user asks you to lint or tighten a piece of prose.

## How to run the checker

Pipe the draft to the checker on stdin, or pass a file path as the single argument.

```
"${CLAUDE_PLUGIN_ROOT}"/hooks/ste-check draft.md
echo "$DRAFT" | "${CLAUDE_PLUGIN_ROOT}"/hooks/ste-check
```

The checker prints one line per violation and exits 1. A clean draft prints the word count
and the profile name, then exits 0.

## How to read the output

Each line names the rule, the offending text, and the fix. Apply the fix and run the checker
again. Do not argue with a phrase-list hit. Those lists are exact-match, so the only fix is
to remove the phrase.

A word-count hit needs real compression. Cut whole bullets. Do not compress by the removal
of articles, because that breaks a different rule.

## Quoted text

The checker exempts text inside double quotes. You can name a banned phrase when you explain
it to the user. You cannot use one.

## How to change the rules

The active profile lives at `~/.claude/ste-guard.json`, or comes from the `STE_GUARD_PROFILE`
environment variable, or falls back to the bundled default. Read the repository README for
the profile schema. Never edit a bundled profile in place. Write a user profile that extends
it instead.
