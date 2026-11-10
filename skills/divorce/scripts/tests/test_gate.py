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


    def keyboard_record(self, **changes):
        record = {
            "tag": "div", "role": None, "id": "action", "text": "Action",
            "native": False, "control": False, "click": ["attribute"],
            "visible": True, "tab_index": -1, "disabled": False,
            "inert": False, "aria_hidden": False, "roving": False,
            "focusable_descendant": False, "navigates": False,
        }
        record.update(changes)
        return record

    def keyboard_capture(self, *records, tracked=False):
        return {"tool": "divorce-keyboard", "version": 1,
                "listeners_tracked": tracked, "elements": list(records)}

    def keyboard_file(self, payload):
        path = self.root / "keyboard.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def keyboard_script(self, command):
        process = subprocess.run([sys.executable, str(GATE), command],
                                 capture_output=True, text=True, timeout=10,
                                 env=self.env, check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stderr, "")
        return process.stdout

    def test_keyboard_empty_capture_passes_with_limits(self):
        code, result = self.run_gate("keyboard", self.keyboard_file(self.keyboard_capture()))
        self.assertEqual((code, result["verdict"], result["reasons"]), (0, "pass", []))
        self.assertEqual(result["keyboard"], {
            "listeners_tracked": False, "controls_visible": 0, "in_tab_order": 0,
            "out_of_tab_order": [], "click_unreachable": [], "role_unreachable": [],
            "navigating_buttons": [],
            "not_measured": ["tab_sequence", "enter_space_activation", "escape",
                             "focus_return", "focus_visible"],
        })

    def test_keyboard_navigating_button_warns_without_failing(self):
        record = self.keyboard_record(tag="button", native=True, control=True,
                                      tab_index=0, navigates=True)
        code, result = self.run_gate("keyboard", self.keyboard_file(self.keyboard_capture(record)))
        self.assertEqual((code, result["verdict"], result["reasons"]), (0, "pass", []))
        self.assertEqual(result["warnings"], ["keyboard_button_navigates:1"])
        self.assertEqual(result["keyboard"]["navigating_buttons"], [
            {key: record[key] for key in ("tag", "role", "id", "text")}])

    def test_keyboard_navigation_warning_filters_and_button_types(self):
        for changes in ({"tag": "a"}, {"tag": "div"}, {"visible": False},
                        {"navigates": False}):
            with self.subTest(exempt=changes):
                record = self.keyboard_record(**{"tag": "button", "native": True,
                    "control": True, "tab_index": 0, "navigates": True, **changes})
                code, result = self.run_gate("keyboard", self.keyboard_file(self.keyboard_capture(record)))
                self.assertEqual((code, result["verdict"], result["reasons"]), (0, "pass", []))
                self.assertEqual(result["keyboard"]["navigating_buttons"], [])
                self.assertNotIn("warnings", result)
        for changes in ({"disabled": True}, {"aria_hidden": True}, {"inert": True}):
            with self.subTest(still_warns=changes):
                record = self.keyboard_record(**{"tag": "button", "native": True,
                    "control": True, "tab_index": 0, "navigates": True, **changes})
                code, result = self.run_gate("keyboard", self.keyboard_file(self.keyboard_capture(record)))
                self.assertEqual((code, result["warnings"]), (0, ["keyboard_button_navigates:1"]))
        records = [self.keyboard_record(tag=tag, role=role, navigates=True, tab_index=0,
                                       id=str(index)) for index, (tag, role) in enumerate(
                                           (("button", None), ("input", None), ("div", "button")))]
        code, result = self.run_gate("keyboard", self.keyboard_file(self.keyboard_capture(*records)))
        self.assertEqual((code, result["verdict"], result["reasons"]), (0, "pass", []))
        self.assertEqual(result["warnings"], ["keyboard_button_navigates:3"])
        self.assertEqual(result["keyboard"]["navigating_buttons"], [
            {key: record[key] for key in ("tag", "role", "id", "text")} for record in records])

    def test_keyboard_navigation_warning_preserves_failures(self):
        record = self.keyboard_record(role="button", control=True)
        path = self.keyboard_file(self.keyboard_capture(record))
        code, baseline = self.run_gate("keyboard", path)
        record["navigates"] = True
        code_with_warning, result = self.run_gate("keyboard", self.keyboard_file(self.keyboard_capture(record)))
        self.assertEqual(code_with_warning, code)
        self.assertEqual((result["verdict"], result["reasons"]),
                         (baseline["verdict"], baseline["reasons"]))
        self.assertEqual(result["warnings"], ["keyboard_button_navigates:1"])

    def test_keyboard_unreachable_records_fail_with_summaries(self):
        record = self.keyboard_record(role="button", control=True)
        code, result = self.run_gate("keyboard", self.keyboard_file(self.keyboard_capture(record)))
        self.assertEqual((code, result["verdict"]), (1, "fail"))
        self.assertEqual(result["reasons"], ["keyboard_click_unreachable:1", "keyboard_role_unreachable:1"])
        summary = {key: record[key] for key in ("tag", "role", "id", "text")}
        for key in ("out_of_tab_order", "click_unreachable", "role_unreachable"):
            self.assertEqual(result["keyboard"][key], [summary])

    def test_keyboard_exemptions_have_failing_controls(self):
        for changes in ({"disabled": True}, {"aria_hidden": True}, {"roving": True},
                        {"focusable_descendant": True}, {"tag": "label"}, {"visible": False}):
            with self.subTest(changes=changes):
                exempt = self.keyboard_record(**changes)
                code, result = self.run_gate("keyboard", self.keyboard_file(self.keyboard_capture(exempt)))
                self.assertEqual((code, result["verdict"], result["reasons"]), (0, "pass", []))
                failing = self.keyboard_record(id="failing")
                code, result = self.run_gate("keyboard", self.keyboard_file(
                    self.keyboard_capture(exempt, failing)))
                self.assertEqual((code, result["verdict"]), (1, "fail"))
                self.assertEqual(result["reasons"], ["keyboard_click_unreachable:1"])
                self.assertEqual([item["id"] for item in result["keyboard"]["click_unreachable"]], ["failing"])

    def test_keyboard_role_exemptions_and_all_interactive_roles(self):
        roles = ("button", "link", "checkbox", "radio", "switch", "tab", "menuitem",
                 "menuitemcheckbox", "menuitemradio", "option", "combobox", "slider",
                 "spinbutton", "textbox", "treeitem")
        records = [self.keyboard_record(role=role, control=True, click=[], id=role) for role in roles]
        code, result = self.run_gate("keyboard", self.keyboard_file(self.keyboard_capture(*records)))
        self.assertEqual((code, result["verdict"]), (1, "fail"))
        self.assertEqual(result["reasons"], ["keyboard_role_unreachable:15"])
        for changes in ({"disabled": True}, {"aria_hidden": True}, {"roving": True},
                        {"visible": False}, {"native": True}, {"tab_index": 0}):
            with self.subTest(changes=changes):
                exempt = self.keyboard_record(role="button", control=True, click=[], **changes)
                code, result = self.run_gate("keyboard", self.keyboard_file(self.keyboard_capture(exempt)))
                self.assertEqual((code, result["verdict"]), (0, "pass"))
        for changes in ({"focusable_descendant": True}, {"tag": "label"}):
            with self.subTest(role_not_exempt=changes):
                record = self.keyboard_record(role="button", control=True, click=[], **changes)
                code, result = self.run_gate("keyboard", self.keyboard_file(self.keyboard_capture(record)))
                self.assertEqual(result["reasons"], ["keyboard_role_unreachable:1"])

    def test_keyboard_counts_and_out_of_tab_order_do_not_fail(self):
        records = [
            self.keyboard_record(tag="button", native=True, control=True, click=[], id="negative"),
            self.keyboard_record(tag="button", native=True, control=True, tab_index=0, id="focusable"),
            self.keyboard_record(control=True, tab_index=2, click=[], aria_hidden=True, id="aria"),
            self.keyboard_record(control=True, tab_index=0, click=[], inert=True, id="inert"),
            self.keyboard_record(control=True, tab_index=0, click=[], disabled=True, id="disabled"),
            self.keyboard_record(control=True, tab_index=0, click=[], visible=False, id="hidden"),
        ]
        code, result = self.run_gate("keyboard", self.keyboard_file(self.keyboard_capture(*records, tracked=True)))
        self.assertEqual((code, result["verdict"]), (0, "pass"))
        facts = result["keyboard"]
        self.assertIs(facts["listeners_tracked"], True)
        self.assertEqual((facts["controls_visible"], facts["in_tab_order"]), (5, 2))
        self.assertEqual([record["id"] for record in facts["out_of_tab_order"]], ["negative"])
        inert = self.keyboard_record(tab_index=0, inert=True)
        code, result = self.run_gate("keyboard", self.keyboard_file(self.keyboard_capture(inert)))
        self.assertEqual((code, result["reasons"]), (0, []))

    def test_keyboard_requires_every_record_key_and_rejects_extra_keys(self):
        record = self.keyboard_record()
        for key in record:
            with self.subTest(missing=key):
                incomplete = dict(record)
                del incomplete[key]
                code, result = self.run_gate("keyboard", self.keyboard_file(self.keyboard_capture(incomplete)))
                self.assertEqual((code, result["verdict"]), (2, "not_measured"))
                self.assertEqual(result["reasons"], ["keyboard_json_invalid"])
                self.assertIsNone(result["keyboard"])
        record["unexpected"] = False
        code, result = self.run_gate("keyboard", self.keyboard_file(self.keyboard_capture(record)))
        self.assertEqual((code, result["reasons"]), (2, ["keyboard_json_invalid"]))

    def test_keyboard_rejects_mistyped_record_fields(self):
        invalid = [(key, 0) for key in ("native", "control", "visible", "disabled", "inert",
                                       "aria_hidden", "roving", "focusable_descendant", "navigates")]
        invalid += [("tag", None), ("tag", "DIV"), ("role", False), ("id", 1), ("text", None),
                    ("tab_index", True), ("tab_index", 0.0), ("tab_index", "0"),
                    ("click", None), ("click", "attribute"), ("click", ["unknown"]),
                    ("click", ["listener", "listener"]), ("click", [1]), ("click", [{}])]
        for key, value in invalid:
            with self.subTest(key=key, value=value):
                record = self.keyboard_record(**{key: value})
                code, result = self.run_gate("keyboard", self.keyboard_file(self.keyboard_capture(record)))
                self.assertEqual((code, result["reasons"]), (2, ["keyboard_json_invalid"]))

    def test_keyboard_rejects_invalid_envelopes(self):
        payloads = [None, [], {}, self.keyboard_capture(None)]
        capture = self.keyboard_capture()
        for key in capture:
            incomplete = dict(capture)
            del incomplete[key]
            payloads.append(incomplete)
        for changes in ({"tool": "other"}, {"version": 2}, {"version": True}, {"version": 1.0},
                        {"listeners_tracked": 0}, {"elements": {}}, {"unexpected": False}):
            payloads.append({**capture, **changes})
        for payload in payloads:
            with self.subTest(payload=payload):
                code, result = self.run_gate("keyboard", self.keyboard_file(payload))
                self.assertEqual((code, result["verdict"]), (2, "not_measured"))
                self.assertEqual(result["reasons"], ["keyboard_json_invalid"])

    def test_keyboard_missing_invalid_and_snippet_error(self):
        for path in (self.root / "missing.json", self.root):
            with self.subTest(path=path):
                code, result = self.run_gate("keyboard", path)
                self.assertEqual((code, result["reasons"]), (2, ["keyboard_json_missing"]))
        path = self.root / "broken.json"
        for content in (b"not JSON", b"\xff"):
            path.write_bytes(content)
            code, result = self.run_gate("keyboard", path)
            self.assertEqual((code, result["reasons"]), (2, ["keyboard_json_invalid"]))
        for error in ("collection_failed", None, False, {}, []):
            with self.subTest(error=error):
                code, result = self.run_gate("keyboard", self.keyboard_file({"error": error}))
                self.assertEqual((code, result["verdict"]), (2, "not_measured"))
                self.assertEqual(result["reasons"], ["keyboard_snippet_error"])

    def test_capture_readers_accept_one_extra_json_string_layer(self):
        for command, payload in (("axe", []), ("keyboard", self.keyboard_capture(
                self.keyboard_record(tab_index=0, click=["attribute", "property", "listener"], id=None)))):
            with self.subTest(command=command):
                path = self.root / "capture.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                expected = self.run_gate(command, path)
                path.write_text(json.dumps(json.dumps(payload)), encoding="utf-8")
                self.assertEqual(self.run_gate(command, path), expected)
                self.assertEqual(expected[0], 0)
                path.write_text(json.dumps(json.dumps(json.dumps(payload))), encoding="utf-8")
                code, result = self.run_gate(command, path)
                self.assertEqual((code, result["reasons"]), (2, [command + "_json_invalid"]))

    def test_capture_decoding_preserves_duplicate_and_constant_rejection(self):
        for command in ("axe", "keyboard"):
            for inner in ('{"error":null,"error":false}', '{"error":NaN}',
                          '{"error":Infinity}', '{"error":-Infinity}', "not JSON"):
                for encoded in (False, True):
                    with self.subTest(command=command, inner=inner, encoded=encoded):
                        path = self.root / "capture.json"
                        path.write_text(json.dumps(inner) if encoded else inner, encoding="utf-8")
                        code, result = self.run_gate(command, path)
                        self.assertEqual((code, result["reasons"]), (2, [command + "_json_invalid"]))

    def test_check_merges_keyboard_with_measurement_priority(self):
        keyboard = self.keyboard_file(self.keyboard_capture())
        code, result = self.run_gate("check", "--html", self.html("valid.html"),
                                     "--axe", self.axe([]), "--keyboard", keyboard)
        self.assertEqual((code, result["verdict"]), (0, "pass"))
        self.assertIn("keyboard", result)
        keyboard = self.keyboard_file(self.keyboard_capture(self.keyboard_record(role="button", control=True)))
        code, result = self.run_gate("check", "--html", self.html("valid.html"),
                                     "--axe", self.axe([]), "--keyboard", keyboard)
        self.assertEqual((code, result["verdict"]), (1, "fail"))
        self.assertEqual(result["reasons"], ["keyboard_click_unreachable:1", "keyboard_role_unreachable:1"])
        code, result = self.run_gate("check", "--html", self.html("error.html"),
                                     "--axe", self.root / "missing.json", "--keyboard", keyboard)
        self.assertEqual((code, result["verdict"]), (2, "not_measured"))
        self.assertEqual(result["reasons"], ["axe_json_missing", "html_errors",
                                             "keyboard_click_unreachable:1", "keyboard_role_unreachable:1"])
        code, result = self.run_gate("check", "--html", self.html("error.html"),
                                     self.html("error.html"), "--axe", self.axe([
                                         {"id": "label", "impact": "serious", "n": 1}]),
                                     "--keyboard", self.root / "missing.json")
        self.assertEqual((code, result["verdict"]), (2, "not_measured"))
        self.assertEqual(result["reasons"], ["keyboard_json_missing", "html_errors",
                                             "axe_violations:critical=0,serious=1"])

    def test_check_carries_keyboard_navigation_warning(self):
        record = self.keyboard_record(tag="button", native=True, control=True,
                                      tab_index=0, navigates=True)
        keyboard = self.keyboard_file(self.keyboard_capture(record))
        code, result = self.run_gate("check", "--html", self.html("valid.html"),
                                     "--axe", self.axe([]), "--keyboard", keyboard)
        self.assertEqual((code, result["verdict"], result["reasons"]), (0, "pass", []))
        self.assertEqual(result["warnings"], ["keyboard_button_navigates:1"])
        self.assertEqual(result["keyboard"]["navigating_buttons"], [
            {key: record[key] for key in ("tag", "role", "id", "text")}])

    def test_check_without_keyboard_keeps_exact_output(self):
        html = self.html("valid.html")
        process = subprocess.run([sys.executable, str(GATE), "check", "--html", str(html),
                                  "--axe", str(self.axe([]))], capture_output=True, text=True,
                                 timeout=90, env=self.env, check=False)
        self.assertEqual((process.returncode, process.stderr), (0, ""))
        expected = {"html": [{"input": str(html), "errors": 0, "warnings": 0, "messages": []}],
                    "axe": {"rules": [], "totals": {"critical": 0, "serious": 0,
                                                      "moderate": 0, "minor": 0, "null": 0}},
                    "verdict": "pass", "reasons": []}
        self.assertEqual(process.stdout, json.dumps(expected, ensure_ascii=False, indent=2) + "\n")

    def test_keyboard_scripts_print_without_network_or_page_actions(self):
        snippet = self.keyboard_script("keyboard-snippet")
        init = self.keyboard_script("keyboard-init")
        self.assertIn("divorce-keyboard", snippet)
        self.assertIn("divorce-keyboard", init)
        self.assertIn("(async () =>", snippet)
        self.assertIn("JSON.stringify", snippet)
        self.assertIn("addEventListener", init)
        self.assertNotRegex(snippet, r"https?://|fetch\s*\(|XMLHttpRequest|import\s*\(")
        self.assertNotRegex(snippet, r"\.(focus|click|dispatchEvent|appendChild|setAttribute|remove)\s*\(")

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_keyboard_scripts_parse_in_node(self):
        for command in ("keyboard-init", "keyboard-snippet"):
            with self.subTest(command=command):
                script = self.root / (command + ".js")
                script.write_text(self.keyboard_script(command), encoding="utf-8")
                process = subprocess.run([shutil.which("node"), "--check", str(script)],
                                         capture_output=True, text=True, timeout=10, env=self.env, check=False)
                self.assertEqual((process.returncode, process.stderr), (0, ""))

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_keyboard_snippet_detects_navigation_sources_in_node(self):
        snippet = self.keyboard_script("keyboard-snippet")
        pattern = (r"\blocation\s*=(?!=)|\blocation\.(?:href|pathname|search)\s*=(?!=)|"
                   r"\blocation\.(?:assign|replace)\s*\(|\bwindow\.open\s*\(")
        self.assertIn("new RegExp(" + json.dumps(pattern) + ")", snippet)
        cases = [
            ('location.href = "x"', True), ('window.location = u', True),
            ('location.assign(u)', True), ('window.open(u)', True),
            ('location = u', True), ('location.pathname = "/x"', True),
            ('location.search = "?x"', True), ('location.replace(u)', True),
            ('location.hash = "#a"', False), ('location.reload()', False),
            ('a == location.href', False), ('location.href == u', False),
            ('location === u', False), ('history.pushState({}, "", "/x")', False),
            ('history.replaceState({}, "", "/x")', False), ('history.back()', False),
        ]
        script = self.root / "keyboard-snippet.js"
        script.write_text(snippet, encoding="utf-8")
        harness = self.root / "keyboard-navigation.cjs"
        harness.write_text('''
const fs = require('fs');
const cases = %s;
const element = (id, source) => ({
  localName: 'button', textContent: 'Go', tabIndex: 0, onclick: null,
  hasAttribute: name => name === 'onclick' && source !== null,
  getAttribute: name => name === 'onclick' ? source : name === 'id' ? id : null,
  matches: () => true, closest: () => null, querySelectorAll: () => [],
  checkVisibility: () => true
});
const elements = cases.map(([source], index) => element(String(index), source));
const property = element('property', null);
property.onclick = () => { location.assign('/property'); };
const listener = element('listener', null);
const unprintable = element('unprintable', null);
unprintable.onclick = () => {};
unprintable.onclick.toString = () => { throw new Error('unprintable'); };
elements.push(property, listener, unprintable);
globalThis.window = {};
globalThis.document = {querySelectorAll: () => elements};
(async () => {
  const capture = () => eval(fs.readFileSync(process.argv[2], 'utf8'));
  const before = JSON.parse(await capture());
  window.__divorce_keyboard_listeners = new WeakSet();
  const wrongRegistry = JSON.parse(await capture());
  const registry = new WeakMap();
  window.__divorce_keyboard_listeners = registry;
  registry.set(listener, [String(() => {}), String(() => { window.open('/listener'); })]);
  const after = JSON.parse(await capture());
  console.log(JSON.stringify({before, wrongRegistry, after}));
})().catch(error => { console.error(error); process.exitCode = 1; });
''' % json.dumps(cases), encoding="utf-8")
        process = subprocess.run([shutil.which("node"), str(harness), str(script)],
                                 capture_output=True, text=True, timeout=10, env=self.env, check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        for key in ("before", "wrongRegistry", "after"):
            capture = result[key]
            self.assertIs(capture["listeners_tracked"], key == "after")
            self.assertEqual([record["navigates"] for record in capture["elements"]],
                             [expected for source, expected in cases] + [True, key == "after", False])
            for record in capture["elements"]:
                self.assertIs(type(record["navigates"]), bool)
                self.assertNotIn("sources", record)
        self.assertEqual(result["after"]["elements"][-2]["click"], ["listener"])
        self.assertEqual(result["after"]["elements"][-3]["click"], ["property"])

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_keyboard_init_tracks_targets_once_and_preserves_calls(self):
        init = self.root / "keyboard-init.js"
        snippet = self.root / "keyboard-snippet.js"
        init.write_text(self.keyboard_script("keyboard-init"), encoding="utf-8")
        snippet.write_text(self.keyboard_script("keyboard-snippet"), encoding="utf-8")
        harness = self.root / "keyboard-harness.cjs"
        harness.write_text('''
const fs = require('fs');
const calls = [];
globalThis.EventTarget = class {
  addEventListener(...args) { calls.push({target: this, args}); return 7; }
};
globalThis.Element = class extends EventTarget {
  constructor(tag) { super(); this.localName = tag; }
};
globalThis.window = new EventTarget();
globalThis.document = new EventTarget();
document.querySelectorAll = () => [];
(async () => {
  const capture = () => eval(fs.readFileSync(process.argv[3], 'utf8'));
  const before = JSON.parse(await capture());
  const init = fs.readFileSync(process.argv[2], 'utf8');
  eval(init);
  const wrapper = EventTarget.prototype.addEventListener;
  eval(init);
  const idempotent = wrapper === EventTarget.prototype.addEventListener;
  const registry = Object.values(window).find(value => value instanceof WeakMap);
  const callback = () => {};
  const options = {capture: true, passive: true};
  const types = ['click', 'mousedown', 'mouseup', 'pointerdown', 'pointerup'];
  const tracked = types.map(type => {
    const target = new Element('div');
    const returned = target.addEventListener(type, callback, options);
    const call = calls[calls.length - 1];
    return registry.has(target) && returned === 7 && call.target === target &&
      call.args[0] === type && call.args[1] === callback && call.args[2] === options;
  });
  const excluded = [new Element('html'), new Element('body'), document, window];
  for (const target of excluded) target.addEventListener('click', callback);
  const keyboardOnly = new Element('div');
  keyboardOnly.addEventListener('keydown', callback);
  const noListener = new Element('div');
  noListener.addEventListener('click', null);
  excluded.push(keyboardOnly, noListener);
  const after = JSON.parse(await capture());
  const result = {before, after, idempotent, tracked,
    excluded: excluded.map(target => registry.has(target)), calls: calls.length};
  const target = new Element('button');
  const functionListener = () => { window.open('/x'); };
  const objectListener = {handleEvent() { location.assign('/x'); }};
  const sources = [String(functionListener), String(objectListener.handleEvent)];
  target.addEventListener('click', functionListener);
  target.addEventListener('click', objectListener);
  target.addEventListener('click', functionListener);
  const stored = registry.get(target);
  result.sourcesMatch = JSON.stringify(stored) === JSON.stringify([...sources, sources[0]]);
  const longListener = () => {};
  longListener.toString = () => 'x'.repeat(2100);
  target.addEventListener('click', longListener);
  result.appendOnly = registry.get(target) === stored;
  result.truncated = stored[3] === 'x'.repeat(2000);
  const exotic = {get handleEvent() { throw new Error('unavailable'); }};
  const unprintable = () => {};
  unprintable.toString = () => { throw new Error('unprintable'); };
  result.exoticReturns = [exotic, unprintable].map(listener =>
    target.addEventListener('click', listener));
  result.sourcesAfterErrors = stored.length;
  result.sourceCalls = calls.slice(result.calls).map(call =>
    call.target === target && call.args[0] === 'click' && call.args.length === 2);
  console.log(JSON.stringify(result));
})().catch(error => { console.error(error); process.exitCode = 1; });
''', encoding="utf-8")
        process = subprocess.run([shutil.which("node"), str(harness), str(init), str(snippet)],
                                 capture_output=True, text=True, timeout=10, env=self.env, check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result["before"], self.keyboard_capture())
        self.assertEqual(result["after"], self.keyboard_capture(tracked=True))
        self.assertIs(result["idempotent"], True)
        self.assertEqual(result["tracked"], [True] * 5)
        self.assertEqual(result["excluded"], [False] * 6)
        self.assertEqual(result["calls"], 11)
        self.assertIs(result["sourcesMatch"], True)
        self.assertIs(result["appendOnly"], True)
        self.assertIs(result["truncated"], True)
        self.assertEqual(result["exoticReturns"], [7, 7])
        self.assertEqual(result["sourcesAfterErrors"], 4)
        self.assertEqual(result["sourceCalls"], [True] * 6)


if __name__ == "__main__":
    unittest.main()
