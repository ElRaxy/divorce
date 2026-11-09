import ast
from html.parser import HTMLParser
import importlib.util
from pathlib import Path
import re
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("build_cards", ROOT / "assets/cards/build_cards.py")
cards = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cards)
NAMES = ["banner.html", "social.html"]
PALETTE = {"#f6f3ec", "#1b1a17", "#d8432f", "#6b665c"}


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def declarations(html, selector):
    result = {}
    for block in re.findall(re.escape(selector) + r"\s*\{([^}]*)\}", html):
        for entry in block.split(";"):
            if ":" in entry:
                name, value = entry.split(":", 1)
                result[name.strip()] = value.strip()
    return result


class BuildCardsTest(unittest.TestCase):
    def test_only_two_html_files_and_deterministic_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(cards.build(root), NAMES)
            output = root / "assets/cards/html"
            first = {p.name: p.read_bytes() for p in output.iterdir()}
            self.assertEqual(sorted(first), NAMES)
            cards.build(root)
            self.assertEqual(first, {p.name: p.read_bytes() for p in output.iterdir()})
            alternate = root / "alternate"
            cards.build(root, alternate)
            self.assertEqual(first, {p.name: p.read_bytes() for p in alternate.iterdir()})
            self.assertEqual(sorted(p.name for p in (ROOT / "assets/cards/html").iterdir()), NAMES)
            for name, contents in first.items():
                self.assertEqual(contents, (ROOT / "assets/cards/html" / name).read_bytes())
            self.assertFalse(list(root.rglob("*.png")))
            for name in ("hero", "numbers", "cases", "ladder", "ruling"):
                self.assertFalse((ROOT / "assets/cards" / (name + ".png")).exists())

    def test_literal_composition_and_social_dimensions(self):
        for social, width, height, mascot, title in (
            (False, "880px", "400px", "300px", "76px"),
            (True, "1280px", "640px", "420px", "108px"),
        ):
            with self.subTest(social=social):
                html = cards.document(social)
                body = declarations(html, "body")
                self.assertEqual((body["width"], body["height"]), (width, height))
                self.assertEqual(body["background"], "#f6f3ec")
                grid = declarations(html, ".b")
                self.assertEqual(grid["grid-template-columns"], mascot + " 1fr")
                self.assertEqual(grid["align-items"], "center")
                self.assertEqual(declarations(html, "img")["width"], mascot)
                heading = declarations(html, "h1")
                self.assertEqual(heading["font"], '400 76px/0.95 "Instrument Serif", serif')
                self.assertEqual(heading.get("font-size", "76px"), title)
                self.assertEqual(heading["letter-spacing"], "-0.02em")
                self.assertEqual(heading["color"], "#1b1a17")
                self.assertEqual(declarations(html, "h1 em")["color"], "#d8432f")
                footer = declarations(html, "p")
                self.assertEqual(footer["font"], "500 15px/1.5 Geist, sans-serif")
                self.assertEqual(footer["color"], "#6b665c")
                self.assertIn('<h1>Native first.<br><em>Then proven.</em></h1>', html)
                self.assertIn('<p><b>divorce</b> &nbsp;·&nbsp; a skill for Claude Code and Codex</p>', html)
                parsed = Elements(html)
                self.assertEqual([attrs for tag, attrs in parsed.tags if tag == "img"],
                                 [{"src": "../../mascot.png", "alt": ""}])
                self.assertEqual([attrs for tag, attrs in parsed.tags if tag == "html"], [{"lang": "en"}])
                self.assertFalse(any(tag in ("script", "link", "svg") for tag, _ in parsed.tags))
                if not social:
                    self.assertEqual(grid["padding"], "44px 64px 44px 40px")
                    self.assertEqual(grid["height"], "312px")
                    self.assertEqual(grid["gap"], "8px")
                    self.assertEqual(heading["margin"], "0 0 22px")

    def test_local_font_faces_and_closed_palette(self):
        expected = {
            ("Instrument Serif", "400", "normal", "instrument-serif-latin-400-normal.woff2"),
            ("Instrument Serif", "400", "italic", "instrument-serif-latin-400-italic.woff2"),
            ("Geist", "500", "normal", "geist-sans-latin-500-normal.woff2"),
        }
        for name in NAMES:
            html = (ROOT / "assets/cards/html" / name).read_text()
            with self.subTest(name=name):
                faces = set()
                blocks = re.findall(r"@font-face\s*\{([^}]*)\}", html)
                self.assertEqual(len(blocks), 3)
                for block in blocks:
                    family = re.search(r"font-family: '([^']+)'", block).group(1)
                    weight = re.search(r"font-weight: (\d+)", block).group(1)
                    style = re.search(r"font-style: (\w+)", block).group(1)
                    url = re.search(r'url\("([^"]+)"\)', block).group(1)
                    self.assertTrue(url.startswith("../../fonts/"))
                    self.assertTrue((ROOT / "assets/cards/html" / url).is_file())
                    faces.add((family, weight, style, Path(url).name))
                self.assertEqual(faces, expected)
                self.assertNotRegex(html, r"https?://|@import|data:")
                colors = re.findall(r"#[0-9a-fA-F]+|rgba?\([^)]*\)|hsla?\([^)]*\)", html)
                self.assertEqual(set(colors), PALETTE)
                values = re.findall(r"(?:color|background(?:-color)?):\s*([^;]+);", html)
                self.assertTrue(all(value in PALETTE for value in values), values)

    def test_all_remaining_fonts_are_used_by_repo_html(self):
        html = "\n".join(p.read_text() for p in ROOT.rglob("*.html"))
        for font in (ROOT / "assets/fonts").glob("*.woff2"):
            self.assertIn(font.name, html)
        notice = (ROOT / "NOTICE").read_text()
        self.assertRegex(notice, r"Instrument Serif .*Open Font License 1\.1.*assets/fonts/OFL-InstrumentSerif.txt")
        self.assertTrue((ROOT / "assets/fonts/OFL-InstrumentSerif.txt").is_file())

    def test_builder_imports_only_stdlib(self):
        modules = set()
        for node in ast.walk(ast.parse((ROOT / "assets/cards/build_cards.py").read_text())):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add(node.module)
        self.assertLessEqual(modules, {"argparse", "datetime", "json", "pathlib"})


class ReadmeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / "README.md").read_text()
        cls.readme = re.sub(r"<!--.*?-->", "", cls.raw, flags=re.S)

    def section(self, title):
        return self.readme.split("## " + title + "\n", 1)[1].split("\n## ", 1)[0]

    def test_numbers_table_and_sentence_recomputed_from_summary(self):
        data = cards.validate_summary(cards.read_json(ROOT / "evals/results/summary.json"))
        section = self.section("Numbers")
        rows = [line for line in section.splitlines() if line.startswith("|")]
        expected = [cards.percentage_change(data, metric) for metric, _ in cards.METRICS if metric != "nu_errors"]
        self.assertEqual(rows, ["|  | HTML | JavaScript | ARIA | axe violations |",
                                "| --- | :---: | :---: | :---: | :---: |",
                                "| **With divorce** | " + " | ".join(expected) + " |"])
        current, baseline = data["arms"]["with"], data["arms"]["without"]
        sentence = (f'Over {data["runs_per_case"]} runs of {data["cases"]} tasks. Nu errors: '
                    f'{current["pages_with_nu_errors"]} of {current["pages"]} pages with divorce, '
                    f'{baseline["pages_with_nu_errors"]} of {baseline["pages"]} without. '
                    'Method and limits in [evals](evals/README.md).')
        self.assertIn(sentence, section)

    def test_cases_match_both_json_files_and_undetected_come_first(self):
        manifest = cards.read_json(ROOT / "examples/manifest.json")
        measured = cards.read_json(ROOT / "examples/axe-measured.json")
        rows, caught, missed = cards.evidence(manifest, measured)
        ordered = sorted(rows, key=lambda row: (bool(row["tools"]), row["id"]))
        expected = []
        for row in ordered:
            nu = "flags it" if row["before_html"] == "fail" else "—"
            impacts = sorted({violation["impact"] for violation in measured["cases"][row["id"]]["before"]})
            axe = "flags it (" + ", ".join(impacts) + ")" if impacts else "—"
            expected.append(f'| [{row["title"]}](examples/{row["id"]}/) | {nu} | {axe} |')
        section = self.section("What validators miss")
        actual = [line for line in section.splitlines() if line.startswith("|")]
        self.assertEqual(actual, ["| Case | Nu | axe |", "| --- | --- | --- |"] + expected)
        self.assertEqual(len(rows), 9)
        self.assertEqual(caught + missed, 9)
        self.assertIn(f"{missed} of 9 pass both checkers. divorce picks the element before anything is checked.", section)

    def test_code_samples_are_literal_example_lines(self):
        section = self.section("What validators miss")
        expected = []
        for side in ("before", "after"):
            source = (ROOT / f"examples/div-button/{side}.html").read_text()
            expected.append(next(line.strip() for line in source.splitlines() if ">Save</" in line))
        self.assertEqual(re.findall(r"```html\n(.*?)\n```", section, re.S), expected)
        self.assertRegex(section, r"Without divorce:\s*```html")
        self.assertRegex(section, r"With divorce:\s*```html")
        self.assertIn("Both of these pass the Nu HTML Checker and axe. Only one can be reached with Tab.", section)

    def test_literal_ladder_and_gate_explanation(self):
        section = self.section("How it works")
        items = re.findall(r"^\d+\. (.*)$", section, re.M)
        plain = [item.replace("**", "") for item in items]
        self.assertEqual(plain, [question + (" " + answer if answer else "") for question, answer in cards.LADDER])
        self.assertIn("Then the gate checks the result: Nu on the HTML, axe on the rendered page. "
                      "Code, not the model, delivers the verdict: `pass`, `fail` or `not_measured` ([exit codes](#details)).", section)

    def test_readme_order_limits_header_quote_install_and_evidence(self):
        self.assertLess(len(self.raw.splitlines()), 170)
        self.assertEqual(re.findall(r"^## (.*)$", self.readme, re.M),
                         ["Install", "Numbers", "What validators miss", "How it works", "Details", "Star History", "License"])
        self.assertTrue(self.readme.startswith('<p align="center"><img src="assets/cards/banner.png" width="880" '
                                              'alt="divorce. Native first. Then proven. A skill for Claude Code and Codex."></p>\n'))
        self.assertIn("<em>End your agent's toxic relationship with div soup.</em>", self.readme)
        self.assertIn("<b>5 of 9 accessibility bugs pass both Nu and axe.</b>", self.readme)
        rows, _, missed = cards.evidence(cards.read_json(ROOT / "examples/manifest.json"),
                                         cards.read_json(ROOT / "examples/axe-measured.json"))
        self.assertIn(f"<b>{missed} of {len(rows)} accessibility bugs pass both Nu and axe.</b>", self.readme)
        self.assertLess(self.readme.index('src="assets/demo/tab.gif"'), self.readme.index("## Install"))
        self.assertIn("```sh\nnpx skills add ElRaxy/divorce\n```", self.section("Install"))
        quote = ("> Your agent writes `<div onclick>`. Every validator says it's fine. Someone using a keyboard can't reach it.\n>\n"
                 "> **divorce** makes the agent pick the native element first, then proves it with Nu and axe.")
        self.assertIn(quote, self.readme)
        self.assertLess(self.readme.index(quote), self.readme.index("## Install"))
        parsed = Elements(self.readme)
        local = [attrs["src"] for tag, attrs in parsed.tags if tag == "img" and not attrs["src"].startswith("https://")]
        self.assertEqual(local, ["assets/cards/banner.png", "assets/demo/tab.gif"])
        self.assertFalse(any(tag == "sub" for tag, _ in parsed.tags))
        self.assertNotRegex(self.readme, r"!\[")
        self.assertIn("```text\n/plugin marketplace add ElRaxy/divorce\n/plugin install divorce@divorce\n```", self.section("Install"))
        self.assertIn("Other agents and install routes: [Details](#details).", self.section("Install"))
        self.assertEqual(self.readme.count("<details>"), 1)
        evidence = self.section("Details").split("<h3>Evidence</h3>", 1)[1].split("<h3>Install</h3>", 1)[0]
        bullets = [line for line in evidence.splitlines() if line.startswith("- ")]
        self.assertEqual(len(bullets), 4)
        self.assertEqual(bullets[-1], '- <a href="assets/demo/replay.gif">Two recorded runs</a> of the same modal task, same prompt and model.')
        self.assertIn("api.star-history.com/svg?repos=ElRaxy/divorce", self.readme)


if __name__ == "__main__":
    unittest.main()
