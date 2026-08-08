#!/usr/bin/env python3
"""Stop hook. Lints the assistant's last message and blocks once so the model rewrites.

Set STE_GUARD_OFF=1 to disable. STE_GUARD_DEBUG=1 writes the verdict to stderr.
A block also arms the lazy contract, which the prompt hook injects on the next turn.
"""

import hashlib
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import ste_rules


def allow():
    sys.exit(0)


def last_message_from_transcript(path):
    if not path or not os.path.exists(path):
        return ""

    text = ""

    try:
        with open(path) as handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue

                message = entry.get("message") or {}
                if message.get("role") != "assistant":
                    continue

                content = message.get("content")

                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    blocks = [
                        b.get("text", "")
                        for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    if blocks:
                        text = "\n".join(blocks)
    except OSError:
        return ""

    return text


def main():
    if os.environ.get("STE_GUARD_OFF"):
        allow()

    try:
        payload = json.load(sys.stdin)
    except ValueError:
        allow()

    profile = ste_rules.load_profile()
    session = payload.get("session_id", "unknown")
    record = ste_rules.load_state(session)

    def clear_chain_and_allow():
        """Any allowed turn ends the block chain. Otherwise a short message wedges it shut."""
        if record.get("chain"):
            record.update({"digest": "", "blocks": 0, "chain": 0})
            ste_rules.save_state(session, record)
        allow()

    if payload.get("stop_hook_active"):
        clear_chain_and_allow()

    message = payload.get("last_assistant_message") or ""
    if not message:
        message = last_message_from_transcript(payload.get("transcript_path"))

    if not message.strip():
        clear_chain_and_allow()

    hard, soft, prose = ste_rules.lint(profile, message)

    if ste_rules.word_count(prose) < profile.get("min_words_to_lint", 25):
        clear_chain_and_allow()

    threshold = profile.get("soft_block_threshold", 3)
    violations = hard + (soft if len(soft) >= threshold or hard else [])

    if os.environ.get("STE_GUARD_DEBUG"):
        print(f"ste-guard: {len(hard)} hard, {len(soft)} soft", file=sys.stderr)

    if not violations:
        clear_chain_and_allow()

    digest = hashlib.md5(message.encode("utf-8", "replace")).hexdigest()
    per_message = profile.get("max_blocks_per_message", 1)
    per_chain = profile.get("max_blocks_per_chain", 2)

    # A rewrite is a new digest, so the per-message guard alone cannot stop a ping-pong.
    # The chain budget caps consecutive blocks and only resets on a message that passes.
    if record.get("digest") == digest and record.get("blocks", 0) >= per_message:
        allow()

    if record.get("chain", 0) >= per_chain:
        record.update({"digest": digest, "blocks": 1})
        ste_rules.save_state(session, record)
        allow()

    blocks = record.get("blocks", 0) + 1 if record.get("digest") == digest else 1

    record.update({"digest": digest, "blocks": blocks, "chain": record.get("chain", 0) + 1, "armed": True})
    ste_rules.save_state(session, record)

    if blocks > per_message:
        allow()

    listed = "\n".join(f"  - {item}" for item in violations[:8])
    reason = (
        "STE lint failed on your last message. Rewrite it, then stop.\n"
        "Keep the same content and the same conclusions. Fix only the prose.\n\n"
        f"{listed}\n\n"
        "Do not explain the rewrite. Just send the clean version."
    )

    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


if __name__ == "__main__":
    main()
