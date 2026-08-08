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

STATE_DIR = pathlib.Path(os.path.expanduser("~/.claude/.ste-guard-state"))
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

    if cfg.get("extends"):
        parent = _read_json(BUNDLED_PROFILES / f"{cfg['extends']}.json") or {}
        base = _deep_merge(base, parent)

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
    text = re.sub(r"^\s*(?:[|>].*|\s{4,}\S.*)$", " ", text, flags=re.M)
    text = re.sub(r"https?://\S+", " URL ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\S+/\S+\.\w+(?::\d+)?", " PATH ", text)
    text = re.sub(r"[*_#]+", "", text)

    return text


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


def find_phrase_hits(profile, prose):
    """Banned phrase checks. Quoted runs are exempt, because a citation is not a use."""
    hits = []

    citable = strip_quoted(prose)
    lowered = citable.lower()

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
        if MID_ASIDE.search(citable):
            hits.append("Rule 18 — mid-sentence em-dash aside. Split it into two sentences.")

        if PAREN_ASIDE.search(citable):
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

    return [f"Rule 0 — {total} words, ceiling is {ceiling}. Cut it down. Bullets, not prose."]


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
            if passive:
                hits.append(f'Rule 10 — passive voice "{passive.group(0)}". Name the actor.')

    return hits


def lint(profile, raw):
    """Run every enabled rule. Returns the hard list and the soft list separately."""
    prose = strip_noise(raw)

    hard = find_phrase_hits(profile, prose)
    hard += find_budget(profile, raw, prose)
    hard += find_prose_wall(profile, raw)

    soft = find_soft(profile, split_sentences(prose))

    return hard, soft, prose


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
