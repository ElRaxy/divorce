import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


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
        self.assertEqual([s["tool"] for s in without_run["steps"]], ["Write"])
        self.assertEqual([s["tool"] for s in with_run["steps"]], ["Skill", "Write", "Bash", "Bash", "Bash"])
        self.assertIn("divorce", with_run["steps"][0]["summary"])
        self.assertIn("gate.py", with_run["steps"][2]["summary"])
        self.assertIn("vnu --format json", with_run["steps"][4]["summary"])
        self.assertTrue(without_run["final"].startswith("I've created `index.html`"))
        self.assertTrue(with_run["final"].startswith("I wrote `index.html`, but I couldn't run"))
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
        for text in ("claimed done · checks: none", "checks: not_measured · not claimed",
                     "Replay of two recorded runs from the benchmark (same task, same model)."):
            self.assertIn(text, html)
        embedded = json.loads(re.search(r'<script id="replay-data" type="application/json">(.*?)</script>', html, re.S).group(1))
        for arm in ("with", "without"):
            self.assertEqual(embedded[arm], json.loads((ROOT / f"data/modal-{arm}.json").read_text()))

    def assert_font_paths(self, urls):
        for url in urls:
            path = (ROOT / "replay.html").parent / url
            self.assertTrue(path.resolve().is_file(), f"Missing font: {url}")

    def assert_local_fonts(self, html):
        blocks = re.findall(r"@font-face\s*\{([^}]*)\}", html, re.I)
        self.assertEqual(len(blocks), 4)
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
        self.assertCountEqual(faces, [("Bricolage Grotesque", "700"), ("Bricolage Grotesque", "800"),
                                      ("JetBrains Mono", "400"), ("JetBrains Mono", "700")])
        self.assert_font_paths(urls)
        self.assertNotRegex(html, r'''(?i)(?:\b(?:href|src)\s*=\s*["']?\s*|url\s*\(\s*["']?\s*)(?:https?:|//|data:)|@import\b''')
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
