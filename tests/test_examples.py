#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 divorce contributors
"""Example inventory and real-validator contracts; no browser or axe execution."""

from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
import unittest
from urllib.parse import urlsplit


REPOSITORY = Path(__file__).resolve().parents[1]
EXAMPLES = REPOSITORY / "examples"
GATE = REPOSITORY / "skills" / "divorce" / "scripts" / "gate.py"


class JavaScriptSize(HTMLParser):
    """Count inline script and event-handler text rather than script tags alone."""

    def __init__(self):
        super().__init__()
        self.size = 0
        self.in_script = False
        self.external_scripts = []

    def handle_starttag(self, tag, attrs):
        self.in_script = self.in_script or tag == "script"
        for name, value in attrs:
            if tag == "script" and name == "src":
                self.external_scripts.append(value)
            if name.startswith("on") and value:
                self.size += len(value)
            if value and value.lstrip().lower().startswith("javascript:"):
                self.size += len(value)

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if self.in_script:
            self.size += len(data)


class ExampleTests(unittest.TestCase):
    def setUp(self):
        self.cases = json.loads((EXAMPLES / "manifest.json").read_text(encoding="utf-8"))["cases"]
        self.assertGreaterEqual(len(self.cases), 9, "The example inventory must not be empty or incomplete.")

    def test_manifest_and_directories_match_in_both_directions(self):
        identifiers = [case["id"] for case in self.cases]
        self.assertEqual(len(identifiers), len(set(identifiers)), "Duplicate case ID")
        directories = {path.name for path in EXAMPLES.iterdir()
                       if path.is_dir() and path.name != "__pycache__"}
        self.assertEqual(set(identifiers), directories)
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertRegex(case["id"], r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
                self.assertTrue(case["title"])
                spec = urlsplit(case["spec"])
                self.assertEqual(spec.scheme, "https")
                self.assertIn(spec.netloc, ("html.spec.whatwg.org", "www.w3.org"))
                self.assertTrue(spec.fragment, "A specification URL needs a section anchor.")
                self.assertIn(case["before_html"], ("pass", "fail"))
                self.assertEqual(case["after_html"], "pass")
                self.assertIsInstance(case["axe_rules"], list)
                for rule in case["axe_rules"]:
                    self.assertRegex(rule, r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
                for version in ("before", "after"):
                    self.assertTrue((EXAMPLES / case["id"] / f"{version}.html").is_file())

    def test_readme_matches_generator(self):
        process = subprocess.run(
            [sys.executable, str(EXAMPLES / "build_readme.py")],
            cwd=REPOSITORY, capture_output=True, text=True, encoding="utf-8",
            check=False, timeout=10,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stdout, (EXAMPLES / "README.md").read_text(encoding="utf-8"))

    def test_documents_are_complete_and_after_does_not_add_javascript(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                sizes = []
                for version in ("before", "after"):
                    source = (EXAMPLES / case["id"] / f"{version}.html").read_text(encoding="utf-8")
                    self.assertRegex(source, r"(?i)^<!doctype html>")
                    self.assertIn('<html lang="en">', source)
                    self.assertIn('<meta charset="utf-8">', source)
                    self.assertRegex(source, r"<title>[^<]+</title>")
                    self.assertIn("</body>", source)
                    self.assertTrue(source.rstrip().endswith("</html>"))
                    parser = JavaScriptSize()
                    parser.feed(source)
                    parser.close()
                    self.assertEqual(parser.external_scripts, [])
                    sizes.append(parser.size)
                self.assertLessEqual(sizes[1], sizes[0])

    def measure_html(self, case, version):
        path = EXAMPLES / case["id"] / f"{version}.html"
        process = subprocess.run(
            [sys.executable, str(GATE), "html", str(path)],
            cwd=REPOSITORY, capture_output=True, text=True, encoding="utf-8",
            check=False, timeout=90,
        )
        if process.returncode == 2:
            self.skipTest("vnu not found: set VNU, VNU_JAR or put vnu on PATH")
        evidence = f"{path.relative_to(REPOSITORY)}: {process.stdout}\n{process.stderr}"
        expected = case[f"{version}_html"]
        self.assertEqual(process.returncode, {"pass": 0, "fail": 1}[expected], evidence)
        result = json.loads(process.stdout)
        self.assertEqual(result["verdict"], expected, evidence)
        self.assertTrue(result["html"], "The gate must include measured HTML evidence.")
        errors = sum(entry["errors"] for entry in result["html"])
        if expected == "pass":
            self.assertEqual(errors, 0, evidence)
            self.assertEqual(result["reasons"], [], evidence)
        else:
            self.assertGreater(errors, 0, evidence)
            self.assertIn("html_errors", result["reasons"], evidence)

    def test_before_html_matches_real_validator(self):
        for case in self.cases:
            self.measure_html(case, "before")

    def test_after_html_passes_real_validator(self):
        for case in self.cases:
            self.measure_html(case, "after")


if __name__ == "__main__":
    unittest.main()
