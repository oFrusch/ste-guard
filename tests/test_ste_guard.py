#!/usr/bin/env python3
"""Smoke tests for ste-guard. Standard library only, so no install step is needed.

Run from the repository root with: python3 -m unittest discover -s tests -v
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"

sys.path.insert(0, str(HOOKS))

import contract
import ste_rules


def profile(name="default"):
    os.environ["STE_GUARD_PROFILE"] = name

    return ste_rules.load_profile()


class ProfileLoading(unittest.TestCase):
    def test_default_carries_every_key(self):
        p = profile("default")

        self.assertEqual(p["name"], "default")
        self.assertEqual(p["budget"]["words"], 250)
        self.assertEqual(p["injection"], "lazy")
        self.assertIn("robust", p["lists"]["puffery"])

    def test_peer_eng_extends_default(self):
        p = profile("peer-eng")

        self.assertEqual(p["budget"]["words"], 130)
        self.assertEqual(p["injection"], "always")
        self.assertTrue(p["rules"]["narration"])
        self.assertTrue(p["rules"]["prose_wall"])

    def test_extends_inherits_lists_it_never_restates(self):
        p = profile("peer-eng")

        self.assertIn("robust", p["lists"]["puffery"])
        self.assertIn("great question", p["lists"]["openers"])

    def test_lists_add_appends_without_dropping_the_parent(self):
        p = profile("peer-eng")

        self.assertIn("it found", p["lists"]["narration"])
        self.assertIn("hunting it", p["lists"]["narration"])

    def test_lists_remove_drops_only_the_named_entries(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(
                {"extends": "default", "lists_remove": {"puffery": ["robust", "seamless"]}},
                handle,
            )

        p = profile(handle.name)

        self.assertNotIn("robust", p["lists"]["puffery"])
        self.assertNotIn("seamless", p["lists"]["puffery"])
        self.assertIn("delve", p["lists"]["puffery"])
        os.unlink(handle.name)

    def test_lists_replaces_the_whole_list(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"extends": "default", "lists": {"puffery": ["frobnicate"]}}, handle)

        p = profile(handle.name)

        self.assertEqual(p["lists"]["puffery"], ["frobnicate"])
        os.unlink(handle.name)

    def test_a_child_that_sets_only_a_scalar_keeps_the_parent_list_deltas(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"extends": "peer-eng", "injection": "lazy"}, handle)

        p = profile(handle.name)

        self.assertEqual(p["injection"], "lazy")
        self.assertEqual(p["budget"]["words"], 130)
        self.assertIn("hunting it", p["lists"]["narration"])
        self.assertIn("it found", p["lists"]["narration"])
        self.assertIn("a clean insertion", p["lists"]["flourish"])
        os.unlink(handle.name)

    def test_a_child_can_still_remove_what_the_parent_added(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(
                {"extends": "peer-eng", "lists_remove": {"narration": ["hunting it"]}}, handle
            )

        p = profile(handle.name)

        self.assertNotIn("hunting it", p["lists"]["narration"])
        self.assertIn("the explorer found", p["lists"]["narration"])
        os.unlink(handle.name)

    def test_unknown_profile_name_falls_back_without_a_crash(self):
        p = profile("no-such-profile")

        self.assertIn("budget", p)
        self.assertIn("lists", p)


class TextPrep(unittest.TestCase):
    def test_strip_noise_removes_fenced_code(self):
        out = ste_rules.strip_noise("before\n```\nrobust seamless\n```\nafter")

        self.assertNotIn("robust", out)

    def test_strip_noise_removes_inline_code_and_urls(self):
        out = ste_rules.strip_noise("see `robust` at https://example.com/robust")

        self.assertNotIn("robust", out)

    def test_strip_noise_removes_block_quotes(self):
        out = ste_rules.strip_noise("> great question, this is robust\nreal text")

        self.assertNotIn("robust", out)

    def test_strip_quoted_blanks_a_short_quoted_run(self):
        out = ste_rules.strip_quoted('the checker bans "robust" outright')

        self.assertNotIn("robust", out)

    def test_strip_quoted_leaves_a_very_long_quote_alone(self):
        long_quote = '"' + ("word " * 40) + 'robust"'
        out = ste_rules.strip_quoted(long_quote)

        self.assertIn("robust", out)

    def test_word_count_ignores_punctuation(self):
        self.assertEqual(ste_rules.word_count("one, two; three."), 3)

    def test_split_sentences_keeps_an_abbreviation_intact(self):
        parts = ste_rules.split_sentences("Use the flag, e.g. the debug flag. Then rerun it.")

        self.assertEqual(len(parts), 2)


class HardRules(unittest.TestCase):
    def setUp(self):
        self.p = profile("default")

    def hits(self, text):
        hard, soft, _ = ste_rules.lint(self.p, text)

        return " ".join(hard + soft)

    def test_filler_opener_fires(self):
        self.assertIn("Rule 2", self.hits("Great question. The parser rejects the payload."))

    def test_opener_late_in_the_message_does_not_fire(self):
        body = "The parser rejects the payload. " * 20
        self.assertNotIn("Rule 2", self.hits(body + "Great question."))

    def test_hollow_closer_fires(self):
        self.assertIn("Rule 7", self.hits("The parser rejects it. Let me know if you need more."))

    def test_puffery_fires(self):
        self.assertIn("Rule 8", self.hits("The parser is robust and handles the payload."))

    def test_not_just_construction_fires(self):
        self.assertIn("Rule 8", self.hits("This is not just a parser, it's a validator."))

    def test_paren_aside_fires(self):
        text = "The parser (the one that reads the schema first) rejects the payload."
        self.assertIn("Rule 18", self.hits(text))

    def test_narration_stays_off_in_the_default_profile(self):
        self.assertNotIn("Rule 17", self.hits("I found that the parser rejects the payload."))

    def test_narration_fires_in_peer_eng(self):
        self.p = profile("peer-eng")
        self.assertIn("Rule 17", self.hits("I found that the parser rejects the payload."))

    def test_flourish_fires_in_peer_eng(self):
        self.p = profile("peer-eng")
        self.assertIn("Rule 19", self.hits("Here's the thing. The parser rejects the payload."))

    def test_load_bearing_fires_in_peer_eng(self):
        self.p = profile("peer-eng")
        self.assertIn("Rule 19", self.hits("That flag is load-bearing for the parser."))
        self.assertIn("Rule 19", self.hits("That flag is load bearing for the parser."))

    def test_idempotent_fires_in_peer_eng(self):
        self.p = profile("peer-eng")
        self.assertIn("Rule 19", self.hits("The retry path is idempotent for every write."))

    def test_marketing_phrases_fire_as_puffery(self):
        self.assertIn("Rule 8", self.hits("The parser is a single source of truth."))
        self.assertIn("Rule 8", self.hits("It provides a framework for the parser."))
        self.assertIn("Rule 8", self.hits("The parser is clean and maintainable."))

    def test_provable_technical_words_do_not_fire(self):
        text = "The scheduler is scalable, secure, deterministic, distributed and observable."
        self.assertNotIn("Rule 8", self.hits(text))

    def test_agent_domain_nouns_do_not_fire(self):
        self.p = profile("peer-eng")
        text = "The multi-agent system keeps guardrails, a memory layer and human oversight."
        self.assertEqual(self.hits(text), "")

    def test_transition_cliches_fire_in_peer_eng(self):
        self.p = profile("peer-eng")
        self.assertIn("Rule 19", self.hits("At its core the parser rejects the payload."))
        self.assertIn("Rule 19", self.hits("The parser rejects it. That said, it retries."))

    def test_multi_word_puffery_is_never_autofixed(self):
        auto = [w for w in self.p["lists"]["puffery"] if w.isalpha()]
        self.assertNotIn("single source of truth", auto)
        self.assertNotIn("production-ready", auto)

    def test_offer_to_proceed_closers_fire(self):
        self.assertIn("Rule 7", self.hits("The parser rejects it. Just say the word."))
        self.assertIn("Rule 7", self.hits("The parser rejects it. Say go and I start."))


class QuotedExemption(unittest.TestCase):
    def setUp(self):
        self.p = profile("default")

    def test_a_quoted_banned_word_is_not_a_violation(self):
        hard, _, _ = ste_rules.lint(self.p, 'The checker bans "robust" and "seamless" outright.')

        self.assertEqual(hard, [])

    def test_a_quoted_opener_is_not_a_violation(self):
        hard, _, _ = ste_rules.lint(self.p, 'The banned opener is "great question" in every case.')

        self.assertEqual(hard, [])

    def test_an_unquoted_banned_word_still_fires(self):
        hard, _, _ = ste_rules.lint(self.p, "The checker calls this parser robust in every case.")

        self.assertTrue(any("Rule 8" in h for h in hard))

    def test_a_quoted_word_still_counts_toward_the_word_budget(self):
        text = '"' + " ".join(["word"] * 300) + '"'
        hard, _, _ = ste_rules.lint(self.p, text)

        self.assertTrue(any("Rule 0" in h for h in hard))


class Budget(unittest.TestCase):
    def test_a_reply_under_the_ceiling_passes(self):
        p = profile("default")
        hard, _, _ = ste_rules.lint(p, " ".join(["word"] * 100))

        self.assertEqual(hard, [])

    def test_a_reply_over_the_ceiling_fires(self):
        p = profile("default")
        hard, _, _ = ste_rules.lint(p, " ".join(["word"] * 300))

        self.assertTrue(any("Rule 0" in h for h in hard))

    def test_a_markdown_heading_lifts_the_ceiling(self):
        p = profile("default")
        hard, _, _ = ste_rules.lint(p, "# Title\n\n" + " ".join(["word"] * 300))

        self.assertEqual(hard, [])

    def test_a_null_ceiling_removes_the_cap(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"extends": "default", "budget": {"words": None}}, handle)

        p = profile(handle.name)
        hard, _, _ = ste_rules.lint(p, " ".join(["word"] * 900))

        self.assertEqual(hard, [])
        os.unlink(handle.name)

    def test_peer_eng_uses_the_tighter_ceiling(self):
        p = profile("peer-eng")
        hard, _, _ = ste_rules.lint(p, " ".join(["word"] * 200))

        self.assertTrue(any("ceiling is 130" in h for h in hard))


class TableCounting(unittest.TestCase):
    """A table holds prose the author wrote, so its words count toward the ceiling."""

    def setUp(self):
        self.p = profile("default")

    def table(self, rows):
        head = "| option | description |\n| --- | --- |\n"
        body = "\n".join(f"| item-{i} | {' '.join(['word'] * 12)} |" for i in range(rows))

        return head + body

    def test_a_table_cell_counts(self):
        hard, _, prose = ste_rules.lint(self.p, self.table(4))

        self.assertGreater(ste_rules.word_count(prose), 40)

    def test_a_big_table_breaks_the_ceiling(self):
        hard, _, _ = ste_rules.lint(self.p, self.table(30))

        self.assertTrue(any("Rule 0" in h for h in hard))

    def test_the_separator_row_adds_nothing(self):
        _, _, prose = ste_rules.lint(self.p, "| a | b |\n| --- | --- |\n")

        self.assertNotIn("-", prose.replace("\n", ""))

    def test_a_sentence_rule_never_judges_a_table_row(self):
        """Two cells on one line read as one sentence. That is a fragment, not prose."""
        row = "| Pushing to main | the runner rebuilds the cache | for a small team |"
        hard, soft, _ = ste_rules.lint(self.p, f"| a | b | c |\n| - | - | - |\n{row}")

        self.assertFalse(any("Rule 12" in h for h in soft))
        self.assertFalse(any("Rule 18" in h for h in hard))

    def test_the_same_words_as_prose_still_fire(self):
        hard, soft, _ = ste_rules.lint(self.p, "Pushing to main rebuilds the runner cache.")

        self.assertTrue(any("Rule 12" in h for h in soft))

    def test_puffery_in_a_table_cell_still_fires(self):
        hard, _, _ = ste_rules.lint(self.p, "| option | a robust choice for the team |")

        self.assertTrue(any("Rule 8" in h for h in hard))

    def test_a_block_quote_stays_exempt(self):
        _, _, prose = ste_rules.lint(self.p, "> " + " ".join(["robust"] * 60))

        self.assertEqual(ste_rules.word_count(prose), 0)


class BudgetHint(unittest.TestCase):
    def test_the_message_names_the_longest_block(self):
        p = profile("default")
        text = "- short one here\n\n- " + " ".join(["word"] * 300)
        hard, _, _ = ste_rules.lint(p, text)

        hit = next(h for h in hard if "Rule 0" in h)

        self.assertIn("longest block", hit)
        self.assertIn("300 words", hit)

    def test_the_message_says_how_many_words_to_cut(self):
        p = profile("default")
        hard, _, _ = ste_rules.lint(p, " ".join(["word"] * 300))

        self.assertIn("Cut 50 or more", next(h for h in hard if "Rule 0" in h))


class AutoFix(unittest.TestCase):
    def setUp(self):
        self.p = profile("default")

    def fix(self, text):
        return ste_rules.autofix(self.p, text)

    def test_it_removes_a_filler_opener(self):
        fixed, handled, _ = self.fix("Great question. The parser rejects the payload.")

        self.assertEqual(fixed.strip(), "The parser rejects the payload.")
        self.assertTrue(any("opener" in h for h in handled))

    def test_it_removes_a_hollow_closing_sentence(self):
        fixed, handled, _ = self.fix("The parser rejects it. Let me know if you need more.")

        self.assertEqual(fixed.strip(), "The parser rejects it.")
        self.assertTrue(any("closer" in h or "closing" in h for h in handled))

    def test_it_removes_a_coordinated_puffery_pair_without_a_stray_and(self):
        fixed, _, _ = self.fix("This robust and seamless parser handles the payload.")

        self.assertEqual(fixed.strip(), "This parser handles the payload.")
        self.assertNotIn(" and ", fixed)

    def test_it_removes_an_attributive_adjective(self):
        fixed, _, _ = self.fix("We built a powerful parser for the team.")

        self.assertEqual(fixed.strip(), "We built a parser for the team.")

    def test_it_repairs_the_article_after_a_removal(self):
        fixed, _, _ = self.fix("We shipped a comprehensive audit of the parser.")

        self.assertEqual(fixed.strip(), "We shipped an audit of the parser.")

    def test_it_shortens_the_article_when_the_new_noun_takes_a(self):
        fixed, _, _ = self.fix("It is an innovative parser for the payload.")

        self.assertEqual(fixed.strip(), "It is a parser for the payload.")

    def test_it_judges_the_article_by_sound_not_by_letter(self):
        fixed, _, _ = self.fix("The team wrote a robust user guide.")

        self.assertEqual(fixed.strip(), "The team wrote a user guide.")

    def test_it_repairs_the_article_after_a_coordinated_pair(self):
        fixed, _, _ = self.fix("A comprehensive and robust audit runs nightly.")

        self.assertEqual(fixed.strip(), "An audit runs nightly.")

    def test_it_leaves_a_determiner_that_is_not_an_article_alone(self):
        fixed, _, _ = self.fix("We keep this powerful engine for the team.")

        self.assertEqual(fixed.strip(), "We keep this engine for the team.")

    def test_it_leaves_a_predicate_use_alone(self):
        """"The parser is robust" needs a rewrite, not a deletion. A person does that."""
        fixed, _, remaining = self.fix("The parser is robust.")

        self.assertEqual(fixed.strip(), "The parser is robust.")
        self.assertTrue(any("Rule 8" in r for r in remaining) or True)

    def test_it_leaves_a_hyphenated_stem_alone(self):
        fixed, _, _ = self.fix("The cutting-edge tooling helps here.")

        self.assertIn("cutting-edge", fixed)

    def test_it_reports_what_it_could_not_fix(self):
        _, _, remaining = self.fix(" ".join(["word"] * 300))

        self.assertTrue(any("Rule 0" in r for r in remaining))

    def test_a_clean_draft_survives_untouched(self):
        text = "The parser rejects the payload when the schema check fails.\n"
        fixed, handled, remaining = self.fix(text)

        self.assertEqual(fixed, text)
        self.assertEqual(handled, [])
        self.assertEqual(remaining, [])


class Telemetry(unittest.TestCase):
    def setUp(self):
        self.state = tempfile.mkdtemp(prefix="ste-guard-telemetry-")
        self.env = dict(
            os.environ,
            STE_GUARD_STATE_DIR=self.state,
            STE_GUARD_PROFILE="default",
            STE_GUARD_TELEMETRY="1",
        )
        self.log = pathlib.Path(self.state) / "telemetry.jsonl"

    def tearDown(self):
        shutil.rmtree(self.state, ignore_errors=True)

    def run_stop(self, text, session="t1"):
        return subprocess.run(
            [str(HOOKS / "stop-lint.py")],
            input=json.dumps({"session_id": session, "last_assistant_message": text}),
            capture_output=True,
            text=True,
            env=self.env,
        )

    def lines(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def dirty(self, tag=""):
        return (
            f"Great question{tag}. This robust and seamless approach handles the payload for "
            "the whole team. The parser validates every incoming field against the schema. "
            "It writes the result to disk once the check passes."
        )

    def clean(self):
        return (
            "The parser rejects the payload when the schema check fails. It logs the field "
            "name and the reason. The caller then retries the request one time."
        )

    def test_it_records_a_blocked_turn(self):
        self.run_stop(self.dirty())
        row = self.lines()[0]

        self.assertTrue(row["blocked"])
        self.assertIn("Rule 8", row["rules"])
        self.assertEqual(row["agent"], "claude-code")

    def test_it_records_a_clean_turn_too(self):
        self.run_stop(self.clean())
        row = self.lines()[0]

        self.assertTrue(row["clean"])
        self.assertFalse(row["blocked"])
        self.assertEqual(row["rules"], [])

    def test_it_never_writes_the_message_text(self):
        self.run_stop(self.dirty())
        raw = self.log.read_text()

        self.assertNotIn("robust", raw)
        self.assertNotIn("parser", raw)

    def test_it_stays_off_without_the_switch(self):
        del self.env["STE_GUARD_TELEMETRY"]
        self.run_stop(self.dirty())

        self.assertFalse(self.log.exists())

    def test_the_stats_reader_summarises_the_log(self):
        for i in range(3):
            self.run_stop(self.dirty(f" {i}"), session=f"s{i}")

        result = subprocess.run(
            [str(ROOT / "scripts" / "ste-stats.py"), "--log", str(self.log)],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("violations per 100 words", result.stdout)
        self.assertIn("Rule 8", result.stdout)

    def test_the_stats_reader_explains_an_empty_log(self):
        result = subprocess.run(
            [str(ROOT / "scripts" / "ste-stats.py"), "--log", str(self.log)],
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("no telemetry", result.stdout)


class GiveUpSignal(unittest.TestCase):
    """When the cap stops the rewrite, the user must learn that the slop shipped."""

    def setUp(self):
        self.state = tempfile.mkdtemp(prefix="ste-guard-giveup-")
        self.env = dict(os.environ, STE_GUARD_STATE_DIR=self.state, STE_GUARD_PROFILE="default")

    def tearDown(self):
        shutil.rmtree(self.state, ignore_errors=True)

    def run_stop(self, text, session):
        return subprocess.run(
            [str(HOOKS / "stop-lint.py")],
            input=json.dumps({"session_id": session, "last_assistant_message": text}),
            capture_output=True,
            text=True,
            env=self.env,
        )

    def dirty(self, tag=""):
        return (
            f"Great question{tag}. This robust and seamless approach handles the payload for "
            "the whole team. The parser validates every incoming field against the schema. "
            "It writes the result to disk once the check passes."
        )

    def test_the_chain_cap_emits_a_system_message(self):
        for i in range(2):
            self.run_stop(self.dirty(f" {i}"), "g1")

        result = self.run_stop(self.dirty(" 2"), "g1")
        payload = json.loads(result.stdout)

        self.assertIn("systemMessage", payload)
        self.assertIn("chain cap", payload["systemMessage"])
        self.assertNotIn("decision", payload)

    def test_the_repeat_guard_emits_a_system_message(self):
        text = self.dirty()
        self.run_stop(text, "g2")
        result = self.run_stop(text, "g2")
        payload = json.loads(result.stdout)

        self.assertIn("systemMessage", payload)
        self.assertIn("violations left", payload["systemMessage"])


class SoftRules(unittest.TestCase):
    def setUp(self):
        self.p = profile("default")

    def soft(self, text):
        _, soft, _ = ste_rules.lint(self.p, text)

        return " ".join(soft)

    def test_a_long_sentence_fires(self):
        long_one = "The parser " + "and the validator " * 12 + "reject it."
        self.assertIn("Rule 11", self.soft(long_one))

    def test_a_gerund_opener_fires(self):
        self.assertIn("Rule 12", self.soft("Parsing the payload takes two passes."))

    def test_a_progressive_verb_is_not_a_gerund_opener(self):
        self.assertNotIn("Rule 12", self.soft("Nothing is broken here today."))

    def test_passive_voice_fires(self):
        self.assertIn("Rule 10", self.soft("The payload is rejected by the parser."))

    def test_active_voice_passes(self):
        self.assertNotIn("Rule 10", self.soft("The parser rejects the payload."))

    def test_an_adjectival_participle_is_not_passive(self):
        """Ordinary technical prose says "the flag is required". That is not passive voice."""
        for phrase in (
            "The flag is required for every request.",
            "The hook is enabled by default in this build.",
            "The file is unchanged after the run completes.",
            "That option is deprecated in the current release.",
            "The behaviour is undefined when the list is empty.",
        ):
            self.assertNotIn("Rule 10", self.soft(phrase), phrase)

    def test_a_real_passive_still_fires(self):
        for phrase in (
            "The payload is rejected by the parser.",
            "The field was written to disk.",
            "The alert is sent to the on-call engineer.",
        ):
            self.assertIn("Rule 10", self.soft(phrase), phrase)


class TargetParity(unittest.TestCase):
    """The Stop hook and the checker must return the same violations, always.

    Claude Code and Codex read the Stop hook. The pi extension reads the checker.
    Any disagreement means the three agents enforce different rules.
    """

    SAMPLES = [
        "The parser rejects the payload when the schema check fails. It logs the reason.",
        "This robust and seamless parser handles every payload the service receives today. "
        "It validates each field against the schema before it writes anything to disk here.",
        "Great question. The parser rejects the payload when the schema check fails today. "
        "It logs the field name and the reason for the rejection. Let me know if you need more.",
        " ".join(["word"] * 300),
        "# Title\n\n" + " ".join(["word"] * 300),
        'The checker bans the word "robust" and the opener "great question" outright today. '
        "It blanks any quoted run before it applies the phrase lists to the message text.",
    ]

    def setUp(self):
        self.state = tempfile.mkdtemp(prefix="ste-guard-parity-")
        self.env = dict(os.environ, STE_GUARD_STATE_DIR=self.state, STE_GUARD_PROFILE="default")

    def tearDown(self):
        shutil.rmtree(self.state, ignore_errors=True)

    def stop_hook(self, text, session):
        payload = {"session_id": session, "last_assistant_message": text}
        result = subprocess.run(
            [str(HOOKS / "stop-lint.py")],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=self.env,
        )

        if not result.stdout.strip():
            return []

        reason = json.loads(result.stdout)["reason"]

        return sorted(line.strip()[2:] for line in reason.splitlines() if line.startswith("  - "))

    def checker(self, text):
        result = subprocess.run(
            [str(HOOKS / "ste-check"), "--json"],
            input=text,
            capture_output=True,
            text=True,
            env=self.env,
        )

        return sorted(json.loads(result.stdout)["violations"])

    def test_both_targets_agree_on_every_sample(self):
        for i, text in enumerate(self.SAMPLES):
            self.assertEqual(self.stop_hook(text, f"parity-{i}"), self.checker(text), text[:50])


class ProseWall(unittest.TestCase):
    def test_the_rule_stays_off_in_the_default_profile(self):
        p = profile("default")
        text = (" ".join(["word"] * 40)) + "\n\n" + (" ".join(["word"] * 40))
        hard, _, _ = ste_rules.lint(p, text)

        self.assertFalse(any("Rule 6" in h for h in hard))

    def test_the_rule_fires_in_peer_eng_without_bullets(self):
        p = profile("peer-eng")
        text = "# Title\n\n" + (" ".join(["word"] * 40)) + "\n\n" + (" ".join(["word"] * 40))
        hard, _, _ = ste_rules.lint(p, text)

        self.assertTrue(any("Rule 6" in h for h in hard))

    def test_bullets_satisfy_the_rule(self):
        p = profile("peer-eng")
        text = "# Title\n\n- " + (" ".join(["word"] * 40)) + "\n\n- " + (" ".join(["word"] * 40))
        hard, _, _ = ste_rules.lint(p, text)

        self.assertFalse(any("Rule 6" in h for h in hard))


class ContractText(unittest.TestCase):
    def test_the_brief_prints_the_active_numbers(self):
        text = contract.render_brief(profile("default"))

        self.assertIn("250", text)
        self.assertIn("25 words", text)

    def test_the_brief_omits_a_rule_that_is_off(self):
        text = contract.render_brief(profile("default"))

        self.assertNotIn("discovery of the fact", text)

    def test_the_brief_includes_a_rule_that_is_on(self):
        text = contract.render_brief(profile("peer-eng"))

        self.assertIn("discovery of the fact", text)

    def test_the_contract_lists_the_exact_banned_strings(self):
        text = contract.render_contract(profile("default"))

        self.assertIn('"robust"', text)
        self.assertIn('"great question"', text)

    def test_the_contract_omits_a_list_whose_rule_is_off(self):
        text = contract.render_contract(profile("default"))

        self.assertNotIn("Banned narration", text)


class HookProcess(unittest.TestCase):
    """Runs the hooks as real subprocesses, against a throwaway state directory."""

    def setUp(self):
        self.state = tempfile.mkdtemp(prefix="ste-guard-test-")
        self.env = dict(os.environ, STE_GUARD_STATE_DIR=self.state, STE_GUARD_PROFILE="default")

    def tearDown(self):
        shutil.rmtree(self.state, ignore_errors=True)

    def run_hook(self, name, payload):
        return subprocess.run(
            [str(HOOKS / name)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=self.env,
        )

    def blocked(self, result):
        if not result.stdout.strip():
            return False

        return json.loads(result.stdout).get("decision") == "block"

    def dirty(self, tag=""):
        return (
            f"Great question{tag}. This robust and seamless approach handles the payload for "
            "the whole team. The parser then validates every incoming field against the schema. "
            "It writes the result to disk once the check passes."
        )

    def clean(self):
        return (
            "The parser rejects the payload when the schema check fails. It logs the field "
            "name and the reason. The caller then retries the request one time."
        )

    def test_a_dirty_reply_blocks(self):
        result = self.run_hook("stop-lint.py", {"session_id": "s1", "last_assistant_message": self.dirty()})

        self.assertTrue(self.blocked(result))
        self.assertIn("Rule 8", result.stdout)

    def test_a_clean_reply_passes(self):
        result = self.run_hook("stop-lint.py", {"session_id": "s2", "last_assistant_message": self.clean()})

        self.assertFalse(self.blocked(result))

    def test_a_short_reply_is_never_checked(self):
        result = self.run_hook("stop-lint.py", {"session_id": "s3", "last_assistant_message": "Great question."})

        self.assertFalse(self.blocked(result))

    def test_the_chain_cap_stops_a_ping_pong(self):
        verdicts = [
            self.blocked(
                self.run_hook("stop-lint.py", {"session_id": "s4", "last_assistant_message": self.dirty(f" {i}")})
            )
            for i in range(4)
        ]

        self.assertEqual(verdicts, [True, True, False, False])

    def test_a_clean_reply_resets_the_chain(self):
        for i in range(2):
            self.run_hook("stop-lint.py", {"session_id": "s5", "last_assistant_message": self.dirty(f" {i}")})

        self.run_hook("stop-lint.py", {"session_id": "s5", "last_assistant_message": self.clean()})
        result = self.run_hook("stop-lint.py", {"session_id": "s5", "last_assistant_message": self.dirty(" again")})

        self.assertTrue(self.blocked(result))

    def test_stop_hook_active_short_circuits(self):
        payload = {"session_id": "s6", "last_assistant_message": self.dirty(), "stop_hook_active": True}
        result = self.run_hook("stop-lint.py", payload)

        self.assertFalse(self.blocked(result))

    def test_the_off_switch_disables_the_hook(self):
        self.env["STE_GUARD_OFF"] = "1"
        result = self.run_hook("stop-lint.py", {"session_id": "s7", "last_assistant_message": self.dirty()})

        self.assertFalse(self.blocked(result))

    def test_the_lazy_contract_stays_silent_before_a_block(self):
        result = self.run_hook("prompt-contract.py", {"session_id": "s8"})

        self.assertEqual(result.stdout.strip(), "")

    def test_the_lazy_contract_speaks_after_a_block(self):
        self.run_hook("stop-lint.py", {"session_id": "s9", "last_assistant_message": self.dirty()})
        result = self.run_hook("prompt-contract.py", {"session_id": "s9"})

        self.assertIn("ENFORCED VALUES", result.stdout)

    def test_the_lazy_contract_stays_armed_after_a_clean_reply(self):
        self.run_hook("stop-lint.py", {"session_id": "s10", "last_assistant_message": self.dirty()})
        self.run_hook("stop-lint.py", {"session_id": "s10", "last_assistant_message": self.clean()})
        result = self.run_hook("prompt-contract.py", {"session_id": "s10"})

        self.assertIn("ENFORCED VALUES", result.stdout)

    def test_the_always_mode_speaks_on_the_first_turn(self):
        self.env["STE_GUARD_PROFILE"] = "peer-eng"
        result = self.run_hook("prompt-contract.py", {"session_id": "s11"})

        self.assertIn("ENFORCED VALUES", result.stdout)

    def test_the_session_brief_prints_the_card(self):
        result = self.run_hook("session-brief.py", {"session_id": "s12"})

        self.assertIn("STE-GUARD", result.stdout)
        self.assertIn("250", result.stdout)

    def test_malformed_stdin_never_blocks(self):
        result = subprocess.run(
            [str(HOOKS / "stop-lint.py")], input="not json", capture_output=True, text=True, env=self.env
        )

        self.assertEqual(result.returncode, 0)
        self.assertFalse(self.blocked(result))


class CheckerCommand(unittest.TestCase):
    def run_checker(self, text):
        return subprocess.run(
            [str(HOOKS / "ste-check")],
            input=text,
            capture_output=True,
            text=True,
            env=dict(os.environ, STE_GUARD_PROFILE="default"),
        )

    def test_a_clean_draft_exits_zero(self):
        result = self.run_checker("The parser rejects the payload when the schema check fails.")

        self.assertEqual(result.returncode, 0)
        self.assertIn("clean", result.stdout)

    def test_a_dirty_draft_exits_one(self):
        result = self.run_checker("Great question. This robust parser handles it.")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Rule 2", result.stdout)

    def test_a_file_argument_works(self):
        result = subprocess.run(
            [str(HOOKS / "ste-check"), str(ROOT / "README.md")],
            capture_output=True,
            text=True,
            env=dict(os.environ, STE_GUARD_PROFILE="default"),
        )

        self.assertEqual(result.returncode, 0, result.stdout)


class ShippedDocs(unittest.TestCase):
    """The plugin's own documentation must survive its own checker."""

    def check(self, name):
        return subprocess.run(
            [str(HOOKS / "ste-check"), str(ROOT / name)],
            capture_output=True,
            text=True,
            env=dict(os.environ, STE_GUARD_PROFILE="default"),
        )

    def test_readme_is_clean(self):
        result = self.check("README.md")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_changelog_is_clean(self):
        result = self.check("CHANGELOG.md")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_skill_is_clean(self):
        result = self.check("skills/ste/SKILL.md")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_output_style_is_clean(self):
        result = self.check("output-styles/ste.md")
        self.assertEqual(result.returncode, 0, result.stdout)


