#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 divorce contributors
"""CLI contract tests using a fake validator and temporary fixtures."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


GATE = Path(__file__).resolve().parents[1] / "gate.py"
REAL_ENV = os.environ.copy()
REAL_VALIDATOR = (
    shutil.which(REAL_ENV.get("VNU", "")) or shutil.which("vnu") or
    (REAL_ENV.get("VNU_JAR") and Path(REAL_ENV["VNU_JAR"]).is_file() and shutil.which("java"))
)
VALID_HTML = '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Test</title></head><body><main><h1>Test</h1></main></body></html>'
FAKE_VNU = r'''
import json
from pathlib import Path
import sys

if sys.argv[1:4] != ["--format", "json", "--exit-zero-always"] or len(sys.argv) != 5:
    sys.exit(9)
source = sys.argv[-1]
name = Path(source).name
if name == "malformed.html":
    print("not JSON", file=sys.stderr)
    sys.exit(0)
if name == "null.html":
    print("null", file=sys.stderr)
    sys.exit(0)
if name == "missing-messages.html":
    print("{}", file=sys.stderr)
    sys.exit(0)
messages = []
payload = {"messages": messages}
if name in ("error.html", "root-url.html", "grouped.html", "failure.html"):
    messages.append({"type": "error", "message": "Element is not allowed here.",
                     "lastLine": 7, "lastColumn": 12, "extract": "x" * 250})
if name == "root-url.html":
    payload["url"] = "file:///root-url.html"
elif messages:
    messages[0]["url"] = source
if name == "grouped.html":
    messages.append({"type": "info", "subType": "warning", "message": "Review this element.",
                     "url": source + "#second"})
if name == "warning.html":
    messages.append({"type": "info", "subType": "warning", "message": "Review this element.", "url": source})
if name == "unreachable.html":
    messages.append({"type": "non-document-error", "message": "Cannot read document.", "url": source})
if name == "bad-fields.html":
    messages.append({"type": "error", "message": None, "lastLine": True})
print(json.dumps(payload), file=sys.stderr)
sys.exit(4 if name == "failure.html" else 0)
'''


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.validator = self.root / "vnu"
        self.validator.write_text("#!" + sys.executable + "\n" + FAKE_VNU, encoding="utf-8")
        self.validator.chmod(0o755)
        self.env = {"HOME": str(self.root), "PATH": os.environ["PATH"]}
        self.env["VNU"] = str(self.validator)
        self.env.pop("VNU_JAR", None)

    def html(self, name):
        path = self.root / name
        path.write_text(VALID_HTML, encoding="utf-8")
        return path

    def axe(self, payload):
        path = self.root / "axe.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def run_gate(self, *arguments, env=None):
        process = subprocess.run([sys.executable, str(GATE)] + [str(arg) for arg in arguments],
                                 capture_output=True, text=True, timeout=90,
                                 env=self.env if env is None else env, check=False)
        self.assertEqual(process.stderr, "", process.stderr)
        result = json.loads(process.stdout)
        self.assertIsInstance(result["reasons"], list)
        return process.returncode, result

    def test_valid_html_passes(self):
        code, result = self.run_gate("html", self.html("valid.html"))
        self.assertEqual((code, result["verdict"]), (0, "pass"))
        self.assertEqual(result["html"][0]["errors"], 0)
        self.assertEqual(result["html"][0]["warnings"], 0)
        self.assertEqual(result["html"][0]["messages"], [])
        self.assertEqual(result["reasons"], [])

    def test_html_error_includes_position_and_trimmed_extract(self):
        code, result = self.run_gate("html", self.html("error.html"))
        self.assertEqual((code, result["verdict"]), (1, "fail"))
        self.assertEqual(result["reasons"], ["html_errors"])
        entry = result["html"][0]
        self.assertEqual(entry["errors"], 1)
        self.assertIs(type(entry["errors"]), int)
        message = entry["messages"][0]
        self.assertEqual(message["message"], "Element is not allowed here.")
        self.assertEqual((message["line"], message["column"]), (7, 12))
        self.assertEqual(message["type"], "error")
        self.assertEqual(len(message["extract"]), 200)

    def test_multiple_inputs_and_warning(self):
        code, result = self.run_gate("html", self.html("valid.html"), self.html("warning.html"))
        self.assertEqual(code, 0)
        self.assertEqual(len(result["html"]), 2)
        self.assertEqual([entry["warnings"] for entry in result["html"]], [0, 1])

    def test_message_urls_preserve_one_fact_per_input(self):
        paths = [self.html("grouped.html"), self.html("root-url.html")]
        code, result = self.run_gate("html", *paths)
        self.assertEqual(code, 1)
        self.assertEqual([entry["input"] for entry in result["html"]], [str(path) for path in paths])
        self.assertEqual(result["html"][0]["errors"], 1)
        self.assertEqual(result["html"][0]["warnings"], 1)
        self.assertEqual(len(result["html"][0]["messages"]), 2)

    def test_missing_validator_is_not_measured(self):
        empty = self.root / "empty-path"
        empty.mkdir()
        self.env["VNU"] = str(self.root / "does-not-exist")
        self.env["PATH"] = str(empty)
        code, result = self.run_gate("html", self.html("valid.html"))
        self.assertEqual((code, result["verdict"]), (2, "not_measured"))
        self.assertEqual(result["reasons"], ["validator_missing"])

    def test_path_validator_fallback(self):
        self.env["VNU"] = str(self.root / "does-not-exist")
        self.env["PATH"] = str(self.root)
        code, result = self.run_gate("html", self.html("valid.html"))
        self.assertEqual((code, result["verdict"]), (0, "pass"))

    def test_jar_validator_fallback(self):
        java = self.root / "java"
        java.write_text("#!" + sys.executable + "\nimport json, sys\n"
                        "assert sys.argv[1] == '-jar'\n"
                        "assert sys.argv[3:6] == ['--format', 'json', '--exit-zero-always']\n"
                        "print(json.dumps({'messages': []}), file=sys.stderr)\n", encoding="utf-8")
        java.chmod(0o755)
        self.validator.unlink()
        jar = self.root / "vnu.jar"
        jar.write_bytes(b"fixture")
        self.env["VNU_JAR"] = str(jar)
        self.env["PATH"] = str(self.root)
        code, result = self.run_gate("html", self.html("valid.html"))
        self.assertEqual((code, result["verdict"]), (0, "pass"))

    def test_validator_failure_preserves_observed_errors(self):
        code, result = self.run_gate("html", self.html("failure.html"))
        self.assertEqual((code, result["verdict"]), (2, "not_measured"))
        self.assertEqual(result["html"][0]["errors"], 1)
        self.assertEqual(result["reasons"], ["validator_failed", "html_errors"])

    def test_bad_validator_json_is_not_measured(self):
        for name in ("malformed.html", "null.html", "missing-messages.html", "bad-fields.html"):
            with self.subTest(name=name):
                code, result = self.run_gate("html", self.html(name))
                self.assertEqual((code, result["verdict"]), (2, "not_measured"))
                self.assertIn("validator_failed", result["reasons"])

    def test_unreachable_url_is_not_measured(self):
        code, result = self.run_gate("html", "https://example.invalid/unreachable.html")
        self.assertEqual((code, result["verdict"]), (2, "not_measured"))
        self.assertEqual(result["reasons"], ["input_unreachable"])
        self.assertEqual(result["html"][0]["messages"][0]["type"], "non-document-error")

    def test_serious_axe_violation_fails(self):
        payload = {"violations": [{"id": "label", "impact": "serious",
                                    "nodes": [{}, {}], "tags": ["wcag2a"]}]}
        code, result = self.run_gate("axe", self.axe(payload))
        self.assertEqual((code, result["verdict"]), (1, "fail"))
        self.assertEqual(result["reasons"], ["axe_violations:critical=0,serious=1"])
        self.assertEqual(result["axe"]["rules"], [{"id": "label", "impact": "serious",
                                                    "nodes": 2, "tags": ["wcag2a"]}])
        self.assertEqual(result["axe"]["totals"]["serious"], 1)

    def test_moderate_threshold_and_count_aliases(self):
        for count_key in ("n", "node_count"):
            with self.subTest(count_key=count_key):
                path = self.axe([{"id": "landmark-one-main", "impact": "moderate", count_key: 1}])
                code, result = self.run_gate("axe", path)
                self.assertEqual((code, result["verdict"]), (0, "pass"))
                code, result = self.run_gate("axe", path, "--axe-max-impact", "moderate")
                self.assertEqual((code, result["verdict"]), (1, "fail"))
                self.assertIn("moderate=1", result["reasons"][0])

    def test_critical_and_minor_thresholds(self):
        code, result = self.run_gate("axe", self.axe([{"id": "rule", "impact": "critical", "n": 1}]))
        self.assertEqual((code, result["verdict"]), (1, "fail"))
        path = self.axe([{"id": "rule", "impact": "minor", "n": 1}])
        code, result = self.run_gate("axe", path, "--axe-max-impact", "minor")
        self.assertEqual((code, result["verdict"]), (1, "fail"))

    def test_null_impact_is_not_measured(self):
        code, result = self.run_gate("axe", self.axe([{"id": "rule", "impact": None, "n": 1}]))
        self.assertEqual((code, result["verdict"]), (2, "not_measured"))
        self.assertEqual(result["reasons"], ["axe_impact_unknown"])
        self.assertIsNone(result["axe"]["rules"][0]["impact"])
        self.assertEqual(result["axe"]["totals"]["null"], 1)

    def test_invalid_axe_shapes_are_not_measured(self):
        for payload in (None, {}, {"violations": None}, [None],
                        [{"id": "rule", "impact": "unknown", "n": 1}],
                        [{"id": "rule", "impact": "minor", "n": True}],
                        [{"id": "rule", "impact": "minor", "n": -1}],
                        [{"id": "rule", "impact": "minor"}],
                        [{"id": "rule", "impact": "minor", "n": 1, "tags": None}],
                        [{"id": "rule", "impact": "minor", "nodes": [], "n": 1}]):
            with self.subTest(payload=payload):
                code, result = self.run_gate("axe", self.axe(payload))
                self.assertEqual((code, result["verdict"]), (2, "not_measured"))
                self.assertEqual(result["reasons"], ["axe_json_invalid"])

    def test_unreadable_and_malformed_axe_json(self):
        for path in (self.root / "missing.json", self.root):
            with self.subTest(path=path):
                code, result = self.run_gate("axe", path)
                self.assertEqual((code, result["verdict"]), (2, "not_measured"))
                self.assertEqual(result["reasons"], ["axe_json_missing"])
        path = self.root / "broken.json"
        for content in (b"not JSON", b"\xff", b'{"violations":[],"violations":[]}', b"[NaN]"):
            with self.subTest(content=content):
                path.write_bytes(content)
                code, result = self.run_gate("axe", path)
                self.assertEqual((code, result["verdict"]), (2, "not_measured"))
                self.assertEqual(result["reasons"], ["axe_json_invalid"])

    def test_axe_version_mismatch_is_not_measured(self):
        payload = {"error": "axe_version_mismatch", "expected": "4.10.2", "found": "4.0.0"}
        code, result = self.run_gate("axe", self.axe(payload))
        self.assertEqual((code, result["verdict"]), (2, "not_measured"))
        self.assertEqual(result["reasons"], ["axe_version_mismatch"])
        self.assertIsNone(result["axe"])

    def test_other_snippet_errors_are_not_measured(self):
        for error in ("load_failed", None, False, {}, []):
            with self.subTest(error=error):
                code, result = self.run_gate("axe", self.axe({"error": error, "violations": []}))
                self.assertEqual((code, result["verdict"]), (2, "not_measured"))
                self.assertEqual(result["reasons"], ["axe_snippet_error"])
                self.assertIsNone(result["axe"])

    def test_combined_verdict_and_infrastructure_priority(self):
        html = self.html("valid.html")
        code, result = self.run_gate("check", "--html", html, "--axe", self.axe([]))
        self.assertEqual((code, result["verdict"]), (0, "pass"))
        path = self.axe([{"id": "rule", "impact": "moderate", "n": 1}])
        code, result = self.run_gate("check", "--html", html, "--axe", path,
                                     "--axe-max-impact", "moderate")
        self.assertEqual((code, result["verdict"]), (1, "fail"))
        code, result = self.run_gate("check", "--html", self.html("error.html"),
                                     "--axe", self.root / "missing.json")
        self.assertEqual((code, result["verdict"]), (2, "not_measured"))
        self.assertEqual(result["reasons"], ["axe_json_missing", "html_errors"])

    def test_snippet_uses_script_load_and_all_tags(self):
        process = subprocess.run([sys.executable, str(GATE), "axe-snippet"],
                                 capture_output=True, text=True, timeout=10, env={"HOME": str(self.root), "PATH": os.environ["PATH"]}, check=False)
        self.assertEqual(process.returncode, 0)
        snippet = process.stdout
        for fragment in ("(async () =>", "window.axe.version", '"4.10.2"', "axe_version_mismatch",
                         "createElement('script')", "script.onload",
                         "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js",
                         "JSON.stringify", "n: v.nodes.length", "tags: v.tags", "'wcag2a'", "'wcag2aa'",
                         "'wcag21a'", "'wcag21aa'", "'wcag22aa'", "'best-practice'"):
            self.assertIn(fragment, snippet)
        self.assertNotIn("import(", snippet)

    def run_snippet(self, loaded_version):
        process = subprocess.run([sys.executable, str(GATE), "axe-snippet"],
                                 capture_output=True, text=True, timeout=10, env={"HOME": str(self.root), "PATH": os.environ["PATH"]}, check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        snippet = self.root / "snippet.js"
        snippet.write_text(process.stdout, encoding="utf-8")
        harness = self.root / "harness.cjs"
        harness.write_text('''
const fs = require('fs');
globalThis.window = globalThis;
const scripts = [];
let previousRuns = 0;
let loadedRuns = 0;
window.axe = {version: '4.0.0', run: async () => {
  previousRuns++;
  return {violations: []};
}};
globalThis.document = {
  createElement: tag => ({tag, remove() {}}),
  head: {appendChild(script) {
    scripts.push({tag: script.tag, src: script.src});
    window.axe = {version: process.argv[3], run: async () => {
      loadedRuns++;
      return {violations: [{id: 'label', impact: 'serious', tags: ['wcag2a'], nodes: [{}, {}]}]};
    }};
    script.onload();
  }}
};
(async () => {
  const result = await eval(fs.readFileSync(process.argv[2], 'utf8'));
  console.log(JSON.stringify({result: JSON.parse(result), scripts, previousRuns, loadedRuns}));
})().catch(error => { console.error(error); process.exitCode = 1; });
''', encoding="utf-8")
        process = subprocess.run([shutil.which("node"), str(harness), str(snippet), loaded_version],
                                 capture_output=True, text=True, timeout=10, env={"HOME": str(self.root), "PATH": os.environ["PATH"]}, check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result["scripts"], [{"tag": "script", "src":
                         "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"}])
        self.assertEqual(result["previousRuns"], 0)
        return result

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_snippet_replaces_previous_axe_version(self):
        result = self.run_snippet("4.10.2")
        self.assertEqual(result["loadedRuns"], 1)
        self.assertEqual(result["result"], [{"id": "label", "impact": "serious",
                                             "tags": ["wcag2a"], "n": 2}])

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_snippet_rejects_mismatched_loaded_version(self):
        result = self.run_snippet("4.0.0")
        self.assertEqual(result["loadedRuns"], 0)
        self.assertEqual(result["result"], {"error": "axe_version_mismatch",
                                             "expected": "4.10.2", "found": "4.0.0"})

    @unittest.skipUnless(REAL_VALIDATOR, "Nu HTML Checker is not installed")
    def test_real_validator_integration(self):
        code, result = self.run_gate("html", self.html("real.html"), env={"HOME": str(self.root), "PATH": os.environ["PATH"],
                                                                  **{key: REAL_ENV[key] for key in ("VNU", "VNU_JAR")
                                                                     if key in REAL_ENV}})
        self.assertEqual((code, result["verdict"]), (0, "pass"))
        self.assertEqual(result["html"][0]["errors"], 0)


if __name__ == "__main__":
    unittest.main()
