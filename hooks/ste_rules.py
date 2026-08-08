#!/usr/bin/env python3
"""Core lint engine for ste-guard. Shared by the Stop hook, the contract hook, and the CLI.

Every threshold and phrase list comes from a profile, so no caller hardcodes a value.
See README.md for the profile schema and the resolution order.
"""

import json
import os
import pathlib
import re

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent
BUNDLED_PROFILES = PLUGIN_ROOT / "profiles"
USER_CONFIG = pathlib.Path(os.path.expanduser("~/.claude/ste-guard.json"))

STATE_DIR = pathlib.Path(
    os.environ.get("STE_GUARD_STATE_DIR") or os.path.expanduser("~/.claude/.ste-guard-state")
)
STATE_TTL_SECONDS = 24 * 60 * 60
SESSION_KEY_OK = re.compile(r"[^A-Za-z0-9._-]")


# ---------------------------------------------------------------- profile


def _read_json(path):
    try:
        return json.loads(pathlib.Path(path).read_text())
    except (OSError, ValueError):
        return None


def _merge_lists(base, cfg):
    """Apply the add and remove deltas so a user tunes one list without restating it."""
    merged = {name: list(items) for name, items in base.items()}

    for name, items in (cfg.get("lists") or {}).items():
        merged[name] = list(items)

    for name, items in (cfg.get("lists_add") or {}).items():
        merged.setdefault(name, [])
        merged[name] = merged[name] + [i for i in items if i not in merged[name]]

    for name, items in (cfg.get("lists_remove") or {}).items():
        drop = {i.lower() for i in items}
        merged[name] = [i for i in merged.get(name, []) if i.lower() not in drop]

    return merged


def load_profile():
    """Resolve the active profile. Env override, then user config, then the bundled default."""
    base = _read_json(BUNDLED_PROFILES / "default.json") or {}

    named = os.environ.get("STE_GUARD_PROFILE")
    cfg = None

    if named:
        cfg = _read_json(BUNDLED_PROFILES / f"{named}.json") or _read_json(named)

    if cfg is None:
        cfg = _read_json(USER_CONFIG)

    if cfg is None:
        cfg = {}

    # The parent's own list deltas must land before the child's, or a grandchild config
    # that only sets a scalar silently discards every phrase its parent added.
    if cfg.get("extends"):
        parent = _read_json(BUNDLED_PROFILES / f"{cfg['extends']}.json") or {}
        inherited = _merge_lists(base.get("lists") or {}, parent)
        base = _deep_merge(base, parent)
        base["lists"] = inherited

    profile = _deep_merge(base, cfg)
    profile["lists"] = _merge_lists(base.get("lists") or {}, cfg)

    return profile


def _deep_merge(base, top):
    out = dict(base)

    for key, value in top.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value

    return out


# ---------------------------------------------------------------- patterns

NOT_JUST = re.compile(r"\b(is|are|isn't|aren't|it's) not (just|only)\b.*\bit'?s\b", re.I)

# An em-dash or parenthetical that interrupts a sentence, rather than trailing it.
# The classes exclude newlines so consecutive bullets with "label - text" never pair up.
MID_ASIDE = re.compile(r"[a-z,]\s+[—–]\s+\w[^—–\n]{4,}?\s+[—–]\s+\w")
PAREN_ASIDE = re.compile(r"[a-z,]\s+\([^)\n]{12,}\)\s+\w")

PARTICIPLE = (
    r"(?:[a-z]+ed|done|made|seen|taken|given|known|shown|built|held|found|kept|"
    r"sent|left|put|set|written|driven|chosen|broken|spoken|drawn|thrown)"
)
PASSIVE = re.compile(rf"\b(?:is|are|was|were|been|being|be)\s+(?:\w+ly\s+)?{PARTICIPLE}\b", re.I)

# These -ed words act as adjectives after a linking verb, so "the flag is required" is not
# passive voice. Without this list the checker flags a third of ordinary technical prose.
ADJECTIVAL = {
    "unchanged", "required", "enabled", "disabled", "restricted", "related", "limited",
    "detailed", "advanced", "dedicated", "complicated", "involved", "interested",
    "experienced", "supported", "deprecated", "expected", "unexpected", "reserved",
    "recommended", "unrelated", "unsupported", "undefined", "unused", "malformed",
}

# An -ing opener that is a real gerund clause, not a progressive verb or a known noun.
GERUND_OPENER = re.compile(r"^([A-Z][a-z]+ing)\b(?!\s+(?:is|are|was|were))")
GERUND_ALLOW = {"Something", "Nothing", "Everything", "Anything", "During", "Bring", "String", "Thing"}

