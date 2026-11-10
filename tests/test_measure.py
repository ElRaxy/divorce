#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 divorce contributors
"""Retained page measurements with an offline validator."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY / "evals" / "measure.py"
FAKE_VNU = r'''
import json
import os
from pathlib import Path
import sys

assert sys.argv[1:4] == ["--format", "json", "--exit-zero-always"]
assert len(sys.argv) == 5
source = Path(sys.argv[-1])
assert source.is_absolute()
assert source.is_file()
url = "file:" + str(source)
messages = []
if "INVALID_MARKER" in source.read_text(encoding="utf-8"):
    messages.append({"url": url, "type": "error", "message": "Invalid café heading.",
                     "lastLine": 3, "lastColumn": 8, "extract": "<h9>café</h9>"})
if "UNREACHABLE_MARKER" in source.read_text(encoding="utf-8"):
    original = Path(os.environ.get("VNU_OUTPUT", str(source.parent))) / source.name
    for path in (original, source.resolve()):
        for url in (str(path), "file:" + str(path), "file://" + str(path), path.as_uri()):
            messages.append({"url": url, "type": "non-document-error",
                             "message": "Cannot read " + url, "extract": "Source: " + url})
print(json.dumps({"url": url, "messages": messages}), file=sys.stderr)
'''
MESSAGE = {"type": "error", "message": "Invalid café heading.", "line": 3,
           "column": 8, "extract": "<h9>café</h9>"}


class MeasureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=REPOSITORY)
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)
        self.source = self.tmp / "result.json"
        self.out = self.tmp / "output"
        self.axe = self.tmp / "axe"
        self.axe.mkdir()
        validator = self.tmp / "vnu"
        validator.write_text("#!" + sys.executable + "\n" + FAKE_VNU, encoding="utf-8")
        validator.chmod(0o755)
        self.env = dict(os.environ, VNU=str(validator), PYTHONDONTWRITEBYTECODE="1")

    def run_entry(self, name, content="<!doctype html>", relative=False, error=None):
        root = self.tmp / name
        trace = root / "trace" / "x.jsonl"
        trace.parent.mkdir(parents=True)
        trace.write_text("", encoding="utf-8")
        if content is not None:
            html = root / "sealed" / "home" / "cwd" / "index.html"
            html.parent.mkdir(parents=True)
            html.write_bytes(content.encode("utf-8"))
        return {"tracePath": str(trace.relative_to(self.tmp) if relative else trace),
                "error": error}

    def write_result(self, cases):
        self.source.write_text(json.dumps({"claudeVersion": "1.2.3",
                                          "startedAt": "2026-01-01T00:00:00Z",
                                          "cases": cases}), encoding="utf-8")

    def invoke(self, axe=False):
        command = [sys.executable, str(SCRIPT), str(self.source), "--out", str(self.out)]
        if axe:
            command.extend(["--axe-dir", str(self.axe)])
        return subprocess.run(command, cwd=self.tmp, env=self.env, capture_output=True,
                              text=True, encoding="utf-8", timeout=30, check=False)

    def report(self):
        return json.loads((self.out / "pages.json").read_text(encoding="utf-8"))

    def single_case(self):
        self.write_result([{"name": "sample", "arms": {
            "with": [self.run_entry("one")], "without": []}}])

    def load_measure(self):
        spec = importlib.util.spec_from_file_location("measure_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, "dont_write_bytecode", True):
            spec.loader.exec_module(module)
        return module

    def invoke_mocked(self, outcomes, axe=False):
        module = self.load_measure()
        argv = [str(SCRIPT), str(self.source), "--out", str(self.out)]
        if axe:
            argv.extend(["--axe-dir", str(self.axe)])
        with patch.object(sys, "argv", argv), patch.object(
                module.subprocess, "run", side_effect=outcomes) as runner:
            code = module.main()
        return code, runner

    def test_mixed_runs_preserve_evidence_and_repeat_bytes(self):
        bad = "<!doctype html>\nINVALID_MARKER\n<h9>café</h9>"
        self.write_result([
            {"name": "zeta", "arms": {
                "with": [self.run_entry("bad", bad),
                         self.run_entry("failed", bad, error="")],
                "without": [self.run_entry("missing", None)]}},
            {"name": "alpha", "arms": {
                "with": [self.run_entry("clean", relative=True)],
                "without": [self.run_entry("other", bad, relative=True)]}},
        ])
        (self.axe / "alpha-without-1.axe.json").write_text(json.dumps([
            {"id": "heading-order", "impact": "moderate", "n": 2,
             "tags": ["best-practice"]}]), encoding="utf-8")
        process = self.invoke(axe=True)
        self.assertEqual(process.returncode, 2, process.stderr)
        self.assertEqual(process.stderr, "")
        result = self.report()
        self.assertEqual(result["claude_version"], "1.2.3")
        self.assertEqual(result["started_at"], "2026-01-01T00:00:00Z")
        pages = result["pages"]
        self.assertEqual([(p["case"], p["arm"], p["run"]) for p in pages], [
            ("alpha", "with", 1), ("alpha", "without", 1),
            ("zeta", "with", 1), ("zeta", "with", 2), ("zeta", "without", 1)])
        indexed = {page["page"]: page for page in pages}
        self.assertEqual({key: value["status"] for key, value in indexed.items()}, {
            "alpha-with-1": "measured", "alpha-without-1": "measured",
            "zeta-with-1": "measured", "zeta-with-2": "run_error",
            "zeta-without-1": "html_missing"})
        self.assertEqual(result["totals"], {
            "with": {"pages": 3, "pages_measured": 2, "pages_with_nu_errors": 1,
                     "nu_errors": 1, "pages_with_axe_violations": 0,
                     "pages_axe_measured": 0},
            "without": {"pages": 2, "pages_measured": 1, "pages_with_nu_errors": 1,
                        "nu_errors": 1, "pages_with_axe_violations": 1,
                        "pages_axe_measured": 1}})
        for page in pages:
            name = page["page"]
            if page["status"] != "measured":
                self.assertIsNone(page["nu"])
                self.assertIsNone(page["html_sha256"])
                self.assertFalse((self.out / f"{name}.html").exists())
                continue
            data = (self.out / f"{name}.html").read_bytes()
            self.assertEqual(page["html_sha256"], hashlib.sha256(data).hexdigest())
            errors = int(name != "alpha-with-1")
            self.assertEqual(page["nu"], {"exit": errors, "errors": errors,
                                          "warnings": 0,
                                          "messages": [MESSAGE] if errors else []})
            saved = json.loads((self.out / f"{name}.gate.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, {"exit": errors, "result": {
                "html": [{"input": f"{name}.html", "errors": errors, "warnings": 0,
                          "messages": [MESSAGE] if errors else []}],
                "verdict": "fail" if errors else "pass",
                "reasons": ["html_errors"] if errors else []}})
        self.assertEqual((self.out / "zeta-with-1.html").read_bytes(), bad.encode("utf-8"))
        rules = [{"id": "heading-order", "impact": "moderate", "nodes": 2,
                  "tags": ["best-practice"]}]
        self.assertEqual(indexed["alpha-without-1"]["axe"], {"exit": 0, "rules": rules})
        full = indexed["alpha-without-1"]["axe_gate"]
        self.assertEqual(full["exit"], 0)
        self.assertEqual(full["result"]["axe"]["rules"], rules)
        for page in pages:
            if page["page"] != "alpha-without-1":
                self.assertIsNone(page["axe"])
        before = {path.name: path.read_bytes() for path in self.out.iterdir()}
        for name, data in before.items():
            if name.endswith(".json"):
                text = data.decode("utf-8")
                self.assertNotIn(str(self.tmp), text)
                self.assertNotIn(str(Path.home()), text)
                self.assertNotIn("tracePath", text)
                self.assertEqual(text, json.dumps(json.loads(text), indent=1,
                                                 ensure_ascii=False) + "\n")
        self.assertIn("café", before["pages.json"].decode("utf-8"))
        self.assertEqual(self.invoke(axe=True).returncode, 2)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.out.iterdir()})

    def test_all_nu_measurements_exit_zero_even_with_errors(self):
        self.write_result([{"name": "sample", "arms": {
            "with": [self.run_entry("bad", "INVALID_MARKER")],
            "without": [self.run_entry("clean")]}}])
        process = self.invoke()
        self.assertEqual((process.returncode, process.stderr), (0, ""))
        self.assertTrue(all(page["status"] == "measured" for page in self.report()["pages"]))

    def test_invalid_input_reports_one_line(self):
        for content in (None, "{", "{}", "[]", '{"cases": null}'):
            with self.subTest(content=content):
                if content is None:
                    self.source.unlink(missing_ok=True)
                else:
                    self.source.write_text(content, encoding="utf-8")
                process = self.invoke()
                self.assertEqual(process.returncode, 2)
                self.assertEqual(len(process.stderr.splitlines()), 1)
                self.assertNotIn("Traceback", process.stderr)

    def test_missing_trace_and_unreadable_page(self):
        run = self.run_entry("directory")
        html = Path(run["tracePath"]).parents[1] / "sealed/home/cwd/index.html"
        html.unlink()
        html.mkdir()
        self.write_result([{"name": "sample", "arms": {
            "with": [{}, run], "without": []}}])
        self.assertEqual(self.invoke().returncode, 2)
        self.assertEqual([p["status"] for p in self.report()["pages"]],
                         ["html_missing", "html_missing"])

    def test_gate_transport_failures_are_not_measurements(self):
        self.single_case()
        outcomes = [subprocess.TimeoutExpired(["gate"], 120), OSError("Unavailable"),
                    subprocess.CompletedProcess([], 0, stdout="not JSON", stderr="")]
        for outcome in outcomes:
            with self.subTest(outcome=type(outcome).__name__):
                code, runner = self.invoke_mocked([outcome])
                self.assertEqual(code, 2)
                page = self.report()["pages"][0]
                self.assertEqual(page["status"], "gate_not_measured")
                self.assertIsNone(page["nu"])
                self.assertIsNotNone(page["html_sha256"])
                self.assertEqual(self.report()["totals"]["with"]["pages_measured"], 0)
                command = runner.call_args.args[0]
                self.assertEqual(command, [sys.executable,
                    str(REPOSITORY / "skills/divorce/scripts/gate.py"),
                    "html", "sample-with-1.html"])
                self.assertEqual(runner.call_args.kwargs, {
                    "cwd": self.out, "capture_output": True, "text": True,
                    "encoding": "utf-8", "timeout": 120, "check": False})

    def test_gate_exit_two_preserves_available_nu_without_counting_it(self):
        self.single_case()
        group = {"input": "sample-with-1.html", "errors": 1, "warnings": 2,
                 "messages": [MESSAGE]}
        for groups in ([], [group]):
            with self.subTest(groups=groups):
                result = {"html": groups, "verdict": "not_measured",
                          "reasons": ["validator_failed"]}
                code, _ = self.invoke_mocked([
                    subprocess.CompletedProcess([], 2, stdout=json.dumps(result), stderr="")])
                self.assertEqual(code, 2)
                page = self.report()["pages"][0]
                self.assertEqual(page["status"], "gate_not_measured")
                self.assertEqual(page["nu"], {"exit": 2, "errors": 1, "warnings": 2,
                                              "messages": [MESSAGE]} if groups else None)
                totals = self.report()["totals"]["with"]
                self.assertEqual((totals["pages_measured"], totals["pages_with_nu_errors"],
                                  totals["nu_errors"]), (0, 0, 0))
                saved = json.loads((self.out / "sample-with-1.gate.json").read_text())
                self.assertEqual(saved, {"exit": 2, "result": result})

    def test_axe_invalid_is_unmeasured_but_empty_list_is_measured(self):
        self.single_case()
        source = self.axe / "sample-with-1.axe.json"
        for content, expected, count in (("{", None, 0),
                                         ("[]", {"exit": 0, "rules": []}, 1)):
            with self.subTest(content=content):
                source.write_text(content, encoding="utf-8")
                process = self.invoke(axe=True)
                self.assertEqual(process.returncode, 0, process.stderr)
                result = self.report()
                self.assertEqual(result["pages"][0]["axe"], expected)
                self.assertEqual(result["totals"]["with"]["pages_axe_measured"], count)
                self.assertEqual(result["totals"]["with"]["pages_with_axe_violations"], 0)
                if expected is None:
                    self.assertEqual(result["pages"][0]["axe_gate"], {"exit": 2, "result": {
                        "axe": None, "verdict": "not_measured", "reasons": ["axe_json_invalid"]}})

    def test_validator_paths_are_not_stored(self):
        self.single_case()
        self.out.mkdir()
        original = self.tmp / "output link"
        original.symlink_to(self.out, target_is_directory=True)
        self.out = original
        self.env["VNU_OUTPUT"] = str(self.out)
        page = self.tmp / "one" / "sealed" / "home" / "cwd" / "index.html"
        page.write_text("UNREACHABLE_MARKER", encoding="utf-8")
        process = self.invoke()
        self.assertEqual(process.returncode, 2, process.stderr)
        self.assertNotEqual(self.out, self.out.resolve())
        self.assertEqual(self.report()["pages"][0]["nu"]["messages"], [
            {"type": "non-document-error", "message": "Cannot read sample-with-1.html",
             "line": None, "column": None, "extract": "Source: sample-with-1.html"}] * 8)
        before = {path.name: path.read_bytes() for path in self.out.glob("*.json")}
        self.assertEqual(set(before), {"pages.json", "sample-with-1.gate.json"})
        for name in before:
            text = (self.out / name).read_text(encoding="utf-8")
            self.assertNotIn(str(self.tmp), text)
            self.assertNotIn(str(self.tmp.resolve()), text)
            self.assertNotIn(str(self.out), text)
            self.assertNotIn(str(self.out.resolve()), text)
            self.assertNotIn(str(Path.home()), text)
            self.assertNotIn("file:", text)
            self.assertIn("Cannot read sample-with-1.html", text)
        self.assertEqual(self.invoke().returncode, 2)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.out.glob("*.json")})


if __name__ == "__main__":
    unittest.main()