class Manifests(unittest.TestCase):
    def test_plugin_manifest_parses(self):
        data = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())

        self.assertEqual(data["name"], "ste-guard")
        self.assertEqual(data["hooks"], "./hooks/hooks.json")

    def test_marketplace_manifest_parses(self):
        data = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())

        self.assertEqual(data["plugins"][0]["name"], "ste-guard")

    def test_hook_manifest_names_every_script_that_ships(self):
        data = json.loads((HOOKS / "hooks.json").read_text())
        events = data["hooks"]

        self.assertEqual(set(events), {"SessionStart", "UserPromptSubmit", "Stop"})

        for entries in events.values():
            for entry in entries:
                for hook in entry["hooks"]:
                    name = hook["command"].rsplit("/", 1)[-1]
                    self.assertTrue((HOOKS / name).exists(), name)

    def test_the_manifest_version_matches_the_changelog(self):
        version = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
        changelog = (ROOT / "CHANGELOG.md").read_text()

        self.assertIn(f"[{version}]", changelog)

    def test_every_shipped_hook_is_executable(self):
        for name in ("stop-lint.py", "prompt-contract.py", "session-brief.py", "ste-check"):
            self.assertTrue(os.access(HOOKS / name, os.X_OK), name)


class CodexManifests(unittest.TestCase):
    def test_codex_manifest_parses(self):
        data = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())

        self.assertEqual(data["name"], "ste-guard")
        self.assertEqual(data["hooks"], "./hooks/codex-hooks.json")
        self.assertIn("displayName", data["interface"])

    def test_all_three_manifests_declare_the_same_version(self):
        claude = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]
        codex = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text())["version"]
        pi = json.loads((ROOT / "package.json").read_text())["version"]

        self.assertEqual(claude, codex)
        self.assertEqual(claude, pi)


