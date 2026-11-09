#!/usr/bin/env python3
"""Build deterministic HTML cards from recorded evidence. No browser required."""

import argparse
from datetime import date
from html import escape
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NEWLINE = "\n"
METRICS = (
    ("html_lines", "HTML lines"),
    ("js_lines", "JavaScript lines"),
    ("aria_attributes", "ARIA attributes"),
    ("axe_violation_nodes", "axe violations"),
    ("nu_errors", "Nu errors"),
)
LADDER = (
    ("Does it need to exist?", "If not, omit it."),
    ("Does the project already have it?", "Reuse it."),
    ("Is there a native HTML element for it?", "Use it."),
    ("Can CSS do it without JavaScript?", None),
    ("Does an installed dependency cover it?", None),
    ("Only then:", "the smallest code that works, plus a small test for logic."),
)
MASCOT = '<img class="mascot" src="../../mascot.png" width="160" height="160" alt="A weary div character in round glasses signs separation papers with a red pen.">'
CSS = """@font-face { font-family: 'Geist'; font-weight: 400;
  font-style: normal; font-display: block;
  src: url("../../fonts/geist-sans-latin-400-normal.woff2") format("woff2"); }
@font-face { font-family: 'Geist'; font-weight: 500;
  font-style: normal; font-display: block;
  src: url("../../fonts/geist-sans-latin-500-normal.woff2") format("woff2"); }
@font-face { font-family: 'Geist'; font-weight: 600;
  font-style: normal; font-display: block;
  src: url("../../fonts/geist-sans-latin-600-normal.woff2") format("woff2"); }
@font-face { font-family: 'Geist'; font-weight: 700;
  font-style: normal; font-display: block;
  src: url("../../fonts/geist-sans-latin-700-normal.woff2") format("woff2"); }
@font-face { font-family: 'Geist Mono'; font-weight: 400;
  font-style: normal; font-display: block;
  src: url("../../fonts/geist-mono-latin-400-normal.woff2") format("woff2"); }
@font-face { font-family: 'Geist Mono'; font-weight: 500;
  font-style: normal; font-display: block;
  src: url("../../fonts/geist-mono-latin-500-normal.woff2") format("woff2"); }
:root { color-scheme: dark; --bg: #0d1117; --surface: #161b22; --surface-2: #1c2128;
  --hairline: rgba(240,246,252,0.08); --text: #f5f5f7; --text-2: #a1a1a6;
  --text-3: #86868b; --green: #30d158; --red: #ff453a;
  --red-tint: rgba(255,69,58,0.12); --green-tint: rgba(48,209,88,0.12); }
* { box-sizing: border-box; }
html { background: var(--bg); }
body { width: 880px; margin: 0; background: var(--bg); color: var(--text);
  font: 400 17px/1.45 'Geist', sans-serif; letter-spacing: 0; text-align: center; }
main { padding: 72px 64px; background: var(--bg); display: grid; gap: 40px; }
h1, h2, p { margin: 0; }
h1 { font-size: 40px; line-height: 1.08; letter-spacing: -0.03em; font-weight: 700; }
h2, .subtitle { font-size: 20px; line-height: 1.35; letter-spacing: -0.01em; font-weight: 500; }
code { font: 400 15px/1.5 'Geist Mono', monospace; letter-spacing: 0; }
.display { font-size: 56px; line-height: 1.04; letter-spacing: -0.035em; font-weight: 700; }
.figure { font-size: 64px; line-height: 1; letter-spacing: -0.045em; font-weight: 700;
  font-variant-numeric: tabular-nums; }
.label { color: #86868b; font-size: 13px; line-height: 1.2; letter-spacing: 0.08em;
  font-weight: 600; text-transform: uppercase; }
header { display: grid; gap: 16px; }
.secondary { color: var(--text-2); }
.quiet, footer { color: var(--text-3); }
.red { color: var(--red); }
.green { color: var(--green); }
.surface { background: var(--surface); border: 1px solid var(--hairline); border-radius: 20px; }
.pair { display: grid; grid-template-columns: repeat(2, 340px); gap: 16px; justify-content: center; }
.sample { padding: 32px; display: grid; gap: 16px; }
.sample code { font-size: 26px; }
.sample p { color: var(--text-2); }
.metric-grid { display: grid; grid-template-columns: repeat(2, 360px); gap: 16px; justify-content: center; }
.metric { height: 180px; display: flex; flex-direction: column; align-items: center;
  justify-content: center; gap: 16px; }
.metric code { color: #86868b; }
.nu-line { color: var(--text-2); }
.nu-line::before { content: ''; display: inline-block; width: 8px; height: 8px;
  margin-right: 8px; border-radius: 50%; background: var(--red); vertical-align: middle; }
.case-grid { display: grid; grid-template-columns: repeat(3, 240px); gap: 12px;
  justify-content: center; margin: 0; padding: 0; list-style: none; }
.case { height: 88px; border-radius: 16px; display: flex; flex-direction: column;
  justify-content: center; gap: 16px; background: var(--surface); border: 1px solid var(--hairline); }
.case.missed { background: var(--red-tint); border: 0; }
.detector { color: #86868b; font-size: 13px; line-height: 1.2; }
.missed .detector { color: var(--red); }
.terminal { width: 640px; margin-inline: auto; padding: 32px; display: grid; gap: 40px; }
.command { color: var(--text-2); }
.status { display: flex; justify-content: center; align-items: baseline; gap: 16px; }
.status code { color: #86868b; }
.gate-facts { display: flex; justify-content: center; gap: 40px; margin: 0; }
.gate-facts div { display: grid; gap: 16px; }
.gate-facts dd { margin: 0; }
.social { width: 1280px; height: 640px; text-align: left; }
.social main { height: 640px; grid-template-columns: 360px 1fr; align-items: center; }
.social .mascot { display: block; width: 360px; height: 360px; object-fit: contain; }
.social-copy { display: grid; gap: 40px; }
.wordmark { font-size: 72px; line-height: 1.04; letter-spacing: -0.035em; }
"""
CARD_CSS = """main { padding: 56px 64px; }
.sample code { justify-self: center; border-radius: 10px; outline-offset: 8px; }
.sample code.red { outline: 1.5px dashed var(--text-3); }
.sample code.green { outline: 2px solid var(--green); }
.sample p { color: var(--text-3); }
.sample p.green { color: var(--green); }
kbd { font: 400 13px/1.5 'Geist Mono', monospace; color: var(--text-3);
  background: var(--surface-2); border: 1px solid var(--hairline); border-radius: 6px; padding: 2px 8px; }
.ladder-list { width: 600px; margin: 0 auto; padding: 0; list-style: none; text-align: left; }
.ladder-list li { display: grid; grid-template-columns: 32px 1fr; gap: 16px; padding: 24px 0; }
.ladder-list li + li { border-top: 1px solid var(--hairline); }
.rung-number { font: 400 15px/1.5 'Geist Mono', monospace; color: var(--text-3); }
.rung-copy { display: grid; gap: 8px; }
.rung-copy h2 { color: var(--text); }
.rung-copy p { color: var(--text-2); }
"""


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def evidence(manifest, measured):
    rows = []
    for case in sorted(manifest["cases"], key=lambda item: item["id"]):
        before = measured["cases"][case["id"]]["before"]
        tools = (["Nu"] if case["before_html"] == "fail" else [])
        if before:
            tools.append("axe")
        rows.append({**case, "tools": tools, "violations": before})
    caught = sum(bool(row["tools"]) for row in rows)
    return rows, caught, len(rows) - caught


