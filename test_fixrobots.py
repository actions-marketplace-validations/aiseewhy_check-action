"""Unit tests for fix mode. Run from this folder: python3 -m unittest"""

import os
import tempfile
import unittest

from fixrobots import fix, main, parse, root_blocked


def read(path):
    with open(path) as f:
        return f.read()


def agents_rules(text):
    lines = text.splitlines(keepends=True)
    return {t: g.rules for g in parse(lines) for _, t in g.agents}


class FixTests(unittest.TestCase):
    def test_own_group_disallow_replaced(self):
        src = "User-agent: OAI-SearchBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n"
        new, changes = fix(src)
        self.assertEqual(new, "User-agent: OAI-SearchBot\nAllow: /\n\nUser-agent: *\nAllow: /\n")
        self.assertEqual([b for b, _ in changes], ["OAI-SearchBot"])

    def test_case_insensitive_token(self):
        new, changes = fix("user-agent: perplexitybot\ndisallow: /\n")
        self.assertEqual(new, "user-agent: perplexitybot\nAllow: /\n")
        self.assertEqual([b for b, _ in changes], ["PerplexityBot"])

    def test_only_star_blocking_adds_group_and_keeps_star(self):
        src = "User-agent: *\nDisallow: /\n"
        new, changes = fix(src)
        self.assertTrue(new.startswith(src))  # the * group is untouched
        self.assertEqual(len(changes), 6)
        groups = agents_rules(new)
        self.assertTrue(root_blocked(groups["*"]))
        for bot in ("oai-searchbot", "chatgpt-user", "claude-searchbot", "claude-user", "perplexitybot",
                    "perplexity-user"):
            self.assertFalse(root_blocked(groups[bot]), bot)
        self.assertNotIn("gptbot", groups)

    def test_mixed_group_moves_only_search_bot(self):
        src = ("User-agent: GPTBot\nUser-agent: ChatGPT-User\nUser-agent: CCBot\nDisallow: /\n"
               "\nUser-agent: *\nAllow: /\n")
        new, changes = fix(src)
        self.assertEqual([b for b, _ in changes], ["ChatGPT-User"])
        groups = agents_rules(new)
        self.assertTrue(root_blocked(groups["gptbot"]))
        self.assertTrue(root_blocked(groups["ccbot"]))
        self.assertFalse(root_blocked(groups["chatgpt-user"]))
        self.assertIn("User-agent: GPTBot\n", new)
        self.assertIn("Disallow: /\n", new)
        self.assertIn("# AISeeWhy: moved to its own group at the end: User-agent: ChatGPT-User\n", new)
        self.assertTrue(new.rstrip().endswith("User-agent: ChatGPT-User\nAllow: /"))

    def test_group_of_only_search_bots_replaced_in_place(self):
        src = "User-agent: Claude-SearchBot\nUser-agent: Claude-User\nDisallow: /\nDisallow: /x\n"
        new, changes = fix(src)
        self.assertEqual(new, "User-agent: Claude-SearchBot\nUser-agent: Claude-User\nAllow: /\n")
        self.assertEqual(sorted(b for b, _ in changes), ["Claude-SearchBot", "Claude-User"])

    def test_already_fine_no_change(self):
        for src in ("User-agent: *\nAllow: /\n",
                    "User-agent: *\nDisallow: /admin\n",
                    "User-agent: *\nDisallow:\n",
                    "User-agent: *\nDisallow: /\n\nUser-agent: OAI-SearchBot\nUser-agent: ChatGPT-User\n"
                    "User-agent: Claude-SearchBot\nUser-agent: Claude-User\nUser-agent: PerplexityBot\n"
                    "User-agent: Perplexity-User\nAllow: /\n",
                    ""):
            new, changes = fix(src)
            self.assertEqual(new, src)
            self.assertEqual(changes, [])

    def test_comments_and_other_lines_preserved(self):
        src = ("# top comment\r\n"
               "Sitemap: https://example.com/sitemap.xml\r\n"
               "User-agent: PerplexityBot # inline\r\n"
               "# rule comment\r\n"
               "Disallow: / # nope\r\n"
               "Crawl-delay: 5\r\n"
               "\r\n"
               "User-agent: *\r\n"
               "Disallow: /private\r\n")
        new, _ = fix(src)
        self.assertEqual(new, src.replace("Disallow: / # nope\r\n", "Allow: /\r\n"))

    def test_training_bots_untouched(self):
        src = ("User-agent: GPTBot\nDisallow: /\n\nUser-agent: ClaudeBot\nDisallow: /\n\n"
               "User-agent: Google-Extended\nUser-agent: Applebot-Extended\nUser-agent: CCBot\n"
               "User-agent: Bytespider\nUser-agent: Meta-ExternalAgent\nDisallow: /\n\n"
               "User-agent: *\nDisallow: /\n")
        new, _ = fix(src)
        self.assertTrue(new.startswith(src))
        groups = agents_rules(new)
        for bot in ("gptbot", "claudebot", "google-extended", "applebot-extended", "ccbot", "bytespider",
                    "meta-externalagent", "*"):
            self.assertTrue(root_blocked(groups[bot]), bot)

    def test_no_trailing_newline(self):
        new, _ = fix("User-agent: *\nDisallow: /")
        self.assertTrue(new.startswith("User-agent: *\nDisallow: /\n\n# AISeeWhy:"))

    def test_longest_match_and_wildcard(self):
        self.assertTrue(root_blocked([(0, "disallow", "/*")]))
        self.assertFalse(root_blocked([(0, "disallow", "/"), (1, "allow", "/")]))
        self.assertFalse(root_blocked([(0, "disallow", "/"), (1, "allow", "/$")]))
        self.assertFalse(root_blocked([(0, "disallow", "/admin")]))


