import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


SCRIPT = Path(__file__).resolve().parents[1] / "build_cases.py"
SVG = "{http://www.w3.org/2000/svg}"


class BuildCasesTest(unittest.TestCase):
    def test_manifest_count_tags_and_reproducibility(self):
        cases = [
            {"id": "only-nu", "title": "Nu only", "before_html": "fail", "axe_rules": []},
            {"id": "only-axe", "title": "axe only", "before_html": "pass", "axe_rules": []},
            {"id": "both", "title": "Both tools", "before_html": "fail", "axe_rules": ["image-alt", "other"]},
            {"id": "none-&-safe", "title": "<No tool>", "before_html": "pass", "axe_rules": ["label"]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "fixture.json"
            manifest.write_text(json.dumps({"cases": cases}), encoding="utf-8")
            measured = root / "measured.json"
            measured.write_text(json.dumps({"cases": {
                "only-nu": {"before": [], "after": []},
                "only-axe": {"before": [{"id": "tabindex", "impact": "serious", "nodes": 1}], "after": []},
                "both": {"before": [
                    {"id": "heading-order", "impact": "moderate", "nodes": 1},
                    {"id": "image-alt", "impact": "critical", "nodes": 1},
                    {"id": "tabindex", "impact": "serious", "nodes": 1},
                ], "after": []},
                "none-&-safe": {"before": [], "after": [{"id": "label", "impact": "critical", "nodes": 1}]},
            }}), encoding="utf-8")
            outputs = [root / "first", root / "second"]
            for output in outputs:
                subprocess.run(
                    [sys.executable, str(SCRIPT), "--manifest", str(manifest),
                     "--axe-measured", str(measured), "--out-dir", str(output)],
                    cwd=root, check=True, capture_output=True,
                )
            for filename in ("cases.svg", "cases-dark.svg"):
                with self.subTest(filename=filename):
                    first = (outputs[0] / filename).read_bytes()
                    self.assertEqual(first, (outputs[1] / filename).read_bytes())
                    svg = ET.fromstring(first)
                    self.assertEqual(svg.find(f"{SVG}title").text, "3 of 4 caught by tools")
                    texts = [node.text for node in svg.findall(f"{SVG}text")]
                    self.assertIn("3 of 4 caught by tools", texts)
                    self.assertIn("Nu and axe measured", texts)
                    groups = svg.findall(f"{SVG}g")
                    self.assertEqual(len(groups), len(cases))
                    names_and_tags = [
                        [node.text for node in group.findall(f"{SVG}text")]
                        for group in groups
                    ]
                    self.assertEqual(names_and_tags, [
                        ["only nu", "Nu"],
                        ["only axe", "axe", "axe: serious"],
                        ["both", "Nu + axe", "axe: critical"],
                        ["none & safe", "no tool: the ladder"],
                    ])
                    self.assertEqual(groups[-1].find(f"{SVG}title").text, "<No tool>")

    def test_missing_measurement_fails_without_writing_cards(self):
        for measured_cases in ({}, {"absent": {"after": []}}):
            with self.subTest(measured_cases=measured_cases), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                manifest = root / "manifest.json"
                manifest.write_text(json.dumps({"cases": [
                    {"id": "absent", "title": "Absent", "before_html": "pass", "axe_rules": []},
                ]}), encoding="utf-8")
                measured = root / "measured.json"
                measured.write_text(json.dumps({"cases": measured_cases}), encoding="utf-8")
                output = root / "output"
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--manifest", str(manifest),
                     "--axe-measured", str(measured), "--out-dir", str(output)],
                    cwd=root, capture_output=True, text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("absent", result.stderr)
                self.assertIn("measured axe", result.stderr)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
