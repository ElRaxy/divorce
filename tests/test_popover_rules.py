#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 divorce contributors
"""The two Nu errors the 5-run benchmark found with divorce, as a regression fixture."""

import json
from pathlib import Path
import subprocess
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
GATE = REPOSITORY / "skills" / "divorce" / "scripts" / "gate.py"
FIXTURE = REPOSITORY / "tests" / "fixtures" / "popover-menu"
SKILL = REPOSITORY / "skills" / "divorce" / "SKILL.md"
EXPANDED = "The “aria-expanded” attribute must not be used on any element which has a “popovertarget” attribute."
LABEL = "The “aria-label” attribute must not be specified on any “div” element unless"


class PopoverRuleTests(unittest.TestCase):
    def test_skill_states_both_rules(self):
        skill = SKILL.read_text(encoding="utf-8")
        self.assertIn("A button with `popovertarget` must not carry `aria-expanded`", skill)
        self.assertIn("Do not put `aria-label` on a `<div>` or `<span>` without a role", skill)

    def gate(self, name):
        process = subprocess.run(
            [sys.executable, str(GATE), "html", f"tests/fixtures/popover-menu/{name}.html"],
            cwd=REPOSITORY, capture_output=True, text=True, encoding="utf-8",
            check=False, timeout=90,
        )
        if process.returncode == 2:
            self.skipTest("vnu not found: set VNU, VNU_JAR or put vnu on PATH")
        return process.returncode, json.loads(process.stdout)

    def test_before_reproduces_both_benchmark_errors(self):
        code, result = self.gate("before")
        errors = [m["message"] for m in result["html"][0]["messages"] if m["type"] == "error"]
        self.assertEqual(code, 1, result)
        self.assertEqual(len(errors), 2, errors)
        self.assertEqual(errors[0], EXPANDED)
        self.assertTrue(errors[1].startswith(LABEL), errors)

    def test_after_passes(self):
        code, result = self.gate("after")
        self.assertEqual((code, result["reasons"]), (0, []), result)


if __name__ == "__main__":
    unittest.main()
