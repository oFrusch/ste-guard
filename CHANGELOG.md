# Changelog

All notable changes to ste-guard appear in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.3.1]: https://github.com/ofrusch/ste-guard/releases/tag/v0.3.1
[0.3.0]: https://github.com/ofrusch/ste-guard/releases/tag/v0.3.0
[0.2.0]: https://github.com/ofrusch/ste-guard/releases/tag/v0.2.0
[0.1.1]: https://github.com/ofrusch/ste-guard/releases/tag/v0.1.1
[0.1.0]: https://github.com/ofrusch/ste-guard/releases/tag/v0.1.0
