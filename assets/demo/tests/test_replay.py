import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_replay", ROOT / "build_replay.py")
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


class ReplayTest(unittest.TestCase):
    def test_published_data_has_no_absolute_paths_or_session_identifiers(self):
        files = sorted((ROOT / "data").glob("*.json"))
        self.assertEqual([p.name for p in files], ["modal-with.json", "modal-without.json"])
        for path in files:
            replay.validate_public(json.loads(path.read_text(encoding="utf-8")))

    def test_recorded_steps_and_final_messages_are_faithful(self):
        with_run = json.loads((ROOT / "data/modal-with.json").read_text())
        without_run = json.loads((ROOT / "data/modal-without.json").read_text())
        self.assertEqual([s["tool"] for s in without_run["steps"]], ["Write", "Bash"])
        self.assertEqual([s["tool"] for s in with_run["steps"]], ["Skill", "Write", "Bash"])
        self.assertIn("divorce", with_run["steps"][0]["summary"])
        self.assertIn("gate.py", with_run["steps"][2]["summary"])
        self.assertIn("node -e", without_run["steps"][1]["summary"])
        self.assertTrue(without_run["final"].startswith("I've written the document manager to `index.html`"))
        self.assertTrue(with_run["final"].startswith("I wrote `index.html` and it passes HTML validation"))
        self.assertEqual(with_run["facts"], {"gate_ran": True, "gate_verdict": "pass",
                         "nu_errors": 0, "gate_exit": 0, "axe_ran": False})
        self.assertEqual(without_run["facts"], {"gate_ran": False, "gate_verdict": None,
                         "nu_errors": None, "gate_exit": None, "axe_ran": False})
        for run in (with_run, without_run):
            write = next(s for s in run["steps"] if s["tool"] == "Write")
            self.assertIn("index.html", write["summary"])
            self.assertIn("<button", write["summary"])
            self.assertIn("<dialog", write["summary"])

    def test_frame_api_dimensions_and_no_timers_or_network(self):
        html = (ROOT / "replay.html").read_text()
        frames = int(re.search(r"window\.FRAMES\s*=\s*(\d+)", html).group(1))
        self.assertGreaterEqual(frames, 60)
        self.assertLessEqual(frames, 90)
        self.assertIn("window.setFrame = function (n)", html)
        self.assertRegex(html, r"body\s*\{[^}]*width:\s*880px;[^}]*height:\s*500px;")
        executable = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
        css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
        self.assertNotRegex(executable, r"setTimeout|setInterval|requestAnimationFrame|fetch\s*\(")
        self.assertNotRegex(css, r"animation\s*:|transition\s*:|@keyframes|@import")
        self.assertNotRegex(css, r'''(?i)url\s*\(\s*["']?\s*(?:https?:|//|data:)''')
        for url in re.findall(r"url\s*\(([^)]*)\)", css, re.I):
            self.assertRegex(url, r'^"\.\./fonts/[\w-]+\.woff2"$')
        self.assertNotRegex(html, r'<(?:script|link)[^>]*(?:src|href)="https?://')
        self.assertIn("Two recorded runs of the modal task, same prompt and model, no browser.", html)
        for text in ("claimed done · checks: none", "checks: not_measured · not claimed"):
            self.assertNotIn(text, html)
        embedded = json.loads(re.search(r'<script id="replay-data" type="application/json">(.*?)</script>', html, re.S).group(1))
        for arm in ("with", "without"):
            self.assertEqual(embedded[arm], json.loads((ROOT / f"data/modal-{arm}.json").read_text()))

    def fact_trace(self, path, outputs, axe=False):
        events = []
        for index, content in enumerate(outputs):
            tool_id = f"gate-{index}"
            events.extend([
                {"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "id": tool_id, "name": "Bash",
                     "input": {"command": "python3 gate.py html index.html"}}]}},
                {"type": "user", "message": {"content": [
                    {"type": "tool_result", "tool_use_id": tool_id, "content": content}]}}
            ])
        if axe:
            events.append({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "axe-check", "name": "Bash",
                 "input": {"command": "axe index.html"}}]}})
        trace = self.trace(path, "The agent claims everything passed, including axe.")
        events = [json.loads(line) for line in trace.read_text().splitlines()] + events
        trace.write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")
        return trace

    def test_fact_footers_and_status_colors(self):
        cases = [
            ('{"verdict":"pass","html":[{"errors":0}]}\nexit: 0', False,
             ("pass", 0, 0), "gate: pass · Nu errors: 0 · exit 0 · axe: not run", True),
            ('{"verdict":"pass","html":[{"errors":0}]}\nexit: 1', False,
             ("pass", 0, 1), "gate: pass · Nu errors: 0 · exit 1 · axe: not run", False),
            ('{"verdict":"fail","html":[{"errors":1}]}\nexit: 0', False,
             ("fail", 1, 0), "gate: fail · Nu errors: 1 · exit 0 · axe: not run", False),
            ('{"verdict":"fail","html":[{"errors":1},{"errors":1}]}\nexit=1', False,
             ("fail", 2, 1), "gate: fail · Nu errors: 2 · exit 1 · axe: not run", False),
            ('{"verdict":"not_measured"}\nexit: 2', False,
             ("not_measured", None, 2), "gate: not_measured · Nu errors: null · exit 2 · axe: not run", False),
            (None, False, (None, None, None), "gate: not run · axe: not run", False),
            ([{"type": "text", "text": 'Prefix {"verdict":"pass","html":[{"errors":0}]}'},
              {"type": "text", "text": "exit: 0"}], True,
             ("pass", 0, 0), "gate: pass · Nu errors: 0 · exit 0", True),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for output, axe, values, text, ok in cases:
                with self.subTest(text=text):
                    trace = self.fact_trace(root / "trace.jsonl", [] if output is None else [output], axe)
                    events = [json.loads(line) for line in trace.read_text().splitlines()]
                    before = json.dumps(events)
                    facts = replay.extract_facts(events)
                    self.assertEqual(json.dumps(events), before)
                    self.assertEqual(facts, dict(zip(
                        ("gate_ran", "gate_verdict", "nu_errors", "gate_exit", "axe_ran"),
                        (output is not None, *values, axe))))
                    self.assertEqual(replay.footer(facts), (text, ok))
                    replay.build(trace, trace, root / "output")
                    run = json.loads((root / "output/data/modal-with.json").read_text())
                    self.assertEqual(run["facts"], facts)
                    self.assertEqual(run["footer"], {"text": text, "ok": ok})
                    html = (root / "output/replay.html").read_text()
                    self.assertIn("const complete = frame >= 52;", html)
                    self.assertIn("status.textContent = complete ? run.footer.text : '';", html)
                    self.assertIn("status.className = 'status ' + (run.footer.ok ? 'status-pass' : 'status-fail');", html)
                    for old in ("claimed done · checks: none", "checks: not_measured · not claimed"):
                        self.assertNotIn(old, html)

    def test_missing_or_malformed_gate_facts_stay_null(self):
        cases = [
            ([], (None, None, None)),
            (['{"verdict":"pass","html":[{"errors":0}]\nexit: 0'], (None, None, 0)),
            (['{"verdict":"pass","html":[{"errors":"0"}]}'], ("pass", None, None)),
            (['{"html":[{"errors":true}]}\nexit: 0\nmore output'], (None, None, None)),
            (['{"verdict":"pass","html":[{"errors":0}]}\nexit: 0',
              'prefix {"verdict":"fail","html":[{"errors":1}],"note":"} brace"}\nexit: 0\nexit=1'],
             ("fail", 1, 1)),
            (['{"verdict":"pass","html":[{"errors":0}]}\nexit: 0', "missing report"],
             (None, None, None)),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            for outputs, expected in cases:
                with self.subTest(outputs=outputs):
                    trace = self.fact_trace(path, outputs)
                    events = [json.loads(line) for line in trace.read_text().splitlines()]
                    if not outputs:
                        events.append({"type": "assistant", "message": {"content": [
                            {"type": "tool_use", "id": "unanswered", "name": "Bash",
                             "input": {"command": "gate.py html index.html"}}]}})
                    events.append({"type": "user", "message": {"content": [
                        {"type": "tool_result", "tool_use_id": "unrelated",
                         "content": '{"verdict":"pass","html":[{"errors":0}]}\nexit: 0'}]}})
                    facts = replay.extract_facts(events)
                    self.assertEqual(tuple(facts[key] for key in ("gate_verdict", "nu_errors", "gate_exit")), expected)
                    self.assertFalse(replay.footer(facts)[1])

            trace = self.fact_trace(path, ['{"verdict":"pass","html":[{"errors":0}]}\nexit: 0'])
            events = [json.loads(line) for line in trace.read_text().splitlines()]
            events.append({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "latest-unanswered", "name": "Bash",
                 "input": {"command": "gate.py html index.html"}}]}})
            facts = replay.extract_facts(events)
            self.assertEqual(facts, {"gate_ran": True, "gate_verdict": None, "nu_errors": None,
                                    "gate_exit": None, "axe_ran": False})
            self.assertEqual(replay.footer(facts),
                             ("gate: null · Nu errors: null · exit null · axe: not run", False))

    def test_facts_and_footer_are_sanitized_and_validated_before_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            verdict = str(root / "report.txt") + " 12345678-1234-1234-1234-123456789abc"
            report = {"verdict": verdict, "html": [{"errors": 0}]}
            trace = self.fact_trace(root / "trace.jsonl", [json.dumps(report) + "\nexit: 0"])
            replay.build(trace, trace, root / "output")
            path = root / "output/data/modal-with.json"
            run = json.loads(path.read_text())
            self.assertEqual(run["facts"]["gate_verdict"], "report.txt [redacted]")
            self.assertEqual(run["footer"]["text"],
                             "gate: report.txt [redacted] · Nu errors: 0 · exit 0 · axe: not run")
            replay.validate_public(run)
            before = path.read_bytes()
            trace = self.fact_trace(root / "trace.jsonl", ['{"verdict":"session_id"}\nexit: 0'])
            with self.assertRaises(ValueError):
                replay.build(trace, trace, root / "output")
            self.assertEqual(path.read_bytes(), before)

    def test_status_palette_meets_aa_contrast(self):
        html = (ROOT / "replay.html").read_text()
        colors = dict(re.findall(r"--(surface|red|green):\s*(#[0-9a-f]{6})", html))

        def channels(color):
            return [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]

        def luminance(rgb):
            linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
            return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

        surface = channels(colors["surface"])
        for status, color in (("pass", "green"), ("fail", "red")):
            self.assertIn(f".status-{status} {{ color: var(--{color}); background: var(--{color}-tint); }}", html)
            tint = re.search(rf"--{color}-tint: rgba\(([^)]+)\)", html).group(1)
            red, green, blue, alpha = map(float, tint.split(","))
            background = [alpha * c / 255 + (1 - alpha) * b
                          for c, b in zip((red, green, blue), surface)]
            contrast = (luminance(channels(colors[color])) + 0.05) / (luminance(background) + 0.05)
            self.assertGreaterEqual(contrast, 4.5, f"{status} contrast: {contrast:.2f}:1")
        muted = channels("#86868b")
        self.assertGreaterEqual((luminance(muted) + 0.05) / (luminance(surface) + 0.05), 4.5)

    def test_default_rebuild_preserves_recorded_data_and_derives_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            result = subprocess.run([sys.executable, str(ROOT / "build_replay.py"),
                                     "--out-dir", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for arm in ("with", "without"):
                self.assertEqual((output / f"data/modal-{arm}.json").read_bytes(),
                                 (ROOT / f"data/modal-{arm}.json").read_bytes())
            page = (output / "replay.html").read_bytes()
            replay.build(out_dir=output)
            self.assertEqual((output / "replay.html").read_bytes(), page)
            path = output / "data/modal-with.json"
            run = json.loads(path.read_text())
            run["facts"]["gate_exit"] = 1
            path.write_text(json.dumps(run))
            with patch.object(replay, "ROOT", output):
                replay.build(out_dir=output)
            rebuilt = json.loads(path.read_text())
            self.assertFalse(rebuilt["footer"]["ok"])
            self.assertEqual(rebuilt["footer"]["text"], replay.footer(run["facts"])[0])
            before = (output / "replay.html").read_bytes()
            result = subprocess.run([sys.executable, str(ROOT / "build_replay.py"),
                                     str(root / "only-one-trace.jsonl"), "--out-dir", str(output)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual((output / "replay.html").read_bytes(), before)

    def assert_font_paths(self, urls):
        for url in urls:
            path = (ROOT / "replay.html").parent / url
            self.assertTrue(path.resolve().is_file(), f"Missing font: {url}")

    def assert_local_fonts(self, html):
        blocks = re.findall(r"@font-face\s*\{([^}]*)\}", html, re.I)
        self.assertEqual(len(blocks), 6)
        faces, urls = [], []
        for block in blocks:
            family = re.search(r'''font-family:\s*['"]([^'"]+)['"]\s*;''', block).group(1)
            weight = re.search(r"font-weight:\s*(\d+)\s*;", block).group(1)
            url = re.search(r'''src:\s*url\("([^"]+)"\)\s*format\("woff2"\)\s*;''', block).group(1)
            self.assertRegex(block, r"font-display:\s*block\s*;")
            self.assertRegex(block, r"font-style:\s*normal\s*;")
            self.assertRegex(url, r"^\.\./fonts/[\w-]+\.woff2$")
            faces.append((family, weight))
            urls.append(url)
        self.assertCountEqual(faces, [("Geist", "400"), ("Geist", "500"), ("Geist", "600"), ("Geist", "700"),
                                      ("Geist Mono", "400"), ("Geist Mono", "500")])
        self.assert_font_paths(urls)
        active_html = re.sub(r'<script id="replay-data" type="application/json">.*?</script>', '', html, flags=re.S)
        self.assertNotRegex(active_html, r'''(?i)(?:\b(?:href|src)\s*=\s*["']?\s*|url\s*\(\s*["']?\s*)(?:https?:|//|data:)|@import\b''')
        return urls

    def test_generated_and_published_html_load_local_fonts(self):
        self.assert_local_fonts((ROOT / "replay.html").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = self.trace(root / "trace.jsonl")
            replay.build(trace, trace, root / "output")
            self.assert_local_fonts((root / "output/replay.html").read_text(encoding="utf-8"))

    def test_missing_font_path_fails(self):
        urls = self.assert_local_fonts((ROOT / "replay.html").read_text(encoding="utf-8"))
        urls[0] = "../fonts/nonexistent.woff2"
        with self.assertRaisesRegex(AssertionError, "Missing font"):
            self.assert_font_paths(urls)

    def trace(self, path, final="Created index.html."):
        events = [
            {"type": "system", "session_id": "ignored", "cwd": str(path.parent)},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Write", "input": {
                    "file_path": str(path.parent / "index.html"),
                    "content": '<!doctype html>\n<button>Delete</button>\n<dialog>\n</dialog>'}},
                {"type": "text", "text": "Earlier response"}]}},
            {"type": "result", "result": final},
        ]
        path.write_text("\n".join(json.dumps(event) for event in events))
        return path

    def test_build_is_deterministic_and_removes_paths_and_uuids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identifier = "12345678-1234-1234-1234-123456789abc"
            trace = self.trace(root / "trace.jsonl", f"Created {root / 'index.html'} {identifier}.")
            replay.build(trace, trace, root / "output")
            outputs = list((root / "output").rglob("*.json")) + [root / "output/replay.html"]
            before = {p.name: p.read_bytes() for p in outputs}
            replay.build(trace, trace, root / "output")
            self.assertEqual(before, {p.name: p.read_bytes() for p in outputs})
            run = json.loads(outputs[0].read_text())
            self.assertEqual(run["final"], "Created index.html [redacted].")
            self.assertEqual(len(run["steps"]), 1)

    def test_path_normalization_keeps_html_and_relative_paths(self):
        self.assertEqual(replay.sanitize(r"C:\workspace\index.html"), "index.html")
        self.assertEqual(replay.sanitize("/opt/work/bin/vnu --format json"), "vnu --format json")
        self.assertEqual(replay.sanitize("/var/build/folder"), "~/project")
        self.assertEqual(replay.sanitize("<button>OK</button> skills/divorce/gate.py"),
                         "<button>OK</button> skills/divorce/gate.py")

    def test_residual_paths_are_rejected(self):
        for value in ("/opt/secrets/file.txt", r"C:\private\file.txt", "session_id", "cwd",
                      "12345678-1234-1234-1234-123456789abc"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                replay.validate_public({"final": value})

    def test_adversarial_paths_and_embedded_identifiers(self):
        for value in ("file:///opt/fixture/index.html", "path:/opt/fixture/index.html",
                      "-I/opt/fixture/include", "-L/opt/fixture/lib", "/",
                      r'\"/opt/fixture/index.html\"', r"\\server\private\index.html"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    replay.validate_public(value)
                replay.validate_public(replay.sanitize(value))
        identifier = "prefix12345678-1234-1234-1234-123456789abcsuffix"
        with self.assertRaises(ValueError):
            replay.validate_public(identifier)
        self.assertEqual(replay.sanitize(identifier), "prefix[redacted]suffix")
        public = 'https://example.org/docs/index.html <dialog>OK</dialog> skills/divorce/gate.py'
        self.assertEqual(replay.sanitize(public), public)
        replay.validate_public(public)

    def test_cli_rejects_unsafe_or_incomplete_trace_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = self.trace(root / "trace.jsonl")
            output = root / "output"
            replay.build(trace, trace, output)
            before = (output / "replay.html").read_bytes()
            self.trace(trace, "session_id remains private")
            result = subprocess.run([sys.executable, str(ROOT / "build_replay.py"), str(trace), str(trace),
                                     "--out-dir", str(output)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn(str(root), result.stderr)
            self.assertEqual(before, (output / "replay.html").read_bytes())
            trace.write_text('{"type": "result", "result": "No steps"}')
            with self.assertRaises(ValueError):
                replay.read_trace(trace)


if __name__ == "__main__":
    unittest.main()
