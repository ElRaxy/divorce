import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


ASSETS = Path(__file__).resolve().parents[1]
SCRIPT = ASSETS / "build_bench.py"
FIXTURE = Path(__file__).with_name("bench-fixture.json")
SVG = "{http://www.w3.org/2000/svg}"


class BuildBenchTest(unittest.TestCase):
    def run_builder(self, input_path, output):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--input", str(input_path), "--out-dir", str(output)],
            cwd=output.parent, capture_output=True, text=True,
        )

    def test_counts_scales_metadata_and_reproducibility(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outputs = [root / "first", root / "second"]
            for output in outputs:
                result = self.run_builder(FIXTURE, output)
                self.assertEqual(result.returncode, 0, result.stderr)
            for filename in ("bench.svg", "bench-dark.svg"):
                with self.subTest(filename=filename):
                    content = (outputs[0] / filename).read_bytes()
                    self.assertEqual(content, (outputs[1] / filename).read_bytes())
                    self.assertLess(len(content), 80_000)
                    svg = ET.fromstring(content)
                    self.assertEqual(svg.find(f"{SVG}title").text, "Numbers")
                    texts = " ".join(svg.itertext())
                    self.assertIn(data["model"], texts)
                    self.assertIn("2000-01-01", texts)
                    self.assertIn("2 runs per case", texts)
                    self.assertIn("4 cases per arm", texts)
                    groups = svg.findall(f"{SVG}g")
                    self.assertEqual(len(groups), 4)
                    for group in groups:
                        metric = group.attrib["id"]
                        values = [data["arms"][arm][metric] for arm in ("with", "without")]
                        bars = [rect for rect in group.findall(f"{SVG}rect") if "data-arm" in rect.attrib]
                        self.assertEqual(len(bars), 2)
                        self.assertIn(f"scale 0–{max(values)}", " ".join(group.itertext()))
                        for bar, arm, value in zip(bars, ("with", "without"), values):
                            self.assertEqual(bar.attrib["data-arm"], arm)
                            self.assertAlmostEqual(float(bar.attrib["width"]), 640 * value / max(values), places=2)
                            self.assertIn(str(value), [node.text for node in group.findall(f"{SVG}text")])
                    self.assertIsNone(svg.find(f".//{SVG}script"))
                    self.assertFalse(any(key.endswith("href") for node in svg.iter() for key in node.attrib))

    def test_zero_metrics_render_zero_width_bars(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for arm in data["arms"].values():
            for metric in arm:
                arm[metric] = 0
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "zero.json"
            fixture.write_text(json.dumps(data), encoding="utf-8")
            result = self.run_builder(fixture, root / "cards")
            self.assertEqual(result.returncode, 0, result.stderr)
            svg = ET.parse(root / "cards" / "bench.svg").getroot()
            bars = [node for node in svg.iter() if "data-arm" in node.attrib]
            self.assertEqual(len(bars), 8)
            self.assertTrue(all(float(bar.attrib["width"]) == 0 for bar in bars))

    def test_missing_and_invalid_input_fail_without_output(self):
        base = json.loads(FIXTURE.read_text(encoding="utf-8"))
        mutations = []
        for field, value in (("date", "not-a-date"), ("model", ""), ("runs_per_case", True), ("cases", 0)):
            data = copy.deepcopy(base)
            data[field] = value
            mutations.append(data)
        for value in (-1, "3", False):
            data = copy.deepcopy(base)
            data["arms"]["with"]["gate_pass"] = value
            mutations.append(data)
        missing_arm = copy.deepcopy(base)
        del missing_arm["arms"]["without"]
        mutations.extend([missing_arm, [], {}])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = [root / "missing.json"]
            for index, data in enumerate(mutations):
                fixture = root / f"invalid-{index}.json"
                fixture.write_text(json.dumps(data), encoding="utf-8")
                inputs.append(fixture)
            for fixture in inputs:
                with self.subTest(input=fixture.name):
                    output = root / "cards"
                    result = self.run_builder(fixture, output)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("error:", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
