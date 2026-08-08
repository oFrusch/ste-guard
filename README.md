# ste-guard

A Claude Code plugin that keeps Claude's replies in Simplified Technical English.

Claude talks too much. This makes it talk less.

## What it does

1. A `SessionStart` hook injects a short rule card one time.
2. A `Stop` hook checks each reply. When a rule fails, the hook blocks once and returns the
   violations. Claude rewrites and sends the clean version.
3. A `UserPromptSubmit` hook injects the full rule text with the exact banned strings. In
   the default lazy mode this hook stays silent until the `Stop` hook blocks once.
4. A `ste-check` command lets Claude lint a draft before it sends the draft.

The rules come from ASD-STE100, adapted for chat. This is not certified conformance. The
ASD licenses the official approved dictionary, so this repository does not carry it.

## Why the injection is lazy

An always-on rule injection costs about 1,000 tokens per turn. A 50-turn session pays 50,000
tokens to repeat rules that Claude read at the start.

The lazy mode pays once at session start, then nothing. When Claude breaks a rule, the hook
arms itself and injects the full contract for the rest of the session. A clean session pays
nothing beyond the opening card.

Set `injection` to `always` when you prefer the predictable cost.

## Install

```
claude plugin marketplace add https://github.com/ofrusch/ste-guard.git
claude plugin install ste-guard@ste-guard
```

The `owner/repo` shorthand also works, but Claude Code clones that form over SSH. The full
HTTPS URL above clones over HTTPS instead, so it works without an SSH key. To keep the
shorthand and still clone over HTTPS, set `CLAUDE_CODE_PLUGIN_PREFER_HTTPS=1`.

Optionally set the output style to `STE` with `/output-style`. The hooks work without it.

## Install for Codex

Codex reads the same marketplace file, so the first two steps match.

```
codex plugin marketplace add https://github.com/ofrusch/ste-guard.git
codex plugin add ste-guard@ste-guard
python3 ~/.codex/plugins/cache/ste-guard/ste-guard/<version>/scripts/codex-install.py
```

The third step exists because Codex v0.147 installs a plugin's skills but does not load the
hooks the plugin ships. The script writes the three hook entries into `~/.codex/hooks.json`
by absolute path. It backs the file up first, it leaves your other hooks alone, and it never
stacks duplicates. Run it again after a plugin update, because the version sits in the path.

Codex asks you to trust each new hook command on the next interactive run. Until you approve
them, Codex skips the hooks without a warning. Run `codex` once and accept the three prompts.

Remove the entries with `--uninstall`.

### What differs on Codex

- A Codex `Stop` hook that blocks does not reject the reply. Codex continues the turn with
  the violations as a new prompt, so the first draft stays in the transcript.
- The `ste` skill loads from the plugin with no extra step.

## Configuration

ste-guard resolves the active profile in this order:

1. The `STE_GUARD_PROFILE` environment variable, read as a bundled profile name or a file
   path.
2. The file at `~/.claude/ste-guard.json`.
3. The bundled `profiles/default.json`.

A user profile does not need to restate the whole schema. Name a parent with `extends`, then
override only the keys you want.

### Profile schema

| Key | Type | Meaning |
| :-- | :-- | :-- |
| `extends` | string | A bundled profile name to inherit from |
| `injection` | string | `lazy`, `always`, or `off` |
| `min_words_to_lint` | number | Replies shorter than this are never checked |
| `soft_block_threshold` | number | Soft violations needed to block on their own |
| `max_blocks_per_message` | number | Blocks allowed against one message digest |
| `max_blocks_per_chain` | number | Consecutive blocks before the hook gives up |
| `budget.words` | number or null | Word ceiling per reply. `null` removes the cap |
| `budget.sentence_words` | number or null | Word ceiling per sentence |
| `budget.uncapped_on_heading` | boolean | A markdown heading lifts the word ceiling |
| `rules.*` | boolean | One switch per rule. See the table below |
| `lists.*` | array | Replaces a phrase list |
| `lists_add.*` | array | Appends to a phrase list |
| `lists_remove.*` | array | Removes entries from a phrase list |

### Rule switches

| Switch | What it catches |
| :-- | :-- |
| `openers` | Filler openers such as a warm-up compliment |
| `closers` | Hollow sign-offs |
| `puffery` | Marketing adjectives |
| `not_just` | The "not just X, it is Y" construction |
| `asides` | Mid-sentence parenthetical and em-dash interruptions |
| `gerund` | A sentence that opens with an -ing form |
| `passive` | Passive voice |
| `narration` | Process narration, which reports the search instead of the finding |
| `flourish` | Wordplay and rhetorical symmetry |
| `prose_wall` | A long reply with dense paragraphs and no bullets |

### Bundled profiles

- `default` — the ASD-STE100 chat subset with a 250-word ceiling. Grammar only, no voice.
- `peer-eng` — a blunt senior-engineer register. A 130-word ceiling, bullets by default,
  every rule on.

### Example

Write `~/.claude/ste-guard.json` to keep the grammar rules and drop the word ceiling:

```json
{
  "extends": "default",
  "budget": { "words": null },
  "lists_add": { "puffery": ["ecosystem", "journey"] }
}
```

## Quoted text is exempt

The checker blanks any run inside double quotes before it applies the phrase lists. Claude
can therefore name a banned phrase when it explains the phrase to you. Claude cannot use one.
Inline code, fenced code, block quotes, links, and file paths are also exempt.

## Environment variables

| Variable | Effect |
| :-- | :-- |
| `STE_GUARD_OFF=1` | Disables every hook |
| `STE_GUARD_DEBUG=1` | Writes the hard and soft counts to stderr |
| `STE_GUARD_PROFILE` | Selects a bundled profile by name, or a profile file by path |

## Limits

- No Claude Code hook rewrites a reply in place. The `Stop` hook can only block and hand back
  the violations. A rewrite therefore costs a second generation.
- The word ceiling and the bullets rule need judgment, so a regular expression cannot fix
  them. Only a rewrite can.
- The checker matches fixed strings. A model that invents a new filler phrase gets through
  until you add the phrase to a list.

## Tests

The suite uses the standard library only, so it needs no install step.

```
python3 -m unittest discover -s tests -v
```

Four of the tests run the plugin's own documentation through the checker, so the docs cannot
drift out of conformance without a red build.

## Related work

- [AminBlg/SimpleEnglish](https://github.com/AminBlg/SimpleEnglish) — an STE skill and plugin
  that gates file writes through a `PreToolUse` hook, with published benchmarks.
- [danyuchn/asd-ste100-skill](https://github.com/danyuchn/asd-ste100-skill) — the ASD-STE100
  rules packaged as a skill.

ste-guard differs in one way. It gates the reply, not the file write.

## License

MIT
