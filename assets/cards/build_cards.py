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
    ("html_lines", "HTML"),
    ("js_lines", "JS"),
    ("aria_attributes", "ARIA"),
    ("axe_violation_nodes", "axe"),
    ("nu_errors", "Nu errors"),
)
IMPACTS = ("minor", "moderate", "serious", "critical")
MASCOT = '<img class="mascot" src="../../mascot.png" width="160" height="160" alt="A weary div character in round glasses signs separation papers with a red pen.">'
CSS = """@font-face { font-family: 'Bricolage Grotesque'; font-weight: 700;
  font-style: normal; font-display: block;
  src: url("../../fonts/bricolage-grotesque-latin-700-normal.woff2") format("woff2"); }
@font-face { font-family: 'Bricolage Grotesque'; font-weight: 800;
  font-style: normal; font-display: block;
  src: url("../../fonts/bricolage-grotesque-latin-800-normal.woff2") format("woff2"); }
@font-face { font-family: 'JetBrains Mono'; font-weight: 400;
  font-style: normal; font-display: block;
  src: url("../../fonts/jetbrains-mono-latin-400-normal.woff2") format("woff2"); }
@font-face { font-family: 'JetBrains Mono'; font-weight: 700;
  font-style: normal; font-display: block;
  src: url("../../fonts/jetbrains-mono-latin-700-normal.woff2") format("woff2"); }
:root { color-scheme: dark; --bg: #0b0b0c; --card: #141416; --line: #26262a;
  --text: #f4f4f5; --muted: #9a9aa2; --red: #ff4d4d; --green: #3ddc84; }
* { box-sizing: border-box; }
html { background: var(--bg); }
body { width: 880px; margin: 0; background: var(--bg); color: var(--text);
  font: 16px/1.5 'JetBrains Mono', monospace; }
main { padding: 48px; }
h1, h2, .display, .wordmark { font-family: 'Bricolage Grotesque', sans-serif;
  font-weight: 800; line-height: 1; letter-spacing: -.045em; }
h1, h2, p { margin: 0; }
h1 { font-size: 60px; }
h2 { font-size: 24px; line-height: 1.1; }
code, pre { font-family: 'JetBrains Mono', monospace; }
.label { color: var(--muted); text-transform: uppercase; font-size: 12px;
  letter-spacing: .14em; }
.muted, footer { color: var(--muted); }
.red { color: var(--red); }
.green { color: var(--green); }
.brand { display: flex; align-items: center; gap: 24px; margin-bottom: 32px; }
.mascot { display: block; object-fit: contain; flex: none; }
.wordmark { font-size: 118px; }
.hook { font: 800 42px/1.1 'Bricolage Grotesque', sans-serif; letter-spacing: -.035em;
  max-width: 740px; margin: 0 0 32px; }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.sample { background: var(--card); border: 1px solid var(--line); border-radius: 16px;
  padding: 24px; }
.sample h2 { margin: 14px 0 20px; font-size: 28px; letter-spacing: -.045em; }
.sample h2 code { font-size: inherit; }
.facts { margin: 0; padding: 0; list-style: none; font-size: 14px; }
.facts li + li { margin-top: 5px; }
.facts .measured { color: var(--muted); margin-top: 16px; font-size: 12px; }
footer { margin-top: 26px; font-size: 11px; line-height: 1.6; }
.social { width: 1280px; height: 640px; }
.social main { height: 640px; padding: 40px 48px; display: grid; position: relative;
  grid-template-columns: 1.12fr 1fr; gap: 40px; align-items: center; }
.social .brand { gap: 16px; margin-bottom: 30px; }
.social .mascot { width: 120px; height: 120px; }
.social .wordmark { font-size: 88px; }
.social .hook { font-size: 44px; margin: 0; }
.social .pair { gap: 12px; grid-template-columns: 1fr; }
.social .sample { padding: 18px 24px; }
.social .sample h2 { margin: 8px 0 12px; }
.social .facts { font-size: 13px; }
.social .facts .measured { margin-top: 8px; }
.social footer { margin-top: 20px; }
.social .benchmark-summary { position: absolute; bottom: 22px; left: 48px;
  color: var(--muted); font-size: 12px; }
.cases main { padding: 32px; }
.cases .label { height: 18px; line-height: 18px; }
.case-head { display: flex; align-items: center; gap: 24px;
  height: 64px; margin: 16px 0; white-space: nowrap; }
.case-head h1 { font-size: 64px; }
.case-head p { font: 700 32px/1 'Bricolage Grotesque', sans-serif;
  letter-spacing: -.035em; }
.case-table { width: 100%; table-layout: fixed; border-spacing: 0; }
.case-table th, .case-table td { padding: 0 12px; text-align: left;
  white-space: nowrap; border-bottom: 1px solid var(--line); }
.case-table thead tr { height: 28px; }
.case-table thead th { color: var(--muted); font-size: 11px; line-height: 16px; }
.case-table .number { width: 48px; }
.case-table .name { width: 226px; }
.case-table .detector { width: 128px; }
.case { height: 36px; font-size: 13px; line-height: 18px; }
.case th { font-weight: 400; }
.case .impact { font-size: 11px; color: var(--muted); }
.case .index { font-size: 12px; color: var(--muted); }
.case.missed { background: var(--card); color: var(--red); }
.case.missed .index, .case.missed .impact { color: var(--red); }
.catch-nu { color: var(--green); }
.catch-axe { color: var(--text); }
.catch-nothing { color: var(--red); }
.cases footer { height: 36px; line-height: 18px; margin-top: 18px; }
.terminal { border: 1px solid var(--line); border-radius: 18px;
  background: var(--card); padding: 28px; }
.terminal h1.label { font: 400 12px/18px 'JetBrains Mono', monospace;
  letter-spacing: .14em; margin-bottom: 24px; }
.terminal .command { color: var(--text); font-size: 13px; white-space: pre-wrap;
  overflow-wrap: anywhere; }
.terminal pre { font-size: 14px; line-height: 1.65; white-space: pre-wrap;
  overflow-wrap: anywhere; margin: 24px 0 0; }
.status { display: flex; justify-content: space-between; align-items: end;
  border-top: 1px solid var(--line); margin-top: 24px; padding-top: 24px; }
.status .display { font-size: 110px; }
.status code { font-size: 24px; font-weight: 700; padding-bottom: 6px; }
.benchmark main { padding: 28px; }
.benchmark .label { height: 18px; line-height: 18px; }
.benchmark h1 { height: 40px; margin: 12px 0 20px; font-size: 32px; line-height: 40px; }
.metric { height: 80px; display: grid; grid-template-columns: 90px minmax(0, 1fr) 140px;
  grid-template-rows: 40px 28px; gap: 4px 16px; padding: 4px 0;
  border-bottom: 1px solid var(--line); }
.metric h2 { grid-column: 1; grid-row: 1; align-self: center; font-size: 24px; }
.metric-bars { grid-column: 2; grid-row: 1; }
.metric .display { grid-column: 3; grid-row: 1; align-self: center;
  text-align: right; font-size: 48px; white-space: nowrap; }
.metric .unavailable { grid-column: 3; grid-row: 1; font-size: 10px; line-height: 13px; }
.metric-ranges { grid-column: 2 / 4; grid-row: 2; }
.metric .direction { color: var(--muted); font-size: 10px; line-height: 14px; white-space: nowrap; }
.bar-row { display: grid; grid-template-columns: 110px 1fr 42px;
  align-items: center; gap: 8px; height: 20px; font-size: 11px; }
.track { height: 12px; background: var(--card); border-radius: 4px; overflow: hidden; }
.bar { display: block; height: 100%; background: var(--muted); }
.bar.with { background: var(--green); }
.value { font: 700 12px/20px 'JetBrains Mono', monospace; text-align: right; }
.benchmark .nu-line { margin-top: 14px; height: 18px; font-size: 12px; line-height: 18px; }
.benchmark footer { margin-top: 14px; height: 48px; line-height: 16px; }
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


def document(title, body, kind="", theme=None):
    themed_css = ""
    if theme:
        page, border = {"light": ("#ffffff", "#6e7681"),
                        "dark": ("#0d1117", "#8b949e")}[theme]
        themed_css = (f"html, body {{ background: {page}; }}\n"
                      f"main {{ background: var(--bg); border: 1px solid {border}; "
                      "border-radius: 24px; }\n")
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>{CSS}{themed_css}</style>
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
    for side, label, code, role, tab in (
        ("before", "Div soup", "<div onclick>", "No button role", "Skipped by Tab"),
        ("after", "Native", "<button>", "Button role", "Reached by Tab"),
    ):
        color = "red" if side == "before" else "green"
        count = len(measured["cases"][case["id"]][side])
        panels.append(f'''<section class="sample">
<p class="label">{label}</p>
<h2 class="{color}"><code>{escape(code)}</code></h2>
<ul class="facts"><li>{tab}</li><li>{role}</li>
<li class="measured">Nu: {escape(case[side + "_html"])} · axe: {count} violations</li></ul>
</section>''')
    return '<div class="pair">' + "\n".join(panels) + '</div>'


def hero(rows, caught, missed, measured, social=False, theme=None, summary=None):
    hook = (f"Validators catch {caught} of these {len(rows)}. "
            f"The other {missed} look fine to every tool.")
    case = next(row for row in rows if row["id"] == "div-button")
    brand = f'<header class="brand">{MASCOT}<h1 class="wordmark">divorce</h1></header>'
    heading = escape(hook).replace(". ", ".<br>", 1)
    intro = brand + f'<p class="hook">{heading}</p>' if social else f'<h1 class="hook">{heading}</h1>'
    source = '<footer>Nu + axe: recorded checks. Tab and role: native HTML behavior.</footer>'
    pair = comparison(case, measured)
    body = f'<div>{intro}{source}</div>\n{pair}' if social else intro + pair + source
    if social and summary is not None:
        body += (f'<p class="benchmark-summary">{percentage_change(summary, "js_lines")} JavaScript · '
                 f'{percentage_change(summary, "axe_violation_nodes")} axe violations · '
                 f'{summary["runs_per_case"]} runs</p>')
    return document("divorce — native HTML, measured evidence", body, "social" if social else "hero", theme)


def cases_card(rows, missed, measured, theme=None):
    cells = []
    ordered = sorted(rows, key=lambda row: (bool(row["tools"]), row["id"]))
    for index, row in enumerate(ordered, 1):
        tools = " + ".join(f'<span class="catch-{tool.lower()}">{tool}</span>'
                           for tool in (row["tools"] or ["nothing"]))
        violations = row["violations"]
        impact = max((item["impact"] for item in violations), key=IMPACTS.index) if violations else None
        if impact:
            nodes = sum(item["nodes"] for item in violations)
            detail = f'axe: {impact} · {nodes} affected node' + ("s" if nodes != 1 else "")
        else:
            detail = "No axe violation recorded"
        kind = "case" if row["tools"] else "case missed"
        cells.append(f'''<tr class="{kind}">
<td class="index">{index:02d}</td>
<th scope="row" title="{escape(row["title"])}">{escape(row["id"])}</th>
<td class="catch">{tools}</td>
<td class="impact">{escape(detail)}</td>
</tr>''')
    body = f'''<p class="label">The evidence / before examples</p>
<header class="case-head"><h1 class="red">{missed} of {len(rows)}</h1>
<p>invisible to every tool</p></header>
<table class="case-table" aria-label="Recorded detector findings by case">
<thead><tr><th class="number" scope="col">No.</th><th class="name" scope="col">Case</th>
<th class="detector" scope="col">Detector</th><th scope="col">Impact</th></tr></thead>
<tbody>{NEWLINE.join(cells)}</tbody></table>
<footer>{escape(measured["tool"])} · {escape(measured["browser"])}<br>
“Every tool” here means Nu and axe. No finding is not proof of correct behavior.</footer>'''
    return document("divorce — the evidence", body, "cases", theme)


def ruling_card(records, theme=None):
    record = next((item for item in records if item["verdict"] == "fail"), records[0])
    verdict = record["verdict"]
    code = {"pass": 0, "fail": 1, "not_measured": 2}[verdict]
    abbreviated = {"html": [{key: entry[key] for key in ("input", "errors", "warnings")}
                             for entry in record["html"]],
                   "verdict": verdict, "reasons": record["reasons"]}
    command = "python3 skills/divorce/scripts/gate.py html " + " ".join(entry["input"] for entry in record["html"])
    output = escape(json.dumps(abbreviated, ensure_ascii=False, indent=2, sort_keys=True))
    color = "green" if verdict == "pass" else "red"
    body = f'''<section class="terminal" aria-label="Recorded gate result">
<h1 class="label">RECORDED OUTPUT / HTML ONLY</h1>
<p class="command"><code>$ {escape(command)}</code></p>
<pre>{output}</pre>
<div class="status"><p class="display {color}">{escape(verdict.upper())}</p>
<code>exit={code}</code></div>
</section>
<footer>Real gate output. Message details omitted.<br>
Nu checks HTML. An HTML-only result says nothing about axe.</footer>'''
    return document("divorce — recorded gate output", body, "ruling", theme)


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


def numbers_card(data, theme=None):
    groups = []
    for metric, label in METRICS:
        if metric == "nu_errors":
            continue
        baseline = data["arms"]["without"][metric]["mean"]
        current = data["arms"]["with"][metric]["mean"]
        if baseline:
            percent = percentage_change(data, metric).replace("%", "\u2009%")
            delta = f'<p class="display">{percent}</p>'
        else:
            delta = '<p class="muted unavailable">No percentage: baseline is zero.</p>'
        bars = []
        ranges = []
        for arm in ("without", "with"):
            stats = data["arms"][arm][metric]
            if baseline:
                width = 100 * stats["mean"] / baseline
                track_style = (f' style="width: {100 * baseline / current:.2f}%; overflow: visible"'
                               if current > baseline else "")
                bars.append(f'''<div class="bar-row"><span>{arm} divorce</span>
<div class="track"{track_style} aria-hidden="true"><span class="bar {arm}" style="width: {width:.2f}%"></span></div>
<span class="value">{width:.0f}\u2009%</span></div>''')
            ranges.append(f'<p class="direction">{arm} divorce: mean {stats["mean"]}; range {stats["min"]}–{stats["max"]}</p>')
        groups.append(f'''<section class="metric" id="{metric}"><h2>{label}</h2>
<div class="metric-bars">{NEWLINE.join(bars)}</div>{delta}
<div class="metric-ranges">{NEWLINE.join(ranges)}</div></section>''')
    with_arm, without_arm = data["arms"]["with"], data["arms"]["without"]
    body = f'''<p class="label">With / without the skill</p>
<h1>Same agent, same {data["cases"]} tasks, {data["runs_per_case"]} runs each.</h1>
{NEWLINE.join(groups)}
<p class="nu-line">Nu errors: {with_arm["pages_with_nu_errors"]} of {with_arm["pages"]} pages with divorce, {without_arm["pages_with_nu_errors"]} of {without_arm["pages"]} without</p>
<footer>{data["cases"]} synthetic tasks, one model, one machine; lines measure size, not quality.<br>
Model: {escape(data["model"])}<br>{escape(data["date"])}</footer>'''
    return document("divorce — measured numbers", body, "benchmark", theme)


def build(root=ROOT, out_dir=None):
    root = Path(root)
    out_dir = Path(out_dir) if out_dir is not None else root / "assets/cards/html"
    manifest = read_json(root / "examples/manifest.json")
    measured = read_json(root / "examples/axe-measured.json")
    records = read_json(root / "assets/data/gate-real.json")
    rows, caught, missed = evidence(manifest, measured)
    summary = root / "evals/results/summary.json"
    data = validate_summary(read_json(summary)) if summary.exists() else None
    pages = {"social.html": hero(rows, caught, missed, measured, social=True, summary=data)}
    for theme in ("light", "dark"):
        pages[f"hero-{theme}.html"] = hero(rows, caught, missed, measured, theme=theme)
        pages[f"cases-{theme}.html"] = cases_card(rows, missed, measured, theme)
        pages[f"ruling-{theme}.html"] = ruling_card(records, theme)
        if data is not None:
            pages[f"numbers-{theme}.html"] = numbers_card(data, theme)
    out_dir.mkdir(parents=True, exist_ok=True)
    obsolete = {"hero.html", "cases.html", "ruling.html", "numbers.html",
                "numbers-light.html", "numbers-dark.html"} - pages.keys()
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