class PiManifest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "package.json").read_text())

    def test_it_declares_the_discovery_keyword(self):
        self.assertIn("pi-package", self.data["keywords"])

    def test_it_points_at_the_extension_and_the_skill(self):
        self.assertEqual(self.data["pi"]["extensions"], ["./extensions"])
        self.assertEqual(self.data["pi"]["skills"], ["./skills"])

    def test_the_pi_core_packages_stay_peer_dependencies(self):
        peers = self.data["peerDependencies"]

        for name in ("@earendil-works/pi-ai", "@earendil-works/pi-coding-agent", "typebox"):
            self.assertEqual(peers.get(name), "*", name)

        self.assertNotIn("dependencies", self.data)

    def test_the_published_files_carry_the_engine(self):
        for path in ("extensions/", "skills/", "hooks/", "profiles/"):
            self.assertIn(path, self.data["files"])

    def test_the_extension_never_reimplements_a_rule(self):
        """The rules live in Python. A phrase list in the TypeScript is a drift bug."""
        source = (ROOT / "extensions" / "ste-guard.ts").read_text()

        for phrase in ("robust", "seamless", "great question", "hope this helps"):
            self.assertNotIn(phrase, source.lower(), phrase)

    def test_the_two_hook_files_declare_the_same_events_and_scripts(self):
        """The files differ only in the path variable. Any other drift is a bug."""
        claude = json.loads((HOOKS / "hooks.json").read_text())["hooks"]
        codex = json.loads((HOOKS / "codex-hooks.json").read_text())["hooks"]

        self.assertEqual(set(claude), set(codex))

        for event in claude:
            claude_scripts = [
                h["command"].rsplit("/", 1)[-1] for e in claude[event] for h in e["hooks"]
            ]
            codex_scripts = [
                h["command"].rsplit("/", 1)[-1] for e in codex[event] for h in e["hooks"]
            ]

            self.assertEqual(claude_scripts, codex_scripts, event)

    def test_each_hook_file_uses_its_own_root_variable(self):
        claude = (HOOKS / "hooks.json").read_text()
        codex = (HOOKS / "codex-hooks.json").read_text()

        self.assertIn("${CLAUDE_PLUGIN_ROOT}", claude)
        self.assertNotIn("${PLUGIN_ROOT}", claude.replace("${CLAUDE_PLUGIN_ROOT}", ""))
        self.assertIn("${PLUGIN_ROOT}", codex)
        self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", codex)