ABBREV = re.compile(r"\b(?:e\.g|i\.e|etc|vs|Mr|Ms|Dr|approx|no|fig|ref|cf|al)\.$", re.I)

HEADING_HINT = re.compile(
    r"^#{1,3}\s|\bimplementation plan\b|\bdesign spec\b|^\s*##\s|\bADR-\d", re.I | re.M
)

# A short run inside straight or curly double quotes reads as a citation, not as authored prose.
QUOTED_SPAN = re.compile(r"[\"“]([^\"”\n]{1,120})[\"”]")


# ---------------------------------------------------------------- text prep


def strip_noise(text):
    """Remove code, links, and paths. The linter judges prose only."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"~~~.*?~~~", " ", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " CODE ", text)

    # A table cell holds prose the author wrote, so its words count. Only the pipes and the
    # separator row go. A block quote stays exempt, because a quote cites someone else.
    text = re.sub(r"^\s*\|[\s:|-]*\|\s*$", " ", text, flags=re.M)
    text = re.sub(r"^(\s*)\|(.*)\|(\s*)$", r"\1\2\3", text, flags=re.M)
    text = text.replace("|", " ")

    text = re.sub(r"^\s*(?:>.*|\s{4,}\S.*)$", " ", text, flags=re.M)
    text = re.sub(r"https?://\S+", " URL ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\S+/\S+\.\w+(?::\d+)?", " PATH ", text)
    text = re.sub(r"[*_#]+", "", text)

    return text


TABLE_ROW = re.compile(r"^\s*\|.*$", re.M)


def drop_tables(text):
    """A table row is a set of fragments, not a sentence.

    Its words still count toward the ceiling, and a puffery word in a cell is still puffery.
    A sentence rule cannot judge it, because two cells on one line read as one sentence.
    """
    return TABLE_ROW.sub(" ", text)


def strip_quoted(text):
    """Blank quoted runs so a cited banned phrase never counts as a violation."""
    return QUOTED_SPAN.sub(" QUOTED ", text)


def split_sentences(text):
    parts, buf = [], ""

    for chunk in re.split(r"(?<=[.!?:])\s+|\n+", text):
        candidate = f"{buf} {chunk}".strip() if buf else chunk.strip()

        if ABBREV.search(candidate):
            buf = candidate
            continue

        buf = ""
        if candidate:
            parts.append(candidate)

    if buf:
        parts.append(buf)

    return parts


def word_count(sentence):
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’-]*", sentence))


# ---------------------------------------------------------------- rules


def _on(profile, rule):
    return bool((profile.get("rules") or {}).get(rule))


def _list(profile, name):
    return (profile.get("lists") or {}).get(name) or []


def find_phrase_hits(profile, prose, sentence_source=None):
    """Banned phrase checks. Quoted runs are exempt, because a citation is not a use."""
    hits = []

    citable = strip_quoted(prose)
    lowered = citable.lower()

    # The aside rules judge sentence shape, so they read the table-free text.
    aside_source = strip_quoted(sentence_source if sentence_source is not None else prose)

    if _on(profile, "openers"):
        head = lowered[: profile["budget"].get("opener_window", 220)]
        for phrase in _list(profile, "openers"):
            if phrase in head:
                hits.append(f'Rule 2 — filler opener "{phrase}". Start at the answer.')

    if _on(profile, "closers"):
        tail = lowered[-profile["budget"].get("closer_window", 320) :]
        for phrase in _list(profile, "closers"):
            if phrase in tail:
                hits.append(f'Rule 7 — hollow closer "{phrase}". Stop when the answer is done.')

    if _on(profile, "puffery"):
        for word in _list(profile, "puffery"):
            if re.search(rf"\b{re.escape(word)}", lowered):
                hits.append(f'Rule 8 — puffery "{word}". Say the concrete thing instead.')

    if _on(profile, "not_just") and NOT_JUST.search(citable):
        hits.append('Rule 8 — the "not just X, it is Y" construction. Cut it.')

    if _on(profile, "narration"):
        for phrase in _list(profile, "narration"):
            if phrase in lowered:
                hits.append(f'Rule 17 — process narration "{phrase}". State the fact, not the discovery.')

    if _on(profile, "flourish"):
        for phrase in _list(profile, "flourish"):
            if phrase in lowered:
                hits.append(f'Rule 19 — literary flourish "{phrase}". Say the plain fact.')

    if _on(profile, "asides"):
        if MID_ASIDE.search(aside_source):
            hits.append("Rule 18 — mid-sentence em-dash aside. Split it into two sentences.")

        if PAREN_ASIDE.search(aside_source):
            hits.append("Rule 18 — mid-sentence parenthetical aside. Split it into two sentences.")

    return hits


def find_budget(profile, raw, prose):
    """Total length is the tax the reader pays. Nothing else in the ruleset caps it."""
    ceiling = profile["budget"].get("words")
    if not ceiling:
        return []

    if profile["budget"].get("uncapped_on_heading", True) and HEADING_HINT.search(raw):
        return []

    total = word_count(prose)
    if total <= ceiling:
        return []

    hint = _longest_chunk(raw)
    where = f" Your longest block runs {hint[0]} words: \"{hint[1]}\"." if hint else ""

    return [
        f"Rule 0 — {total} words, ceiling is {ceiling}. Cut {total - ceiling} or more.{where}"
    ]


def _longest_chunk(raw):
    """Name the fattest bullet or paragraph, because an overshoot needs a target."""
    chunks = [c.strip() for c in re.split(r"\n\s*\n|\n(?=\s*(?:[-*+]\s|\d+[.)]\s))", raw)]
    scored = [(word_count(strip_noise(c)), c) for c in chunks if c]

    if not scored:
        return None

    count, chunk = max(scored, key=lambda pair: pair[0])

    if count < 15:
        return None

    opening = " ".join(strip_noise(chunk).split())[:60]

    return count, f"{opening}..."


def find_prose_wall(profile, raw):
    """Bullets by default. A long message with no list is almost always a wall."""
    if not _on(profile, "prose_wall"):
        return []

    if re.search(r"^\s*(?:[-*+]\s|\d+[.)]\s)", raw, re.M):
        return []

    paragraphs = [p for p in re.split(r"\n\s*\n", raw) if word_count(p) > 35]
    if len(paragraphs) < 2:
        return []

    return [f"Rule 6 — {len(paragraphs)} dense paragraphs and no bullets. Prefer bullets."]


def find_soft(profile, sentences):
    hits = []
    cap = profile["budget"].get("sentence_words")

    for sentence in sentences:
        if cap:
            count = word_count(sentence)
            if count > cap:
                hits.append(f'Rule 11 — {count}-word sentence, cap is {cap}: "{sentence[:70]}..."')

        if _on(profile, "gerund"):
            opener = GERUND_OPENER.match(sentence)
            if opener and opener.group(1) not in GERUND_ALLOW:
                hits.append(f'Rule 12 — sentence opens with the gerund "{opener.group(1)}". Name the actor first.')

        if _on(profile, "passive"):
            passive = PASSIVE.search(sentence)

            if passive and passive.group(0).split()[-1].lower() not in ADJECTIVAL:
                hits.append(f'Rule 10 — passive voice "{passive.group(0)}". Name the actor.')

    return hits


def lint(profile, raw):
    """Run every enabled rule. Returns the hard list and the soft list separately."""
    prose = strip_noise(raw)

    # Two views. The budget counts table words. The sentence rules never see a table row.
    sentence_source = strip_noise(drop_tables(raw))

    hard = find_phrase_hits(profile, prose, sentence_source)
    hard += find_budget(profile, raw, prose)
    hard += find_prose_wall(profile, raw)

    soft = find_soft(profile, split_sentences(sentence_source))

    return hard, soft, prose


def verdict(profile, raw):
    """The one decision every agent target shares. Two implementations would drift."""
    hard, soft, prose = lint(profile, raw)

    words = word_count(prose)
    too_short = words < profile.get("min_words_to_lint", 25)
    threshold = profile.get("soft_block_threshold", 3)

    if too_short:
        violations = []
    else:
        violations = hard + (soft if len(soft) >= threshold or hard else [])

    return {
        "clean": not violations,
        "too_short": too_short,
        "words": words,
        "profile": profile.get("name"),
        "hard": hard,
        "soft": soft,
        "violations": violations,
        "max_blocks_per_chain": profile.get("max_blocks_per_chain", 2),
    }


RULE_ID = re.compile(r"^(Rule \d+)")

# A puffery adjective sits before a noun, so its removal leaves a grammatical phrase.
# "a robust parser" becomes "a parser". A predicate use needs a human, so it stays.
ADJECTIVE_SLOT = r"(?:\b(?:a|an|the|this|that|these|those|our|its|their|and|very|more|most)\s+)"


def autofix(profile, text):
    """Delete the reflex failures that need no judgment. Return the text and what remains.

    The fixer never rewrites a sentence. It removes a filler opener, a hollow closer, and a
    puffery adjective that stands before a noun. Everything else needs a person.
    """
    fixed = text
    handled = []

    for phrase in _list(profile, "openers") if _on(profile, "openers") else []:
        pattern = re.compile(rf"^(\s*(?:[*_#>-]\s*)*){re.escape(phrase)}[.!,]?\s*", re.I)

        if pattern.search(fixed):
            fixed = pattern.sub(r"\1", fixed, count=1)
            handled.append(f'removed the opener "{phrase}"')

    for phrase in _list(profile, "closers") if _on(profile, "closers") else []:
        pattern = re.compile(rf"(?:^|(?<=[.!?\n]))[^.!?\n]*{re.escape(phrase)}[^.!?\n]*[.!?]?\s*$", re.I)

        if pattern.search(fixed):
            fixed = pattern.sub("", fixed, count=1).rstrip() + "\n"
            handled.append(f'removed the closing sentence with "{phrase}"')

    # Only alphabetic entries are safe. A stem such as "game-chang" has no clean boundary.
    adjectives = [w for w in (_list(profile, "puffery") if _on(profile, "puffery") else []) if w.isalpha()]

    # A coordination goes first. "robust and seamless parser" must not leave a stray "and".
    for word in adjectives:
        combo = re.compile(rf"\b{re.escape(word)}\s+and\s+(?=\w)", re.I)

        while combo.search(fixed):
            fixed = combo.sub("", fixed, count=1)
            handled.append(f'removed the puffery "{word}"')

    # Then the lone adjective, but never when a conjunction follows it.
    for word in adjectives:
        pattern = re.compile(
            rf"({ADJECTIVE_SLOT})({re.escape(word)})\s+(?!and\b|or\b)(?=\w)", re.I
        )

        while pattern.search(fixed):
            fixed = pattern.sub(r"\1", fixed, count=1)
            handled.append(f'removed the puffery "{word}"')

    remaining = verdict(profile, fixed)["violations"]

    return fixed, sorted(set(handled)), remaining


def record(profile, result, agent, blocked):
    """Append one line per turn, so a user can measure the rules instead of guessing.

    Off unless the profile sets telemetry or STE_GUARD_TELEMETRY is set. The line holds
    counts and rule numbers only. It never holds the message text.
    """
    import time

    enabled = profile.get("telemetry") or os.environ.get("STE_GUARD_TELEMETRY")

    if not enabled:
        return

    rules = sorted({RULE_ID.match(v).group(1) for v in result["violations"] if RULE_ID.match(v)})

    line = {
        "at": int(time.time()),
        "agent": agent,
        "profile": result["profile"],
        "words": result["words"],
        "clean": result["clean"],
        "too_short": result["too_short"],
        "blocked": blocked,
        "rules": rules,
        "hard": len(result["hard"]),
        "soft": len(result["soft"]),
    }

    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(STATE_DIR / "telemetry.jsonl", "a") as handle:
            handle.write(json.dumps(line) + "\n")
    except OSError:
        pass


def rewrite_prompt(violations, limit=8):
    """The correction text. Every target sends the same wording, so behaviour matches."""
    listed = "\n".join(f"  - {item}" for item in violations[:limit])

    return (
        "STE lint failed on your last message. Rewrite it, then stop.\n"
        "Keep the same content and the same conclusions. Fix only the prose.\n\n"
        f"{listed}\n\n"
        "Do not explain the rewrite. Just send the clean version."
    )


# ---------------------------------------------------------------- state


def state_path(session):
    """One file per session. Concurrent sessions must never share a counter."""
    key = SESSION_KEY_OK.sub("_", session or "unknown")[:120] or "unknown"

    return STATE_DIR / f"{key}.json"


def load_state(session):
    return _read_json(state_path(session)) or {}


def save_state(session, record):
    """Write through a temp file and rename, so a concurrent reader never sees a torn file."""
    import tempfile

    path = state_path(session)

    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="w", dir=STATE_DIR, prefix=".tmp-", suffix=".json", delete=False
        )
        with handle:
            json.dump(record, handle)
        os.replace(handle.name, path)
    except OSError:
        pass

    prune_stale()


def prune_stale():
    import time

    cutoff = time.time() - STATE_TTL_SECONDS

    try:
        for entry in STATE_DIR.iterdir():
            if entry.stat().st_mtime < cutoff:
                entry.unlink()
    except OSError:
        pass