class MainTests(unittest.TestCase):
    def run_main(self, robots, **env):
        with tempfile.TemporaryDirectory() as d:
            if robots is not None:
                with open(os.path.join(d, "robots.txt"), "w") as f:
                    f.write(robots)
            out = os.path.join(d, "out")
            base = {"GITHUB_WORKSPACE": d, "GITHUB_OUTPUT": out, "RUNNER_TEMP": d, "GITHUB_STEP_SUMMARY": os.devnull,
                    "ASW_ROBOTS_PATH": "robots.txt", "ASW_FIX_SEARCH_BOTS": "true"}
            base.update(env)
            old = {k: os.environ.get(k) for k in base}
            os.environ.update(base)
            try:
                self.assertEqual(main(), 0)
            finally:
                for k, v in old.items():
                    os.environ.pop(k) if v is None else os.environ.__setitem__(k, v)
            outputs = dict(l.split("=", 1) for l in read(out).splitlines())
            md = read(outputs["fix-summary"]) if outputs["fix-summary"] else ""
            new = read(os.path.join(d, "robots.txt")) if robots is not None else None
            return outputs, md, new

    def test_fix_writes_file_and_outputs(self):
        outputs, md, new = self.run_main("User-agent: *\nDisallow: /\n")
        self.assertEqual(outputs["fixed"], "true")
        self.assertIn("proposal", md)
        self.assertIn("Training crawlers", md)
        self.assertIn("User-agent: OAI-SearchBot", new)

    def test_off_by_default(self):
        outputs, md, new = self.run_main("User-agent: *\nDisallow: /\n", ASW_FIX_SEARCH_BOTS="false")
        self.assertEqual(outputs["fixed"], "false")
        self.assertEqual(new, "User-agent: *\nDisallow: /\n")

    def test_missing_file(self):
        outputs, _, _ = self.run_main(None)
        self.assertEqual(outputs["fixed"], "false")


if __name__ == "__main__":
    unittest.main()