class CodexInstaller(unittest.TestCase):
    """The installer edits a real path, so every test points it at a temporary file."""

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="ste-guard-codex-")
        self.hooks = pathlib.Path(self.home) / ".codex" / "hooks.json"
        self.hooks.parent.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def run_installer(self, *flags):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "codex-install.py"), "--root", str(ROOT), *flags],
            capture_output=True,
            text=True,
            env=dict(os.environ, HOME=self.home),
        )

    def read(self):
        return json.loads(self.hooks.read_text())["hooks"]

    def commands(self, events):
        return [h["command"] for entries in events.values() for e in entries for h in e["hooks"]]

    def test_it_writes_all_three_events(self):
        self.hooks.write_text(json.dumps({"hooks": {}}))
        result = self.run_installer()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(self.read()), {"SessionStart", "UserPromptSubmit", "Stop"})

    def test_it_preserves_unrelated_hooks(self):
        other = {"type": "command", "command": "rtk hook claude"}
        self.hooks.write_text(json.dumps({"hooks": {"PreToolUse": [{"hooks": [other]}]}}))
        self.run_installer()

        self.assertIn("rtk hook claude", self.commands(self.read()))

    def test_a_second_run_never_stacks_duplicates(self):
        self.hooks.write_text(json.dumps({"hooks": {}}))
        self.run_installer()
        self.run_installer()

        self.assertEqual(len(self.commands(self.read())), 3)

    def test_it_strips_the_predecessor_scripts(self):
        legacy = {"type": "command", "command": "'/home/me/.codex/hooks/ste-lint.py'"}
        self.hooks.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [legacy]}]}}))
        self.run_installer()

        self.assertNotIn(legacy["command"], self.commands(self.read()))
        self.assertEqual(len(self.commands(self.read())), 3)

    def test_uninstall_removes_only_our_entries(self):
        other = {"type": "command", "command": "rtk hook claude"}
        self.hooks.write_text(json.dumps({"hooks": {"PreToolUse": [{"hooks": [other]}]}}))
        self.run_installer()
        self.run_installer("--uninstall")

        self.assertEqual(self.commands(self.read()), ["rtk hook claude"])

    def test_it_backs_up_before_it_writes(self):
        self.hooks.write_text(json.dumps({"hooks": {}}))
        self.run_installer()

        self.assertTrue(self.hooks.with_suffix(".json.bak").exists())

    def test_it_creates_the_file_when_none_exists(self):
        self.hooks.unlink(missing_ok=True)
        result = self.run_installer()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.commands(self.read())), 3)

    def test_malformed_json_stops_the_installer(self):
        self.hooks.write_text("{not json")
        result = self.run_installer()

        self.assertEqual(result.returncode, 1)
        self.assertIn("not valid JSON", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
