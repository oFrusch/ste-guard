# Changelog

All notable changes to ste-guard appear in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.0]: https://github.com/ofrusch/ste-guard/releases/tag/v0.1.0
