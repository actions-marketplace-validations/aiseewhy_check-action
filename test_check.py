"""Unit tests for the check's policy (fail-on, fail-under). Run from this folder: python3 -m unittest"""

import io
import json
import os
import tempfile
import unittest
from unittest import mock

import check
from check import PolicyError, policy, verdict

C = {"P1": 0, "P2": 2, "P3": 5}


class PolicyTests(unittest.TestCase):
    def test_defaults_unchanged(self):
        # no inputs at all: fail on P1 only, no score threshold (what the action did before fail-under existed)
        self.assertEqual(policy({}), ("P1", 0))
        self.assertEqual(policy({"ASW_FAIL_ON": "P1", "ASW_MIN_SCORE": "0", "ASW_FAIL_UNDER": ""}), ("P1", 0))

    def test_fail_under_wins_over_min_score(self):
        self.assertEqual(policy({"ASW_MIN_SCORE": "50", "ASW_FAIL_UNDER": "80"}), ("P1", 80))
        self.assertEqual(policy({"ASW_MIN_SCORE": "50", "ASW_FAIL_UNDER": ""}), ("P1", 50))

    def test_case_and_none(self):
        self.assertEqual(policy({"ASW_FAIL_ON": "p2"})[0], "P2")
        self.assertEqual(policy({"ASW_FAIL_ON": "NONE"})[0], "none")

    def test_bad_values_are_errors(self):
        for env in ({"ASW_FAIL_ON": "P4"}, {"ASW_FAIL_ON": "high"}, {"ASW_FAIL_UNDER": "abc"},
                    {"ASW_FAIL_UNDER": "101"}, {"ASW_FAIL_UNDER": "-1"}):
            with self.assertRaises(PolicyError, msg=env):
                policy(env)


class VerdictTests(unittest.TestCase):
    def test_priority_or_worse(self):
        self.assertEqual(verdict(C, 90, "P1", 0), [])
        self.assertEqual(len(verdict(C, 90, "P2", 0)), 1)
        self.assertIn("7 finding", verdict(C, 90, "P3", 0)[0])
        self.assertEqual(verdict({"P1": 3, "P2": 0, "P3": 0}, 90, "none", 0), [])

    def test_score_threshold(self):
        self.assertEqual(verdict(C, 70, "P1", 70), [])
        self.assertEqual(verdict(C, 69, "P1", 70), ["score 69 is below 70"])
        self.assertEqual(len(verdict({"P1": 1, "P2": 0, "P3": 0}, 10, "P1", 70)), 2)


class MainTests(unittest.TestCase):
    def run_main(self, env, d):
        with tempfile.TemporaryDirectory() as tmp:
            out, summ = os.path.join(tmp, "out"), os.path.join(tmp, "sum")
            full = {"ASW_URL": "https://example.com/", "GITHUB_OUTPUT": out, "GITHUB_STEP_SUMMARY": summ, **env}
            resp = mock.MagicMock()
            resp.__enter__.return_value = io.BytesIO(json.dumps(d).encode())
            with mock.patch.dict(os.environ, full, clear=True), \
                    mock.patch("urllib.request.urlopen", return_value=resp) as op, \
                    mock.patch("sys.stdout", new_callable=io.StringIO):
                code = check.main()
            outputs = dict(line.split("=", 1) for line in open(out).read().splitlines()) if os.path.exists(out) else {}
            summary = open(summ).read() if os.path.exists(summ) else ""
            return code, outputs, summary, op

    REPORT = {"counts": {"P1": 0, "P2": 1, "P3": 0}, "score": {"value": 72}, "final_url": "https://example.com/",
              "markdown": "", "full": True}

    def test_passes_with_defaults(self):
        code, outputs, _, _ = self.run_main({}, self.REPORT)
        self.assertEqual(code, 0)
        self.assertEqual(outputs["failed"], "false")
        self.assertEqual(outputs["score"], "72")

    def test_fails_under_threshold(self):
        code, outputs, summary, _ = self.run_main({"ASW_FAIL_UNDER": "80"}, self.REPORT)
        self.assertEqual(code, 1)
        self.assertEqual(outputs["failed"], "true")
        self.assertIn("score 72 is below 80", summary)

    def test_fails_on_p2(self):
        code, _, summary, _ = self.run_main({"ASW_FAIL_ON": "P2"}, self.REPORT)
        self.assertEqual(code, 1)
        self.assertIn("priority P2", summary)

    def test_bad_input_fails_before_calling_the_api(self):
        code, _, _, op = self.run_main({"ASW_FAIL_ON": "P9"}, self.REPORT)
        self.assertEqual(code, 1)
        op.assert_not_called()


if __name__ == "__main__":
    unittest.main()
