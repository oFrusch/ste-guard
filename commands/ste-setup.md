---
description: Pick which ste-guard features you want, then write the config
---

Configure ste-guard for this user. The script writes `~/.claude/ste-guard.json`.

First run `"${CLAUDE_PLUGIN_ROOT}"/scripts/ste-setup.py --show` and report the current settings.

When `$ARGUMENTS` names the settings the user wants, skip the questions. Map the request onto
the flags below and run the script one time.

Otherwise ask the user with `AskUserQuestion`. Ask these four questions in one call:

1. **Register.** `default` for grammar only with a 250-word ceiling. `peer-eng` for the blunt
   register with a 130-word ceiling and every rule on.
2. **Write guard.** `deny` blocks a markdown write that fails a rule. `warn` lets the write
   land and reports the violations. `off` checks replies only.
3. **Rule card.** `lazy` injects the full rule text only after a reply fails one time.
   `always` injects it every turn. `never` injects nothing, and the reply guard still blocks.
4. **Telemetry.** `on` records one line per turn, with counts only and no message text.

Then run the script with the matching flags:

```
"${CLAUDE_PLUGIN_ROOT}"/scripts/ste-setup.py \
  --profile <default|peer-eng> \
  --write-guard <deny|warn|off> \
  --injection <lazy|always|never> \
  --telemetry <on|off>
```

Report the written config. When the script warns about `STE_GUARD_PROFILE`, tell the user that
the environment variable wins over the file, and name the variable.

Other flags, for a user who asks for one:

- `--rules-off a,b` and `--rules-on a,b` switch one rule at a time. The names are `openers`,
  `closers`, `puffery`, `not_just`, `asides`, `gerund`, `passive`, `narration`, `flourish`,
  and `prose_wall`.
- `--write-suffixes .md,.mdx` sets the file types the write guard reads.
- `--reset` deletes the config, and ste-guard falls back to the bundled default profile.