def document(title, body, kind=""):
    css = CSS if kind == "social" else CSS + CARD_CSS
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{css}</style>
</head>
<body class="{kind}">
<main>
{body}
</main>
</body>
</html>
'''


def comparison(case, measured):
    panels = []
    for code, color, state, role in (
        ("<div onclick>", "red", "skipped", "no role"),
        ("<button>", "green", "focused", "button role"),
    ):
        panels.append(f'''<div class="surface sample">
<code class="{color}">{escape(code)}</code>
<p class="{'green' if state == 'focused' else 'quiet'}"><kbd>Tab</kbd> → {state}</p>
<p>{role}</p>
</div>''')
    return '<div class="pair">' + "\n".join(panels) + '</div>'


def hero(rows, caught, missed, measured, social=False, summary=None):
    first = f"Validators catch {caught} of {len(rows)}."
    second = f"The other {missed} look fine."
    if social:
        body = f'''{MASCOT}
<div class="social-copy"><header><h1 class="wordmark">divorce</h1>
<p class="subtitle secondary">End your agent's toxic relationship with div soup.</p></header>
<p class="quiet">{escape(first)} {escape(second)}</p></div>'''
    else:
        case = next(row for row in rows if row["id"] == "div-button")
        passed = all(case[side + "_html"] == "pass" and not measured["cases"][case["id"]][side]
                     for side in ("before", "after"))
        if passed:
            fact = "Both pass Nu and axe."
        else:
            fact = " · ".join(
                f'{side.capitalize()}: Nu {case[side + "_html"]}, '
                f'axe {len(measured["cases"][case["id"]][side])} violations'
                for side in ("before", "after")) + "."
        body = f'''<header><p class="label">THE PROBLEM</p>
