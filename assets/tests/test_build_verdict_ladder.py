import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


ASSETS = Path(__file__).resolve().parents[1]
SVG = "{http://www.w3.org/2000/svg}"


class BuildVerdictLadderTest(unittest.TestCase):
    def test_literal_rungs_and_recorded_ruling_are_reproducible(self):
        skill = (ASSETS.parent / "skills/divorce/SKILL.md").read_text()
        section = skill.split("## 1. Before writing: the ladder\n", 1)[1].split("\n## 2.", 1)[0]
        rungs = re.findall(r"^\d+\. (.+)$", section, re.MULTILINE)
        records = json.loads((ASSETS / "data/gate-real.json").read_text())
        self.assertEqual(len(records), 4)
        self.assertEqual(records[0]["html"][0]["errors"], 1)
        self.assertEqual(records[0]["verdict"], "fail")
        self.assertEqual(records[0]["reasons"], ["html_errors"])
        for record in records:
            for finding in record["html"]:
                self.assertTrue(finding["input"].startswith("examples/"))
        with tempfile.TemporaryDirectory() as directory:
            outputs = [Path(directory) / "one", Path(directory) / "two"]
            for output in outputs:
                for script in ("build_verdict.py", "build_ladder.py"):
                    subprocess.run([sys.executable, str(ASSETS / script), "--out-dir", str(output)], check=True, capture_output=True)
            for filename in ("verdict.svg", "verdict-dark.svg", "ladder.svg", "ladder-dark.svg"):
                with self.subTest(filename=filename):
                    content = (outputs[0] / filename).read_bytes()
                    self.assertEqual(content, (outputs[1] / filename).read_bytes())
                    self.assertLess(len(content), 80000)
                    svg = ET.fromstring(content)
                    texts = [" ".join("".join(node.itertext()).split()) for node in svg.findall(f".//{SVG}text")]
                    if filename.startswith("ladder"):
                        actual = [" ".join("".join(node.itertext()).split()) for node in svg.findall(f'.//{SVG}text[@class="rung"]')]
                        self.assertEqual(actual, rungs)
                        steps = svg.findall(f"{SVG}g/{SVG}rect")
                        self.assertEqual(len({node.attrib["x"] for node in steps}), 6)
                        self.assertEqual(len({node.attrib["y"] for node in steps}), 6)
                    else:
                        self.assertIn('"verdict": "fail",', texts)
                        self.assertIn('"errors": 1,', texts)
                        self.assertIn("exit=1", texts)
                        self.assertIn("examples/image-alt/before.html", texts)
                        self.assertTrue(any("python3 skills/divorce/scripts/gate.py html" in line for line in texts))


if __name__ == "__main__":
    unittest.main()
