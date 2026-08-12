# Changelog

All notable changes to ste-guard appear in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.1] - 2026-08-12

An audit reported these. Each one has a regression test that failed before the fix.

### Fixed

- `injection` accepts `never`. The setup script and the README both wrote `never`, and both
  hooks matched `off` alone. The setting silently did nothing. `off` stays as an alias.
- `extends` resolves the whole chain. A profile that extended `docs` lost every phrase entry
  `peer-eng` added, because the loader walked one parent only. A cycle now terminates.
- `--fix` never deletes a word that also reads as a noun or a verb.
  It shortened "the leverage ratio" to "the ratio". Only a known adjective goes now, and
  `autofix_adjectives` extends that set.
- `--fix` keeps a closing sentence that carries content. It deleted a rollback instruction,
  because the sentence also held "let me know if". A number, a path, or an imperative verb
  now marks the sentence as substantive.
- A malformed profile section reports nothing instead of raising. A profile with
  `"budget": null` used to raise an AttributeError on every hook invocation.
- `prune_stale` keeps `telemetry.jsonl`. The pruner judged the log by its age, so a user who
  paused for a day lost the whole history.
- The write guard reads the reconstructed file, not the fragment. A small edit fell under the
  word floor, and a banned phrase formed across an edit boundary never appeared in the
  fragment. The guard now reports only the violations the call introduces, so a defect
  already on disk never blocks an unrelated edit.
- The pi extension holds its state per registration. `chain` and `lastAssistantText` were
  module globals, so a second registration inherited the first one's counter.
- The pi extension keeps the chain counter when it gives up. It reset the counter at the cap,
  so the next reply started a fresh chain and the cap never held.
- The pi extension reports a checker failure. Every exec error and JSON error died in
  silence, so a missing `python3` disabled enforcement with no signal.

### Changed

- The Codex install notes say four hooks. The installer has written four since 0.6.0.

## [0.6.0] - 2026-08-12

### Added

- A write guard. A `PreToolUse` hook checks the markdown a `Write`, an `Edit`, or a
  `MultiEdit` puts on disk. The Stop hook reads chat text only, so a README or a spec written
  through a file tool never met a rule before this release.
- The `docs` profile. It runs full STE with no word ceiling, because a chat ceiling means
  nothing in a file. The write guard runs this profile whatever the session runs.
- A `write_guard` block in the profile schema. It holds `enabled`, `mode`, `profile`, and
  `suffixes`. In `warn` mode the hook reports the violations and lets the write land.
- `scripts/ste-setup.py` and the `/ste-setup` command. A user picks the register, the write
  guard mode, the rule card timing, the telemetry switch, and any single rule. The script
  writes `~/.claude/ste-guard.json` and backs up the file it replaces.
- The `STE_GUARD_CONFIG` environment variable, which moves the user config file.
- The `STE_GUARD_WRITE_OFF` environment variable, which stops the write guard alone.

### Changed

- `load_profile()` takes an optional profile name. The write guard pins the lint profile, so
  the session profile never reaches it.
- `commands/` now ships in the npm package.

### Notes

- The write guard reads `.md`, `.markdown`, and `.mdx` by default. A comment in a source file,
  a commit message, and a PR body all pass with no check.

## [0.5.0] - 2026-08-12

### Added

- About 150 entries in the banned phrase lists. The puffery list takes the marketing phrases:
  empty intensifiers, vague value claims, corporate sludge, product sludge, fake specificity,
  consultant voice, and agent bingo. The flourish list takes the transition cliches and the
  faux-nuance hedges, so they apply where the register rules apply.
- `load bearing`, `load-bearing`, and `idempotent` in the flourish list.
- `say the word` and `say go` in the closer list.

### Changed

- The phrase lists ban a phrase, not a word that carries meaning. Words such as `scalable`,
  `secure`, `deterministic`, and `distributed` stay legal, because the puffery rule matches on
  a word prefix and would flag correct technical prose. Agent domain nouns such as
  `guardrails`, `memory layer`, and `multi-agent system` stay legal for the same reason.
- Only a single alphabetic entry reaches the `--fix` pass. Every phrase is flag-only, so the
  fixer never deletes a phrase it cannot replace.

### Fixed

- `--fix` repairs the article when it deletes an adjective. "a comprehensive audit" now becomes
  "an audit", and "an innovative parser" becomes "a parser". The repair judges the article by
  sound, so "a robust user guide" becomes "a user guide". It touches only the article beside
  the deleted word.

## [0.4.0] - 2026-08-08

### Added

- Opt-in telemetry. Each turn appends one line to `telemetry.jsonl` with the word count, the
  rule numbers, and the block decision. The line never holds the message text. Turn it on
  with `"telemetry": true` in a profile, or with `STE_GUARD_TELEMETRY=1`.
- `scripts/ste-stats.py`, which reports the block rate, the violations per 100 words, and the
  share each rule contributes. Use it to find the rules that only nag.
- `ste-check --fix`. It deletes a filler opener, a hollow closing sentence, and a puffery
  adjective that stands before a noun. It never rewrites a sentence, and it lists what still
  needs a person.