<h1 class="display">{escape(first)}<br><span class="secondary">{escape(second)}</span></h1></header>
{comparison(case, measured)}
<footer>{escape(fact)}</footer>'''
    return document("divorce — native HTML, measured evidence", body, "social" if social else "hero")


def cases_card(rows, missed, measured):
    cells = []
    ordered = sorted(rows, key=lambda row: (bool(row["tools"]), row["id"]))
    for row in ordered:
        detector = " + ".join(row["tools"]) if row["tools"] else "no tool flags it"
        kind = "case" if row["tools"] else "case missed"
        cells.append(f'''<li class="{kind}"><code>{escape(row["id"])}</code>
<span class="detector">{escape(detector)}</span></li>''')
    body = f'''<header><h1><span class="red">{missed} of {len(rows)}</span> are invisible to every tool.</h1>
<p class="subtitle secondary">Nu and axe pass them. A person with a keyboard does not.</p></header>
<ul class="case-grid">{NEWLINE.join(cells)}</ul>'''
    return document("divorce — the evidence", body, "cases")


def ladder_card():
    rows = []
    for number, (question, answer) in enumerate(LADDER, 1):
        response = f'<p>{escape(answer)}</p>' if answer is not None else ""
        rows.append(f'''<li><span class="rung-number">{number:02d}</span>
<div class="rung-copy"><h2>{escape(question)}</h2>{response}</div></li>''')
    body = f'''<header><p class="label">HOW IT WORKS</p>
<h1>Stop at the first rung that holds.</h1></header>
<ol class="ladder-list">{NEWLINE.join(rows)}</ol>'''
    return document("divorce — how it works", body, "ladder")


def ruling_card(records):
    record = next((item for item in records if item["verdict"] == "fail"), records[0])
    verdict = record["verdict"]
    code = {"pass": 0, "fail": 1, "not_measured": 2}[verdict]
    command = "$ gate.py html " + " ".join("/".join(Path(entry["input"]).parts[-2:])
                                          for entry in record["html"])
    counts = {}
    for key in ("errors", "warnings"):
        values = [entry[key] for entry in record["html"]]
        counts[key] = sum(values) if values and all(type(value) is int for value in values) else "not_measured"
    reason = ", ".join(record["reasons"]) or "none"
    color = "green" if verdict == "pass" else "red"
    body = f'''<h1>Code delivers the verdict.</h1>
