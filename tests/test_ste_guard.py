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


if __name__ == "__main__":
    unittest.main(verbosity=2)
