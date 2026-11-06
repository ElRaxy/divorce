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
THEMES = ("light", "dark")
CARD_NAMES = {f"{name}-{theme}.html" for name in ("hero", "cases", "ruling") for theme in THEMES}

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
        if name == "social.html":
            return (self.output / name).read_text(encoding="utf-8")
        variants = [(self.output / name.replace(".html", f"-{theme}.html")).read_text(encoding="utf-8")
                    for theme in THEMES]
        # Every content assertion also covers the dark variant's identical evidence.
        self.assertEqual(variants[0].replace("#ffffff", "#0d1117").replace("#6e7681", "#8b949e"), variants[1])
        return variants[0]

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
        self.assertIn(f"Validators catch {caught} of these {len(rows)}.<br>The other {missed} look fine to every tool.", self.content("hero.html"))
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
        self.assertIn("Validators catch 5 of these 10.", self.content("hero.html"))
        self.assertIn("5 of 10", self.content("cases.html"))
        self.assertIn("axe: 1 violations", self.content("hero.html"))

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
        for theme in THEMES:
            self.assertTrue((self.output / f"numbers-{theme}.html").exists())
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
        self.assertEqual(len(blocks), 4)
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
        self.assertCountEqual(faces, [("Bricolage Grotesque", "700"), ("Bricolage Grotesque", "800"),
                                      ("JetBrains Mono", "400"), ("JetBrains Mono", "700")])
        self.assert_font_paths(urls)
        self.assertNotRegex(html, r'''(?i)(?:\b(?:href|src)\s*=\s*["']?\s*|url\s*\(\s*["']?\s*)(?:https?:|//|data:)|@import\b''')
        return urls

    def test_generated_and_published_html_load_local_fonts(self):
        self.write("evals/results/summary.json", self.fixture())
        self.run_builder()
        published = sorted((ROOT / "assets/cards/html").glob("*.html"))
        self.assertEqual({p.name for p in published},
                         CARD_NAMES | {"social.html", "numbers-light.html", "numbers-dark.html"})
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
        self.assertIn('<h1 class="hook">Validators catch ', hero)
        self.assertIn('<div class="pair">', hero)
        self.assertIn("&lt;div onclick&gt;", hero)
        self.assertIn("&lt;button&gt;", hero)
        social = self.content("social.html")
        self.assertIn(cards.MASCOT, social)
        self.assertIn('<h1 class="wordmark">divorce</h1>', social)

    def test_variant_surfaces_and_obsolete_html_cleanup(self):
        self.write("evals/results/summary.json", self.fixture())
        self.output.mkdir(parents=True)
        for name in ("hero", "cases", "ruling", "numbers"):
            (self.output / f"{name}.html").write_text("obsolete", encoding="utf-8")
        unrelated = self.output / "unrelated.txt"
        unrelated.write_text("keep", encoding="utf-8")
        self.run_builder()
        for name in ("hero", "cases", "ruling", "numbers"):
            self.assertFalse((self.output / f"{name}.html").exists())
            for theme, page, border in (("light", "#ffffff", "#6e7681"),
                                        ("dark", "#0d1117", "#8b949e")):
                html = (self.output / f"{name}-{theme}.html").read_text(encoding="utf-8")
                self.assertIn(f"html, body {{ background: {page}; }}", html)
                self.assertIn(f"main {{ background: var(--bg); border: 1px solid {border}; border-radius: 24px; }}", html)
                self.assertRegex(html, r"body \{[^}]*margin: 0;")
                self.assertNotEqual(page, border)
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep")

    def test_cases_height_and_row_content_are_derived_from_css_and_data(self):
        self.run_builder()
        html = self.content("cases.html")
        css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)

        def declaration(selector, property_name):
            rules = re.findall(re.escape(selector) + r"\s*\{([^}]*)\}", css)
            values = [match.group(1).strip() for rule in rules
                      if (match := re.search(r"(?:^|;)\s*" + re.escape(property_name) + r":\s*([^;]+)", rule))]
            self.assertTrue(values, (selector, property_name))
            return values[-1]

        def pixels(selector, property_name):
            value = declaration(selector, property_name)
            self.assertRegex(value, r"^\d+px$")
            return int(value[:-2])

        row_count = len(re.findall(r'<tr class="case(?: missed)?">', html))
        border = int(declaration("main", "border").split("px", 1)[0])
        head_margin = declaration(".case-head", "margin").split()
        self.assertEqual(len(head_margin), 2)
        self.assertEqual(head_margin[1], "0")
        height = (2 * pixels(".cases main", "padding") + 2 * border
                  + pixels(".cases .label", "height")
                  + pixels(".case-head", "height") + 2 * int(head_margin[0][:-2])
                  + pixels(".case-table thead tr", "height")
                  + row_count * pixels(".case", "height")
                  + pixels(".cases footer", "margin-top") + pixels(".cases footer", "height"))
        self.assertLessEqual(height, 700, f"cases CSS height: {height}px")
        self.assertEqual(declaration(".case-head", "display"), "flex")
        self.assertEqual(declaration(".case-head", "white-space"), "nowrap")
        self.assertEqual(declaration(".case-table", "border-spacing"), "0")
        self.assertEqual(declaration(".case-table th, .case-table td", "white-space"), "nowrap")
        self.assertGreaterEqual(pixels(".case", "height"), pixels(".case", "line-height") + 1)
        self.assertEqual(declaration(".case.missed", "color"), "var(--red)")
        self.assertEqual(declaration(".catch-nothing", "color"), "var(--red)")
        self.assertEqual(len({declaration(f".catch-{tool}", "color") for tool in ("nu", "axe", "nothing")}), 3)
        self.assertNotRegex(css, r"(?:\.cases[^{}]*|\.case[^{}]*)\{[^}]*overflow\s*:\s*(?:hidden|clip)")
        manifest = cards.read_json(self.root / INPUTS[0])
        measured = cards.read_json(self.root / INPUTS[1])
        rows, _, missed = cards.evidence(manifest, measured)
        self.assertEqual(row_count, len(rows))
        self.assert_cases_rows(html, rows, missed)
        # Change a previously missed row so alphabetical order cannot mimic grouping.
        rows[0]["tools"] = ["Nu"]
        changed = cards.cases_card(list(reversed(rows)), missed - 1, measured, "light")
        self.assert_cases_rows(changed, rows, missed - 1)

    def assert_cases_rows(self, html, rows, missed):
        actual = re.findall(r'<tr class="(case(?: missed)?)">(.*?)</tr>', html, re.S)
        expected = sorted(rows, key=lambda row: (bool(row["tools"]), row["id"]))
        self.assertEqual(len(actual), len(expected))
        self.assertEqual([kind for kind, _ in actual], ["case missed"] * missed + ["case"] * (len(rows) - missed))
        for index, ((_, cell), row) in enumerate(zip(actual, expected), 1):
            parsed = Structure(cell)
            self.assertEqual(sum(tag in ("td", "th") for tag, _ in parsed.elements), 4)
            self.assertIn(f">{index:02d}</td>", cell)
            self.assertIn(row["id"], " ".join(parsed.text))
            for tool in row["tools"] or ["nothing"]:
                self.assertIn(f'<span class="catch-{tool.lower()}">{tool}</span>', cell)
            if row["violations"]:
                impact = max((v["impact"] for v in row["violations"]), key=cards.IMPACTS.index)
                nodes = sum(v["nodes"] for v in row["violations"])
                self.assertIn(f"axe: {impact} · {nodes} affected node", cell)
            else:
                self.assertIn("No axe violation recorded", cell)

    def test_readme_keeps_header_and_selects_card_variants(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        top = readme.split("<picture>", 1)[0]
        self.assertIn('src="assets/mascot.png"', top)
        self.assertIn('<h1 align="center">divorce</h1>', top)
        self.assertIn("End your agent's toxic relationship with div soup. Write native HTML. Let code deliver the verdict.", top)
        pictures = re.findall(r"<picture>(.*?)</picture>", readme, re.S)
        self.assertEqual(len(pictures), 5)
        for name, picture in zip(("hero", "numbers", "cases", "ruling"), pictures[:4]):
            parsed = Structure(picture)
            sources = [attrs for tag, attrs in parsed.elements if tag == "source"]
            images = [attrs for tag, attrs in parsed.elements if tag == "img"]
            self.assertEqual(sources, [{"media": "(prefers-color-scheme: dark)", "srcset": f"assets/cards/{name}-dark.png"}])
            self.assertEqual(len(images), 1)
            self.assertEqual(images[0]["src"], f"assets/cards/{name}-light.png")
            self.assertTrue(images[0].get("alt", "").strip())

    def test_ruling_is_recorded_result_not_a_fixed_verdict(self):
        records = cards.read_json(self.root / INPUTS[2])
        fail = next(record for record in records if record["verdict"] == "fail")
        self.run_builder()
        text = " ".join(Structure(self.content("ruling.html")).text)
        self.assertNotIn("The ruling", self.content("ruling.html"))
        self.assertIn('<main>\n<section class="terminal"', self.content("ruling.html"))
        self.assertIn('<h1 class="label">RECORDED OUTPUT / HTML ONLY</h1>', self.content("ruling.html"))
        self.assertIn("FAIL", text)
        self.assertIn("exit=1", text)
        for entry in fail["html"]:
            self.assertIn(entry["input"], text)
            self.assertIn(f'"errors": {entry["errors"]}', text)
        passed = next(record for record in records if record["verdict"] == "pass")
        self.write(INPUTS[2], [passed])
        self.run_builder()
        self.assertIn("PASS", self.content("ruling.html"))
        self.assertIn("exit=0", self.content("ruling.html"))

    def test_numbers_percentages_ranges_and_baseline_bars(self):
        data = self.fixture()
        self.write("evals/results/summary.json", data)
        self.run_builder()
        html = self.content("numbers.html")
        parsed = Structure(html)
        self.assertIn(data["model"], " ".join(parsed.text))
        self.assertIn("&lt;not a benchmark&gt;", html)
        self.assertIn("Same agent, same 2 tasks, 3 runs each.", html)
        self.assertIn("2 synthetic tasks, one model, one machine; lines measure size, not quality.", html)
        sections = re.findall(r'<section class="metric"[^>]*>(.*?)</section>', html, re.S)
        self.assertEqual(len(sections), 4)
        for section, change, share, ranges in zip(
            sections, ("−50", "−25", "+50", "−100"), ("50.00", "75.00", "150.00", "0.00"),
            (("40–60", "80–120"), ("24–36", "32–48"), ("4–8", "2–6"), ("0–0", "1–3")),
        ):
            self.assertIn(f">{change}\u2009%</p>", section)
            self.assertIn('class="bar without" style="width: 100.00%"', section)
            self.assertIn(f'class="bar with" style="width: {share}%"', section)
            self.assertIn(f">{float(share):.0f}\u2009%</span>", section)
            for span in ranges:
                self.assertIn(f"range {span}", section)
            tracks = [attrs for _, attrs in Structure(section).elements if attrs.get("class") == "track"]
            self.assertEqual(len(tracks), 2)
            self.assertTrue(all(attrs.get("aria-hidden") == "true" for attrs in tracks))
            if share == "150.00":
                self.assertTrue(all(attrs.get("style") == "width: 66.67%; overflow: visible" for attrs in tracks))
        self.assertNotIn('id="nu_errors"', html)

    def test_numbers_visible_percentages_are_integers(self):
        data = cards.read_json(ROOT / "evals/results/summary.json")
        self.write("evals/results/summary.json", data)
        self.run_builder()
        for theme in THEMES:
            html = (self.output / f"numbers-{theme}.html").read_text(encoding="utf-8")
            visible = " ".join(Structure(html).text)
            self.assertNotRegex(visible, r"\d+\.\d+\s*%")
            self.assertEqual(len(re.findall(r"[−+]?\d+\s*%", visible)), 12)
            self.assertIn("59\u2009%", visible)
            self.assertIn("−41\u2009%", visible)

    def test_numbers_height_is_below_620_from_layout_budget(self):
        self.write("evals/results/summary.json", self.fixture())
        self.run_builder()
        for theme in THEMES:
            html = (self.output / f"numbers-{theme}.html").read_text(encoding="utf-8")
            css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)

            def declaration(selector, name):
                rules = re.findall(re.escape(selector) + r"\s*\{([^}]*)\}", css)
                values = [match.group(1).strip() for rule in rules
                          if (match := re.search(r"(?:^|;)\s*" + re.escape(name) + r":\s*([^;]+)", rule))]
                self.assertTrue(values, (selector, name))
                return values[-1]

            def pixels(selector, name):
                value = declaration(selector, name)
                self.assertRegex(value, r"^\d+px$")
                return int(value[:-2])

            metric_count = len(re.findall(r'<section class="metric"', html))
            self.assertEqual(metric_count, 4)
            margin = declaration(".benchmark h1", "margin").split()
            self.assertEqual(margin[1], "0")
            border = int(declaration("main", "border").split("px", 1)[0])
            height = (2 * pixels(".benchmark main", "padding") + 2 * border
                      + pixels(".benchmark .label", "height")
                      + pixels(".benchmark h1", "height")
                      + int(margin[0][:-2]) + int(margin[2][:-2])
                      + metric_count * pixels(".metric", "height")
                      + pixels(".benchmark .nu-line", "margin-top")
                      + pixels(".benchmark .nu-line", "height")
                      + pixels(".benchmark footer", "margin-top")
                      + pixels(".benchmark footer", "height"))
            self.assertLess(height, 620, f"numbers CSS height: {height}px")
            self.assertEqual(declaration(".metric", "display"), "grid")
            self.assertEqual(declaration(".metric h2", "grid-row"), "1")
            self.assertEqual(declaration(".metric-bars", "grid-row"), "1")
            self.assertEqual(declaration(".metric .display", "grid-column"), "3")
            self.assertEqual(declaration(".metric-ranges", "grid-row"), "2")
            self.assertGreaterEqual(pixels(".metric", "height"),
                                    2 * pixels(".bar-row", "height")
                                    + 2 * pixels(".metric .direction", "line-height") + 4)
            self.assertGreaterEqual(pixels(".benchmark footer", "height"),
                                    3 * pixels(".benchmark footer", "line-height"))
            self.assertNotRegex(css, r"(?:\.benchmark[^{}]*|\.metric[^{}]*)\{[^}]*overflow\s*:\s*(?:hidden|clip)")

    def test_social_benchmark_summary_is_computed_from_supplied_data(self):
        self.write("evals/results/summary.json", self.fixture())
        self.run_builder()
        social = self.content("social.html")
        self.assertIn("−25% JavaScript · −100% axe violations · 3 runs", social)
        self.assertNotIn("−41% JavaScript", social)
        data = cards.read_json(ROOT / "evals/results/summary.json")
        self.write("evals/results/summary.json", data)
        self.run_builder()
        self.assertIn("−41% JavaScript · −76% axe violations · 5 runs", self.content("social.html"))

    def test_social_zero_baseline_does_not_invent_percentage(self):
        data = self.fixture()
        data["arms"]["without"]["js_lines"] = {"mean": 0, "min": 0, "max": 0, "runs": [0]}
        self.write("evals/results/summary.json", data)
        self.run_builder()
        self.assertIn("not measured JavaScript", self.content("social.html"))

    def test_nu_page_line_is_visible_and_calculated_from_fixture(self):
        data = self.fixture()
        data["arms"]["with"].update(pages=9, pages_with_nu_errors=4)
        data["arms"]["without"].update(pages=12, pages_with_nu_errors=2)
        html = cards.numbers_card(cards.validate_summary(data))
        line = "Nu errors: 4 of 9 pages with divorce, 2 of 12 without"
        self.assertIn(line, html.split("<footer>")[0])
        self.assertRegex(html, r'<p[^>]*>' + re.escape(line) + r'</p>')
        self.assertNotIn("<details", html)

    def test_real_summary_numbers_and_nu_pages(self):
        data = cards.read_json(ROOT / "evals/results/summary.json")
        self.write("evals/results/summary.json", data)
        self.run_builder()
        html = self.content("numbers.html")
        for percent in ("−29", "−41", "−33", "−76"):
            self.assertIn(f">{percent}\u2009%</p>", html)
        self.assertIn("Nu errors: 3 of 40 pages with divorce, 0 of 40 without", html)

    def test_zero_baseline_has_no_bar_but_retains_means_and_ranges(self):
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
        self.assertIn("with divorce: mean 50.0; range 40–60", html)
        self.assertIn("without divorce: mean 0; range 0–0", html)

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
        self.assertIn("--bg: #0b0b0c", cards.CSS)
        self.assertIn("--red: #ff4d4d", cards.CSS)
        self.assertIn("--green: #3ddc84", cards.CSS)

        def luminance(color):
            channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            channels = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
            return sum(v * weight for v, weight in zip(channels, (.2126, .7152, .0722)))

        def ratio(foreground, background):
            light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
            return (light + .05) / (dark + .05)

        for background in ("#0b0b0c", "#141416"):
            for foreground in ("#f4f4f5", "#9a9aa2", "#3ddc84"):
                self.assertGreaterEqual(ratio(foreground, background), 4.5)
            self.assertGreaterEqual(ratio("#ff4d4d", background), 4.5)


if __name__ == "__main__":
    unittest.main()