<div class="surface terminal">
<p class="command"><code>{escape(command)}</code></p>
<div class="status"><p class="figure {color}">{escape(verdict.upper())}</p><code>exit {code}</code></div>
<dl class="gate-facts">
<div><dt class="label">NU ERRORS</dt><dd><code>{counts["errors"]}</code></dd></div>
<div><dt class="label">WARNINGS</dt><dd><code>{counts["warnings"]}</code></dd></div>
<div><dt class="label">REASON</dt><dd><code>{escape(reason)}</code></dd></div>
</dl></div>
<footer>Missing evidence is <code>not_measured</code>, never a pass.</footer>'''
    return document("divorce — recorded gate output", body, "ruling")


def validate_summary(data):
    if not isinstance(data, dict):
        raise ValueError("summary must be an object")
    try:
        if date.fromisoformat(data["date"]).isoformat() != data["date"]:
            raise ValueError("date must use YYYY-MM-DD")
        if not isinstance(data["model"], str) or not data["model"].strip():
            raise ValueError("model must be a non-empty string")
        for key in ("runs_per_case", "cases"):
            if type(data[key]) is not int or data[key] < 1:
                raise ValueError(f"{key} must be a positive integer")
        for arm in ("with", "without"):
            values = data["arms"][arm]
            for metric, _ in METRICS:
                value = values[metric]
                if not isinstance(value, dict):
                    raise ValueError(f"arms.{arm}.{metric} must be an object")
                runs = value["runs"]
                if (not isinstance(runs, list) or not runs
                        or any(type(run) is not int or run < 0 for run in runs)):
                    raise ValueError(f"arms.{arm}.{metric}.runs must contain non-negative integers")
                low, mean, high = value["min"], value["mean"], value["max"]
                if (type(low) is not int or type(high) is not int
                        or type(mean) not in (int, float)
                        or not 0 <= low <= mean <= high
                        or low != min(runs) or high != max(runs)):
                    raise ValueError(f"arms.{arm}.{metric} has inconsistent statistics")
            for key in ("pages", "pages_with_nu_errors", "pages_with_axe_violations"):
                if type(values[key]) is not int or values[key] < 0:
                    raise ValueError(f"arms.{arm}.{key} must be a non-negative integer")
                if key != "pages" and values[key] > values["pages"]:
                    raise ValueError(f"arms.{arm}.{key} exceeds pages")
    except (KeyError, TypeError) as error:
        raise ValueError(f"invalid or missing summary field: {error}") from error
    return data


def percentage_change(data, metric):
    baseline = data["arms"]["without"][metric]["mean"]
    if not baseline:
        return "not measured"
    change = round((data["arms"]["with"][metric]["mean"] / baseline - 1) * 100)
    return (f"{change:+d}".replace("-", "−") if change else "0") + "%"


def numbers_card(data):
    groups = []
    for metric, label in METRICS:
        if metric == "nu_errors":
            continue
        baseline = data["arms"]["without"][metric]["mean"]
        current = data["arms"]["with"][metric]["mean"]
        if baseline:
            percent = percentage_change(data, metric)
            delta = f'<p class="figure green">{percent}</p>'
        else:
            delta = '<p class="secondary">No percentage: baseline is zero.</p>'
        groups.append(f'''<section class="surface metric" id="{metric}">{delta}
<h2>{label}</h2><code>{round(baseline)} → {round(current)}</code></section>''')
    with_arm, without_arm = data["arms"]["with"], data["arms"]["without"]
    body = f'''<header><p class="label">WITH VS. WITHOUT DIVORCE</p>
<h1>Same agent. Same {data["cases"]} tasks. {data["runs_per_case"]} runs each.</h1></header>
<div class="metric-grid">{NEWLINE.join(groups)}</div>
<p class="nu-line">Nu errors: {with_arm["pages_with_nu_errors"]} of {with_arm["pages"]} pages with divorce, {without_arm["pages_with_nu_errors"]} of {without_arm["pages"]} without.</p>'''
    return document("divorce — measured numbers", body, "benchmark")


def build(root=ROOT, out_dir=None):
    root = Path(root)
    out_dir = Path(out_dir) if out_dir is not None else root / "assets/cards/html"
    manifest = read_json(root / "examples/manifest.json")
    measured = read_json(root / "examples/axe-measured.json")
    records = read_json(root / "assets/data/gate-real.json")
    rows, caught, missed = evidence(manifest, measured)
    summary = root / "evals/results/summary.json"
    data = validate_summary(read_json(summary)) if summary.exists() else None
    pages = {"hero.html": hero(rows, caught, missed, measured),
             "cases.html": cases_card(rows, missed, measured),
             "ladder.html": ladder_card(),
             "ruling.html": ruling_card(records),
             "social.html": hero(rows, caught, missed, measured, social=True, summary=data)}
    if data is not None:
        pages["numbers.html"] = numbers_card(data)
    out_dir.mkdir(parents=True, exist_ok=True)
    obsolete = {f"{name}-{theme}.html" for name in ("hero", "cases", "ruling", "numbers", "social", "ladder")
                for theme in ("light", "dark")} | ({"numbers.html"} - pages.keys())
    for name in sorted(obsolete):
        (out_dir / name).unlink(missing_ok=True)
    for name, content in sorted(pages.items()):
        (out_dir / name).write_bytes(content.encode("utf-8"))
    return sorted(pages)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Project root containing the evidence files")
    parser.add_argument("--out-dir", type=Path, help="Default: assets/cards/html under the project root")
    args = parser.parse_args()
    try:
        names = build(args.root, args.out_dir)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    print("Built " + ", ".join(names))


if __name__ == "__main__":
    main()