- A signal when the hook gives up. After the chain cap or the repeat guard, the hook now
  emits a `systemMessage` instead of passing the reply through in silence.

### Changed

- A table cell now counts toward the word ceiling. A 30-row table used to score zero words,
  so a very long reply passed a 130-word ceiling untouched.
- A sentence rule never judges a table row. Two cells on one line read as one sentence, which
  produced false gerund and aside violations. The word count still sees the cells.
- A word-budget violation now names the longest block and says how many words to cut.

## [0.3.1] - 2026-08-08

### Fixed

- An `-ed` word that acts as an adjective no longer counts as passive voice. Phrases such as
  "the flag is required" and "the hook is enabled" are ordinary technical prose. A run over
  68 paragraphs of published documentation dropped from 28 passive hits to 6, and the share
  of flagged paragraphs fell from 7 percent to 3 percent.

### Added

- A parity test that runs the same samples through the Stop hook and through the checker.
  Claude Code and Codex read the Stop hook. The pi extension reads the checker. The test
  fails when the two disagree.
- Regression tests for the adjectival participles and for real passive voice.

## [0.3.0] - 2026-08-08

### Added

- pi support. `package.json` carries the `pi` key and the `pi-package` keyword, so one npm
  install brings the extension and the skill. No build step runs, because pi loads the
  TypeScript through jiti.
- `extensions/ste-guard.ts`. It hooks `agent_end`, runs the Python checker through
  `pi.exec`, and calls `pi.sendUserMessage` with `deliverAs: "followUp"` on a failure.
- `ste_rules.verdict()`, the one decision all three agents share.
- `ste_rules.rewrite_prompt()`, the one correction wording all three agents send.
- A `--json` mode on `ste-check`, which prints the verdict for the pi extension.
- A Node test suite for the extension, run with the built-in test runner.

### Changed

- `stop-lint.py` now calls `verdict()` instead of its own copy of the threshold logic.
  Behaviour does not change.

### Notes

- pi has no block primitive on an assistant message. The extension therefore asks for a
  rewrite through a follow-up user message, which matches the Codex behaviour.
- The rules never move into TypeScript. A test asserts the extension holds no phrase list.

## [0.2.0] - 2026-08-08

### Added

- Codex support. A `.codex-plugin/plugin.json` manifest makes the `ste` skill available in
  Codex, and `hooks/codex-hooks.json` declares the same three hooks against `${PLUGIN_ROOT}`.
- `scripts/codex-install.py`, which wires the hooks into `~/.codex/hooks.json` by absolute
  path. Codex v0.147 installs a plugin's skills but does not load the hooks it ships. The
  script backs up the file, strips the predecessor entries, and never stacks duplicates.

### Notes

- Codex reads `.claude-plugin/marketplace.json` directly, so one marketplace serves both
  agents.
- A Codex `Stop` hook that returns `decision: block` continues the turn with the reason as a
  new prompt. It does not reject the reply, so the first draft stays in the transcript.

## [0.1.1] - 2026-08-08

### Fixed

- A user profile that extends a bundled profile now keeps the parent's `lists_add` and
  `lists_remove` deltas. Before this fix, a child that set only a scalar discarded every
  phrase its parent added.

### Added

- The `STE_GUARD_STATE_DIR` environment variable, so a test run never touches the real state.
- A smoke test suite that uses the standard library only, plus a CI workflow.

## [0.1.0] - 2026-08-08

First release.

### Added

- A `Stop` hook that checks each reply against the active profile. The hook blocks one time
  and returns the violations, so Claude rewrites and sends the clean version.
- A `SessionStart` hook that injects a short rule card one time per session.
- A `UserPromptSubmit` hook that injects the full rule text with the exact banned strings.
  The default lazy mode keeps this hook silent until the `Stop` hook blocks one time.
- A `ste-check` pre-flight linter, shipped as the `ste` skill and as the `/ste-check` command.
- JSON profiles for every threshold, rule switch, and phrase list. A profile inherits from a
  bundled parent with `extends`, and tunes one list with `lists_add` or `lists_remove`.
- The bundled `default` profile: the ASD-STE100 chat subset with a 250-word ceiling.
- The bundled `peer-eng` profile: a blunt register with a 130-word ceiling and every rule on.
- An `STE` output style.
- A quoted-text exemption. The checker blanks any run inside double quotes before it applies
  the phrase lists, so a cited phrase never counts as a violation.
- The `STE_GUARD_OFF`, `STE_GUARD_DEBUG`, and `STE_GUARD_PROFILE` environment variables.

[0.4.0]: https://github.com/ofrusch/ste-guard/releases/tag/v0.4.0
[0.3.1]: https://github.com/ofrusch/ste-guard/releases/tag/v0.3.1
[0.3.0]: https://github.com/ofrusch/ste-guard/releases/tag/v0.3.0
[0.2.0]: https://github.com/ofrusch/ste-guard/releases/tag/v0.2.0
[0.1.1]: https://github.com/ofrusch/ste-guard/releases/tag/v0.1.1
[0.1.0]: https://github.com/ofrusch/ste-guard/releases/tag/v0.1.0
