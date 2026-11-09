from html.parser import HTMLParser
import importlib.util
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "assets/cards/build_cards.py"
SPEC = importlib.util.spec_from_file_location("build_cards", SCRIPT)
cards = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cards)
CARD_NAMES = {f"{name}.html" for name in ("hero", "cases", "ladder", "ruling")}

INPUTS = ("examples/manifest.json", "examples/axe-measured.json", "assets/data/gate-real.json")


class Structure(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.text = []
        self.in_style = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))
        if tag == "style":
            self.in_style = True

    def handle_endtag(self, tag):
        if tag == "style":
            self.in_style = False

    def handle_data(self, value):
        if not self.in_style:
            self.text.append(value)


class BuildCardsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in INPUTS:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        self.output = self.root / "assets/cards/html"

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def fixture(self):
        data = {"date": "2026-01-02", "model": "Fixture <not a benchmark>",
                "runs_per_case": 3, "cases": 2, "arms": {}}
        samples = {
            "with": ([40, 50, 60], [24, 30, 36], [4, 6, 8], [0, 0, 0], [0, 1, 2]),
            "without": ([80, 100, 120], [32, 40, 48], [2, 4, 6], [1, 2, 3], [0, 0, 0]),
        }
        for arm, metrics in samples.items():
            data["arms"][arm] = {
                metric: {"mean": sum(runs) / len(runs), "min": min(runs), "max": max(runs), "runs": runs}
                for (metric, _), runs in zip(cards.METRICS, metrics)
            }
            data["arms"][arm].update(pages=6, pages_with_nu_errors=2 if arm == "with" else 0,
                                     pages_with_axe_violations=0 if arm == "with" else 3)
        return data

    def run_builder(self, out_dir=None):
        command = [sys.executable, str(SCRIPT), "--root", str(self.root)]
        if out_dir:
            command += ["--out-dir", str(out_dir)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def content(self, name):
        return (self.output / name).read_text(encoding="utf-8")

    def test_counts_are_union_of_recorded_nu_and_axe_findings(self):
        manifest = cards.read_json(self.root / INPUTS[0])
        measured = cards.read_json(self.root / INPUTS[1])
        expected = {row["id"] for row in manifest["cases"] if row["before_html"] == "fail"}
        expected.update(key for key, value in measured["cases"].items() if value["before"])
        rows, caught, missed = cards.evidence(manifest, measured)
        self.assertEqual(caught, len(expected))
        self.assertEqual(missed, len(manifest["cases"]) - len(expected))
        self.assertEqual((caught, missed, len(rows)), (4, 5, 9))
        self.run_builder()
        self.assertIn(f'Validators catch {caught} of {len(rows)}.<br><span class="secondary">The other {missed} look fine.</span>', self.content("hero.html"))
        self.assertIn(f"{missed} of {len(rows)}", self.content("cases.html"))

    def test_changed_inputs_change_counts_without_double_counting(self):
        manifest = cards.read_json(self.root / INPUTS[0])
        measured = cards.read_json(self.root / INPUTS[1])
        row = next(row for row in manifest["cases"] if row["id"] == "div-button")
        row["before_html"] = "fail"
        measured["cases"]["div-button"]["before"] = [{"id": "test", "impact": "serious", "nodes": 3}]
        manifest["cases"].append({**row, "id": "extra-case", "before_html": "pass"})
        measured["cases"]["extra-case"] = {"before": [], "after": []}
        self.write(INPUTS[0], manifest)
        self.write(INPUTS[1], measured)
        rows, caught, missed = cards.evidence(manifest, measured)
        self.assertEqual((caught, missed, len(rows)), (5, 5, 10))
        self.run_builder()
        self.assertIn("Validators catch 5 of 10.", self.content("hero.html"))
        self.assertIn("5 of 10", self.content("cases.html"))
        self.assertIn("axe 1 violations", self.content("hero.html"))

    def test_byte_identical_output_across_runs_and_key_order(self):
        self.write("evals/results/summary.json", self.fixture())
        self.run_builder()
        first = {p.name: p.read_bytes() for p in self.output.glob("*.html")}
        for name in (*INPUTS, "evals/results/summary.json"):
            data = cards.read_json(self.root / name)
            (self.root / name).write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
        self.run_builder()
        second = {p.name: p.read_bytes() for p in self.output.glob("*.html")}
        self.assertEqual(first, second)
        other = self.root / "elsewhere"
        self.run_builder(other)
        self.assertEqual(first, {p.name: p.read_bytes() for p in other.glob("*.html")})

    def test_no_summary_means_no_numbers_or_benchmark_figure(self):
        self.run_builder()
        self.assertEqual({p.name for p in self.output.glob("*.html")},
                         CARD_NAMES | {"social.html"})
        for path in self.output.glob("*.html"):
            parsed = Structure(path.read_text(encoding="utf-8"))
            self.assertFalse(any(attrs.get("class") == "benchmark" for _, attrs in parsed.elements))
            self.assertFalse(any(attrs.get("class") == "bar-row" for _, attrs in parsed.elements))
            self.assertNotIn("Gate passes", " ".join(parsed.text))
        self.write("evals/results/summary.json", self.fixture())
        self.run_builder()
        self.assertTrue((self.output / "numbers.html").exists())
        (self.root / "evals/results/summary.json").unlink()
        self.run_builder()
        self.assertFalse(list(self.output.glob("numbers*.html")))

    def test_html_structure_including_optional_numbers(self):
        self.write("evals/results/summary.json", self.fixture())
        self.run_builder()
        for path in self.output.glob("*.html"):
            with self.subTest(card=path.name):
                parsed = Structure(path.read_text(encoding="utf-8"))
                elements = parsed.elements
                self.assertEqual([attrs.get("lang") for tag, attrs in elements if tag == "html"], ["en"])
                self.assertEqual(sum(tag == "title" for tag, _ in elements), 1)
                self.assertEqual(sum(tag == "h1" for tag, _ in elements), 1)
                self.assertTrue(all(attrs.get("alt", "").strip() for tag, attrs in elements if tag == "img"))
                headings = [int(tag[1]) for tag, _ in elements if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}]
                self.assertTrue(all(after <= before + 1 for before, after in zip([0] + headings, headings)))
                self.assertFalse(any(tag == "link" and attrs.get("href", "").startswith("http")
                                     for tag, attrs in elements))
                self.assertFalse(any(tag in ("script", "svg") for tag, _ in elements))

    def assert_font_paths(self, urls):
        for url in urls:
            path = (ROOT / "assets/cards/html" / url).resolve()
            self.assertTrue(path.is_file(), f"Missing font: {url}")

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
            self.assertRegex(url, r"^\.\./\.\./fonts/[\w-]+\.woff2$")
            faces.append((family, weight))
            urls.append(url)
        self.assertCountEqual(faces, [("Geist", weight) for weight in ("400", "500", "600", "700")]
                              + [("Geist Mono", "400"), ("Geist Mono", "500")])
        self.assert_font_paths(urls)
        self.assertNotRegex(html, r'''(?i)(?:\b(?:href|src)\s*=\s*["']?\s*|url\s*\(\s*["']?\s*)(?:https?:|//|data:)|@import\b''')
        return urls

    def test_generated_and_published_html_load_local_fonts(self):
        self.write("evals/results/summary.json", self.fixture())
        self.run_builder()
        published = sorted((ROOT / "assets/cards/html").glob("*.html"))
        self.assertEqual({p.name for p in published},
                         CARD_NAMES | {"social.html", "numbers.html"})
        for path in [*self.output.glob("*.html"), *published]:
            with self.subTest(card=str(path)):
                self.assert_local_fonts(path.read_text(encoding="utf-8"))

    def test_missing_font_path_fails(self):
        urls = self.assert_local_fonts(cards.document("Fonts", ""))
        urls[0] = "../../fonts/nonexistent.woff2"
        with self.assertRaisesRegex(AssertionError, "Missing font"):
            self.assert_font_paths(urls)

    def test_hero_and_social_have_distinct_branding(self):
        self.run_builder()
        hero = self.content("hero.html")
        parsed = Structure(hero)
        self.assertFalse(any(tag == "img" for tag, _ in parsed.elements))
        self.assertFalse(any(attrs.get("class") in ("brand", "wordmark") for _, attrs in parsed.elements))
        self.assertIn('<h1 class="display">Validators catch ', hero)
        self.assertIn('<div class="pair">', hero)
        self.assertIn("&lt;div onclick&gt;", hero)
        self.assertIn("&lt;button&gt;", hero)
        social = self.content("social.html")
        self.assertIn(cards.MASCOT, social)
        self.assertIn('<h1 class="wordmark">divorce</h1>', social)

    def test_hero_shows_keyboard_outcomes_and_focus_indicators(self):
        self.run_builder()
        html = self.content("hero.html")
        self.assertIn('<p class="quiet"><kbd>Tab</kbd> → skipped</p>\n<p>no role</p>', html)
        self.assertIn('<p class="green"><kbd>Tab</kbd> → focused</p>\n<p>button role</p>', html)
        self.assertIn("outline: 1.5px dashed var(--text-3);", html)
        self.assertIn("outline: 2px solid var(--green);", html)
        self.assertIn("border-radius: 10px; outline-offset: 8px;", html)
        self.assertIn("kbd { font: 400 13px/1.5 'Geist Mono', monospace;", html)
        self.assertIn("border-radius: 6px; padding: 2px 8px;", html)

    def test_ladder_preserves_previous_readme_literals_and_omits_missing_answers(self):
        previous_readme_lines = (
            "Does it need to exist? If not, omit it.",
            "Does the project already have it? Reuse it.",
            "Is there a native HTML element for it? Use it.",
            "Can CSS do it without JavaScript?",
            "Does an installed dependency cover it?",
            "Only then: the smallest code that works, plus a small test for logic.",
        )
        self.assertIsInstance(cards.LADDER, tuple)
        self.assertTrue(all(isinstance(row, tuple) and len(row) == 2 for row in cards.LADDER))
        self.assertEqual(tuple(question + (" " + answer if answer is not None else "")
                               for question, answer in cards.LADDER), previous_readme_lines)
        self.assertEqual(tuple(answer for _, answer in cards.LADDER[3:5]), (None, None))
        self.run_builder()
        html = self.content("ladder.html")
        self.assertIn('<p class="label">HOW IT WORKS</p>', html)
        self.assertIn('<h1>Stop at the first rung that holds.</h1>', html)
        rows = re.findall(r"<li>(.*?)</li>", html, re.S)
        self.assertEqual(len(rows), 6)
        for number, (row, literal) in enumerate(zip(rows, previous_readme_lines), 1):
            parsed = Structure(row)
            self.assertEqual(" ".join(value.strip() for value in parsed.text if value.strip()),
                             f"{number:02d} {literal}")
            self.assertEqual(sum(tag == "p" for tag, _ in parsed.elements), 0 if number in (4, 5) else 1)
        self.assertIn(".ladder-list { width: 600px; margin: 0 auto;", html)
        self.assertIn(".ladder-list li + li { border-top: 1px solid var(--hairline); }", html)

    def test_card_padding_preserves_social_styles(self):
        self.write("evals/results/summary.json", self.fixture())
        self.run_builder()
        for name in CARD_NAMES | {"numbers.html"}:
            self.assertIn("main { padding: 56px 64px; }", self.content(name))
        social = self.content("social.html")
        self.assertIn(f"<style>{cards.CSS}</style>", social)
        self.assertIn("main { padding: 72px 64px;", social)
        self.assertNotIn(cards.CARD_CSS, social)

    def test_frameless_surfaces_and_obsolete_html_cleanup(self):
        self.write("evals/results/summary.json", self.fixture())
        self.output.mkdir(parents=True)
        names = ("hero", "cases", "ruling", "numbers", "social", "ladder")
        for name in names:
            for theme in ("light", "dark"):
                (self.output / f"{name}-{theme}.html").write_text("obsolete", encoding="utf-8")
        unrelated = self.output / "unrelated.txt"
        unrelated.write_text("keep", encoding="utf-8")
        self.run_builder()
        self.assertEqual({path.name for path in self.output.glob("*.html")},
                         {f"{name}.html" for name in names})
        for name in names:
            html = self.content(f"{name}.html")
            css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
            self.assertIn("--bg: #0d1117", css)
            for element in ("html", "body", "main"):
                rules = [body for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
                         if element in [selector.strip() for selector in selectors.split(",")]]
                self.assertTrue(any("background: var(--bg);" in rule for rule in rules), element)
            for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
                if any(re.search(r"(?:^|\s)(?:html|body|main)(?:[.#][\w-]+)*$", selector.strip())
                       or selector.strip() in ("*", ".social", ".hero", ".cases", ".ruling", ".benchmark")
                       for selector in selectors.split(",")):
                    self.assertNotRegex(body, r"(?:^|;)\s*border(?:-[\w-]+)?\s*:")
            self.assertRegex(css, r"\.surface\s*\{[^}]*border: 1px solid var\(--hairline\);")
            self.assertRegex(html, r"body \{[^}]*margin: 0;")
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep")

    def test_cases_grid_and_content_are_derived_from_data(self):
        self.run_builder()
        html = self.content("cases.html")
        self.assertNotIn("<table", html)
        self.assertIn("grid-template-columns: repeat(3, 240px); gap: 12px;", html)
        self.assertIn(".case { height: 88px; border-radius: 16px;", html)
        manifest = cards.read_json(self.root / INPUTS[0])
        measured = cards.read_json(self.root / INPUTS[1])
        rows, _, missed = cards.evidence(manifest, measured)
        self.assert_cases_rows(html, rows, missed)
        for row in rows:
            self.assertEqual(row["violations"], measured["cases"][row["id"]]["before"])
        rows[0]["tools"] = ["Nu"]
        changed = cards.cases_card(list(reversed(rows)), missed - 1, measured)
        self.assert_cases_rows(changed, rows, missed - 1)

    def assert_cases_rows(self, html, rows, missed):
        actual = re.findall(r'<li class="(case(?: missed)?)">(.*?)</li>', html, re.S)
        expected = sorted(rows, key=lambda row: (bool(row["tools"]), row["id"]))
        self.assertEqual(len(actual), len(expected))
        self.assertEqual([kind for kind, _ in actual], ["case missed"] * missed + ["case"] * (len(rows) - missed))
        for (_, cell), row in zip(actual, expected):
            parsed = Structure(cell)
            self.assertIn(row["id"], " ".join(parsed.text))
            detector = " + ".join(row["tools"]) if row["tools"] else "no tool flags it"
            self.assertIn(f'<span class="detector">{detector}</span>', cell)

    def test_readme_keeps_centered_header_and_single_cards(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        visible = re.sub(r"<!--.*?-->", "", readme, flags=re.S)
        top = visible.split("## Install", 1)[0]
        self.assertIn('<p align="center"><img src="assets/mascot.png" width="200"', top)
        self.assertIn('<h1 align="center">divorce</h1>', top)
        self.assertIn('<p align="center"><em>End your agent\'s toxic relationship with div soup.</em>'
                      '<br>A skill for Claude Code and Codex: native HTML first, then proof.</p>', top)
        self.assertNotIn("<picture", visible)
        parsed = Structure(visible)
        images = [attrs for tag, attrs in parsed.elements if tag == "img"]
        expected = ["assets/mascot.png", "assets/cards/hero.png", "assets/demo/replay.gif",
                    "assets/cards/numbers.png", "assets/cards/cases.png", "assets/cards/ladder.png",
                    "assets/cards/ruling.png"]
        self.assertEqual([attrs["src"] for attrs in images], expected)
        self.assertEqual([attrs["width"] for attrs in images], ["200"] + ["880"] * 6)
        self.assertTrue(all(attrs.get("alt", "").strip() for attrs in images))
        centered = re.findall(r'<p align="center"><img\b[^>]*></p>', visible)
        self.assertEqual(len(centered), len(images))
        self.assertEqual(re.findall(r"^## (.+)$", visible, re.M),
                         ["Install", "Details", "License"])
        self.assertEqual(sum(tag == "details" for tag, _ in parsed.elements), 1)
        self.assertLess(len(readme.splitlines()), 120)
        self.assertIn("plugin install", "\n".join(readme.splitlines()[:25]))
        story = ('<p align="center">Your agent writes <code>&lt;div onclick&gt;</code>. '
                 "Every validator says it's fine. Someone using a keyboard can't reach it. "
                 'divorce makes the agent pick the native element first, then proves it with Nu and axe.</p>')
        self.assertIn(story, top)
        self.assertLess(top.index('src="assets/cards/hero.png"'), top.index(story))
        self.assertLess(top.index(story), top.index('src="assets/demo/replay.gif"'))
        self.assertTrue(images[2]["alt"].startswith(
            "Two recorded runs of the same modal task, same prompt and model."))
        self.assertEqual(visible.count("<sub>"), 1)
        self.assertIn('<p align="center"><sub>Other agents and routes: '
                      '<a href="#details">Details</a></sub></p>', visible)
        details = visible.split("<details>", 1)[1]
        self.assertEqual(re.findall(r"<h3>(.*?)</h3>", details)[0], "Evidence")
        evidence = details.split("<h3>Evidence</h3>", 1)[1].split("<h3>", 1)[0]
        for link in ("evals/README.md", "examples/manifest.json", "assets/data/gate-real.json"):
            self.assertIn(f'href="{link}"', evidence)

    def test_ruling_is_recorded_result_not_a_fixed_verdict(self):
        records = cards.read_json(self.root / INPUTS[2])
        fail = next(record for record in records if record["verdict"] == "fail")
        self.run_builder()
        html = self.content("ruling.html")
        text = " ".join(Structure(html).text)
        self.assertIn("Code delivers the verdict.", text)
        self.assertNotIn('"verdict"', html)
        self.assertNotIn("<pre", html)
        self.assertIn("FAIL", text)
        self.assertIn("exit 1", text)
        for entry in fail["html"]:
            self.assertIn("/".join(Path(entry["input"]).parts[-2:]), text)
        self.assertIn(f'<dt class="label">NU ERRORS</dt><dd><code>{sum(e["errors"] for e in fail["html"])}</code>', html)
        self.assertIn(f'<dt class="label">WARNINGS</dt><dd><code>{sum(e["warnings"] for e in fail["html"])}</code>', html)
        self.assertIn(", ".join(fail["reasons"]), text)
        passed = next(record for record in records if record["verdict"] == "pass")
        self.write(INPUTS[2], [passed])
        self.run_builder()
        self.assertIn("PASS", self.content("ruling.html"))
        self.assertIn("exit 0", self.content("ruling.html"))
        changed = {"verdict": "not_measured", "html": [{"input": "examples/test/before.html",
                   "errors": None, "warnings": None}], "reasons": ["validator_missing"]}
        self.write(INPUTS[2], [changed])
        self.run_builder()
        self.assertIn("NOT_MEASURED", self.content("ruling.html"))
        self.assertIn("exit 2", self.content("ruling.html"))
        self.assertIn("validator_missing", self.content("ruling.html"))
        self.assertIn('<dt class="label">NU ERRORS</dt><dd><code>not_measured</code>', self.content("ruling.html"))

    def test_numbers_percentages_and_rounded_means(self):
        data = self.fixture()
        self.write("evals/results/summary.json", data)
        self.run_builder()
        html = self.content("numbers.html")
        self.assertIn("Same agent. Same 2 tasks. 3 runs each.", html)
        self.assertNotIn(data["model"], " ".join(Structure(html).text))
        self.assertNotRegex(html.lower(), r'range|class="track')
        sections = re.findall(r'<section class="surface metric"[^>]*>(.*?)</section>', html, re.S)
        self.assertEqual(len(sections), 4)
        for section, (metric, label) in zip(sections, cards.METRICS):
            self.assertIn(cards.percentage_change(data, metric), section)
            self.assertNotRegex(section, r"\d\s+%")
            self.assertIn(label, section)
            self.assertIn(f'{round(data["arms"]["without"][metric]["mean"])} → '
                          f'{round(data["arms"]["with"][metric]["mean"])}', section)
        self.assertNotIn('id="nu_errors"', html)

    def test_numbers_visible_percentages_are_integers(self):
        data = cards.read_json(ROOT / "evals/results/summary.json")
        self.write("evals/results/summary.json", data)
        self.run_builder()
        visible = " ".join(Structure(self.content("numbers.html")).text)
        self.assertNotRegex(visible, r"\d+\.\d+\s*%")
        self.assertEqual(len(re.findall(r"[−+]?\d+%", visible)), 4)
        self.assertNotRegex(visible, r"\d\s+%")
        self.assertIn("−41%", visible)

    def test_numbers_grid_uses_specified_dimensions(self):
        self.write("evals/results/summary.json", self.fixture())
        self.run_builder()
        html = self.content("numbers.html")
        self.assertIn("grid-template-columns: repeat(2, 360px); gap: 16px;", html)
        self.assertIn(".metric { height: 180px;", html)
        self.assertEqual(len(re.findall(r'<section class="surface metric"', html)), 4)

    def test_social_uses_evidence_counts_and_specified_composition(self):
        self.write("evals/results/summary.json", self.fixture())
        self.run_builder()
        rows, caught, missed = cards.evidence(cards.read_json(self.root / INPUTS[0]),
                                              cards.read_json(self.root / INPUTS[1]))
        social = self.content("social.html")
        self.assertIn(f"Validators catch {caught} of {len(rows)}. The other {missed} look fine.", social)
        self.assertIn("End your agent's toxic relationship with div soup.", social)
        self.assertIn(".social { width: 1280px; height: 640px; text-align: left; }", social)
        self.assertIn("width: 360px; height: 360px;", social)
        data = self.fixture()
        self.assertEqual(cards.percentage_change(data, "js_lines"), "−25%")
        self.assertEqual(cards.percentage_change(data, "axe_violation_nodes"), "−100%")
        data = cards.read_json(ROOT / "evals/results/summary.json")
        self.assertEqual(cards.percentage_change(data, "js_lines"), "−41%")
        self.assertEqual(cards.percentage_change(data, "axe_violation_nodes"), "−76%")

    def test_zero_baseline_does_not_invent_percentage(self):
        data = self.fixture()
        data["arms"]["without"]["js_lines"] = {"mean": 0, "min": 0, "max": 0, "runs": [0]}
        self.assertEqual(cards.percentage_change(data, "js_lines"), "not measured")

    def test_hero_footer_reflects_both_measured_examples(self):
        manifest = cards.read_json(self.root / INPUTS[0])
        measured = cards.read_json(self.root / INPUTS[1])
        self.run_builder()
        self.assertIn("Both pass Nu and axe.", self.content("hero.html"))
        case = next(row for row in manifest["cases"] if row["id"] == "div-button")
        for side in ("before", "after"):
            for tool in ("nu", "axe"):
                with self.subTest(side=side, tool=tool):
                    if tool == "nu":
                        case[side + "_html"] = "fail"
                    else:
                        measured["cases"]["div-button"][side] = [{"id": "test", "impact": "serious", "nodes": 2}]
                    rows, caught, missed = cards.evidence(manifest, measured)
                    html = cards.hero(rows, caught, missed, measured)
                    self.assertNotIn("Both pass Nu and axe.", html)
                    self.assertIn("Nu fail" if tool == "nu" else "axe 1 violations", html)
                    case[side + "_html"] = "pass"
                    measured["cases"]["div-button"][side] = []

    def test_nu_page_line_is_visible_and_calculated_from_fixture(self):
        data = self.fixture()
        data["arms"]["with"].update(pages=9, pages_with_nu_errors=4)
        data["arms"]["without"].update(pages=12, pages_with_nu_errors=2)
        html = cards.numbers_card(cards.validate_summary(data))
        line = "Nu errors: 4 of 9 pages with divorce, 2 of 12 without."
        self.assertIn(line, html.split("<footer>")[0])
        self.assertRegex(html, r'<p[^>]*>' + re.escape(line) + r'</p>')
        self.assertNotIn("<details", html)

    def test_real_summary_numbers_and_nu_pages(self):
        data = cards.read_json(ROOT / "evals/results/summary.json")
        self.write("evals/results/summary.json", data)
        self.run_builder()
        html = self.content("numbers.html")
        for percent in ("−29", "−41", "−33", "−76"):
            self.assertIn(f">{percent}%</p>", html)
        self.assertIn("Nu errors: 3 of 40 pages with divorce, 0 of 40 without", html)

    def test_zero_baseline_has_no_bar_but_retains_means(self):
        data = self.fixture()
        for metric, _ in cards.METRICS:
            data["arms"]["without"][metric] = {"mean": 0, "min": 0, "max": 0, "runs": [0]}
        self.write("evals/results/summary.json", data)
        self.run_builder()
        html = self.content("numbers.html")
        parsed = Structure(html)
        bars = [attrs for _, attrs in parsed.elements if attrs.get("class", "").startswith("bar ")]
        self.assertEqual(bars, [])
        self.assertIn("No percentage: baseline is zero.", html)
        self.assertIn("0 → 50", html)
        self.assertNotIn("range", html.lower())

    def assert_invalid_summary_without_writes(self, data):
        with self.assertRaises(ValueError):
            cards.validate_summary(data)
        self.write("evals/results/summary.json", data)
        with self.assertRaises(ValueError):
            cards.build(self.root)
        self.assertFalse(self.output.exists())

    def test_invalid_summary_metadata(self):
        for key, value in (("date", "invalid"), ("model", ""), ("cases", 0), ("runs_per_case", True)):
            with self.subTest(field=key):
                data = self.fixture()
                data[key] = value
                self.assert_invalid_summary_without_writes(data)

    def test_missing_runs_is_rejected_before_writing(self):
        data = self.fixture()
        del data["arms"]["with"]["html_lines"]["runs"]
        self.assert_invalid_summary_without_writes(data)

    def test_inconsistent_min_is_rejected_before_writing(self):
        data = self.fixture()
        data["arms"]["with"]["html_lines"]["min"] -= 1
        self.assert_invalid_summary_without_writes(data)

    def test_nu_pages_exceeding_pages_is_rejected_before_writing(self):
        data = self.fixture()
        data["arms"]["with"]["pages_with_nu_errors"] = data["arms"]["with"]["pages"] + 1
        self.assert_invalid_summary_without_writes(data)

    def test_noninteger_is_rejected_before_writing(self):
        for invalid in (1.5, "3", False):
            with self.subTest(value=invalid):
                data = self.fixture()
                data["arms"]["with"]["html_lines"]["runs"][0] = invalid
                self.assert_invalid_summary_without_writes(data)

    def test_invalid_statistics_and_page_counts_in_either_arm(self):
        for arm in ("with", "without"):
            for metric, _ in cards.METRICS:
                for key, invalid in (("runs", []), ("runs", [-1]), ("runs", None),
                                     ("min", False), ("max", 999), ("max", 1.5),
                                     ("mean", -1), ("mean", True), ("mean", "3"),
                                     ("mean", float("nan")), ("mean", float("inf"))):
                    with self.subTest(arm=arm, metric=metric, field=key, value=invalid):
                        data = self.fixture()
                        data["arms"][arm][metric][key] = invalid
                        self.assert_invalid_summary_without_writes(data)
            for key in ("pages", "pages_with_nu_errors", "pages_with_axe_violations"):
                for invalid in (-1, False, 1.5, "3"):
                    with self.subTest(arm=arm, field=key, value=invalid):
                        data = self.fixture()
                        data["arms"][arm][key] = invalid
                        self.assert_invalid_summary_without_writes(data)
            data = self.fixture()
            data["arms"][arm]["pages_with_axe_violations"] = data["arms"][arm]["pages"] + 1
            self.assert_invalid_summary_without_writes(data)

    def test_invalid_summary_preserves_existing_cards(self):
        self.write("evals/results/summary.json", self.fixture())
        self.run_builder()
        before = {path.name: path.read_bytes() for path in self.output.glob("*.html")}
        self.write("evals/results/summary.json", {})
        result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.root)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.output.glob("*.html")})

    def test_palette_text_contrast(self):
        self.assertTrue(re.sub(r"@font-face\s*\{[^}]*\}", "", cards.CSS).lstrip().startswith(":root {"))
        self.assertIn("--bg: #0d1117", cards.CSS)
        self.assertIn("--red: #ff453a", cards.CSS)
        self.assertIn("--green: #30d158", cards.CSS)

        def luminance(color):
            channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            channels = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
            return sum(v * weight for v, weight in zip(channels, (.2126, .7152, .0722)))

        def ratio(foreground, background):
            light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
            return (light + .05) / (dark + .05)

        for background in ("#0d1117", "#161b22"):
            for foreground in ("#f5f5f7", "#a1a1a6", "#86868b", "#30d158"):
                self.assertGreaterEqual(ratio(foreground, background), 4.5)
            self.assertGreaterEqual(ratio("#ff453a", background), 4.5)


if __name__ == "__main__":
    unittest.main()
