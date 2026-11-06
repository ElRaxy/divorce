#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 divorce contributors
"""Input attribution contracts with a fake validator; no browser required."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
GATE = REPOSITORY / "skills" / "divorce" / "scripts" / "gate.py"
FAKE_VNU = r'''
import json
from pathlib import Path
import sys

assert sys.argv[1:4] == ["--format", "json", "--exit-zero-always"]
assert len(sys.argv) == 5
source = Path(sys.argv[-1])
assert source.is_absolute()
assert source.is_file()
url = "file:" + str(source)
messages = []
if source.name != "clean.html" and source.parent.name != "div-button":
    messages.append({"url": url, "type": "error", "message": "Invalid heading order."})
if source.name == "mixed.html":
    messages.append({"url": url + "#other", "type": "info", "subType": "warning",
                     "message": "Review this heading."})
print(json.dumps({"url": url, "messages": messages}), file=sys.stderr)
'''


class GateInputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        validator = self.root / "vnu"
        validator.write_text("#!" + sys.executable + "\n" + FAKE_VNU, encoding="utf-8")
        validator.chmod(0o755)
        self.env = dict(os.environ, VNU=str(validator))

    def run_html(self, *entries, cwd=None):
        if cwd is None:
            cwd = self.root
            for entry in entries:
                (self.root / entry).write_text("<!doctype html>", encoding="utf-8")
        process = subprocess.run(
            [sys.executable, str(GATE), "html", *entries], cwd=cwd,
            env=self.env, capture_output=True, text=True, encoding="utf-8",
            check=False, timeout=10,
        )
        self.assertEqual(process.stderr, "", process.stderr)
        self.assertNotIn("file:", process.stdout)
        result = json.loads(process.stdout)
        self.assertEqual([fact["input"] for fact in result["html"]], list(entries))
        return process.returncode, result

    def test_error_preserves_relative_input(self):
        code, result = self.run_html("./error.html")
        self.assertEqual((code, result["verdict"]), (1, "fail"))
        self.assertEqual(result["reasons"], ["html_errors"])
        self.assertEqual(result["html"][0]["errors"], 1)

    def test_clean_response_preserves_relative_input(self):
        code, result = self.run_html("./clean.html")
        self.assertEqual((code, result["verdict"]), (0, "pass"))
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["html"], [{"input": "./clean.html", "errors": 0,
                                          "warnings": 0, "messages": []}])

    def test_message_urls_do_not_split_an_input(self):
        code, result = self.run_html("mixed.html", "clean.html")
        self.assertEqual((code, result["verdict"]), (1, "fail"))
        fact = result["html"][0]
        self.assertEqual((fact["errors"], fact["warnings"]), (1, 1))
        self.assertEqual(len(fact["messages"]), 2)

    def test_div_button_readme_examples_pass_with_fake_validator(self):
        for version in ("before", "after"):
            with self.subTest(version=version):
                entry = f"examples/div-button/{version}.html"
                code, result = self.run_html(entry, cwd=REPOSITORY)
                self.assertEqual((code, result["verdict"]), (0, "pass"))
                self.assertEqual(result["reasons"], [])
                self.assertEqual(result["html"], [{"input": entry, "errors": 0,
                                                  "warnings": 0, "messages": []}])

    def test_invalid_url_shapes_still_raise_value_error(self):
        spec = importlib.util.spec_from_file_location("divorce_gate", GATE)
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        for url in (None, "", [], 1):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    gate.html_messages({"url": url, "messages": []}, "input.html")
                with self.assertRaises(ValueError):
                    gate.html_messages({"messages": [{"url": url, "type": "error",
                                                      "message": "Invalid."}]}, "input.html")


if __name__ == "__main__":
    unittest.main()
