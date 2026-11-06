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
    ("gate_pass", "Gate passes", "higher is better"),
    ("nu_errors", "Nu errors", "lower is better"),
    ("axe_violations", "axe violations", "lower is better"),
    ("native_choice", "Native choices", "higher is better"),
)
IMPACTS = ("minor", "moderate", "serious", "critical")
MASCOT = '<img class="mascot" src="../../mascot.png" width="160" height="160" alt="A weary div character in round glasses signs separation papers with a red pen.">'
CSS = """:root { color-scheme: dark; --bg: #0b0b0c; --card: #141416; --line: #26262a;
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
.social main { height: 640px; padding: 40px 48px; display: grid;
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
.case-head { margin: 24px 0 36px; }
.case-head h1 { font-size: 152px; white-space: nowrap; }
.case-head p { font: 700 34px/1.1 'Bricolage Grotesque', sans-serif;
  margin-top: 12px; letter-spacing: -.035em; }
.case-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.case { min-height: 206px; padding: 20px; background: var(--card);
  border: 1px solid var(--line); border-radius: 14px; }
.case h2 { min-height: 54px; font-size: 23px; margin: 18px 0; }
.case .catch { font-size: 13px; }
.case .impact { font-size: 11px; color: var(--muted); margin-top: 6px; }
.case .index { font-size: 12px; color: var(--muted); }
.terminal { border: 1px solid var(--line); border-radius: 18px;
  background: var(--card); margin-top: 32px; padding: 28px; }
.terminal .command { color: var(--text); font-size: 13px; white-space: pre-wrap;
  overflow-wrap: anywhere; }
.terminal pre { font-size: 14px; line-height: 1.65; white-space: pre-wrap;
  overflow-wrap: anywhere; margin: 24px 0 0; }
.status { display: flex; justify-content: space-between; align-items: end;
  border-top: 1px solid var(--line); margin-top: 24px; padding-top: 24px; }
.status .display { font-size: 110px; }
.status code { font-size: 24px; font-weight: 700; padding-bottom: 6px; }
.benchmark h1 { margin: 20px 0 36px; font-size: 56px; }
.metric { margin-top: 28px; }
.metric h2 { margin-bottom: 6px; }
.metric .direction { color: var(--muted); font-size: 11px; margin-bottom: 14px; }
.bar-row { display: grid; grid-template-columns: 90px 1fr 64px;
  align-items: center; gap: 12px; margin-top: 8px; font-size: 12px; }
.track { height: 24px; background: var(--card); border-radius: 4px; overflow: hidden; }
.bar { display: block; height: 100%; background: var(--muted); }
.bar.with { background: var(--green); }
.value { font: 800 24px/1 'Bricolage Grotesque', sans-serif; text-align: right; }
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
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@700;800&amp;family=JetBrains+Mono:wght@400;700&amp;display=swap" rel="stylesheet">
<style>{CSS}</style>
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


def hero(rows, caught, missed, measured, social=False):
    hook = (f"Validators catch {caught} of these {len(rows)}. "
            f"The other {missed} look fine to every tool.")
    case = next(row for row in rows if row["id"] == "div-button")
    brand = f'<header class="brand">{MASCOT}<h1 class="wordmark">divorce</h1></header>'
    intro = brand + f'<p class="hook">{escape(hook).replace(". ", ".<br>", 1)}</p>'
    source = '<footer>Nu + axe: recorded checks. Tab and role: native HTML behavior.</footer>'
    pair = comparison(case, measured)
    body = f'<div>{intro}{source}</div>\n{pair}' if social else intro + pair + source
    return document("divorce — native HTML, measured evidence", body, "social" if social else "hero")


def cases_card(rows, missed, measured):
    cells = []
    for index, row in enumerate(rows, 1):
        tools = " + ".join(row["tools"]) or "nothing"
        violations = row["violations"]
        impact = max((item["impact"] for item in violations), key=IMPACTS.index) if violations else None
        if impact:
            nodes = sum(item["nodes"] for item in violations)
            detail = f'axe: {impact} · {nodes} affected node' + ("s" if nodes != 1 else "")
        else:
            detail = "No axe violation recorded"
        cells.append(f'''<article class="case">
<p class="index">{index:02d} / {escape(row["id"])}</p>
<h2>{escape(row["title"])}</h2>
<p class="catch">Caught by: {escape(tools)}</p>
<p class="impact">{escape(detail)}</p>
</article>''')
    body = f'''<p class="label">The evidence / before examples</p>
<header class="case-head"><h1 class="red">{missed} of {len(rows)}</h1>
<p>invisible to every tool</p></header>
<div class="case-grid">{NEWLINE.join(cells)}</div>
<footer>{escape(measured["tool"])} · {escape(measured["browser"])}<br>
“Every tool” here means Nu and axe. No finding is not proof of correct behavior.</footer>'''
    return document("divorce — the evidence", body, "cases")


def ruling_card(records):
    record = next((item for item in records if item["verdict"] == "fail"), records[0])
    verdict = record["verdict"]
    code = {"pass": 0, "fail": 1, "not_measured": 2}[verdict]
    abbreviated = {"html": [{key: entry[key] for key in ("input", "errors", "warnings")}
                             for entry in record["html"]],
                   "verdict": verdict, "reasons": record["reasons"]}
    command = "python3 skills/divorce/scripts/gate.py html " + " ".join(entry["input"] for entry in record["html"])
    output = escape(json.dumps(abbreviated, ensure_ascii=False, indent=2, sort_keys=True))
    color = "green" if verdict == "pass" else "red"
    body = f'''<p class="label">Recorded output / HTML only</p>
<h1>The ruling.</h1>
<section class="terminal" aria-label="Recorded gate result">
<p class="command"><code>$ {escape(command)}</code></p>
<pre>{output}</pre>
<div class="status"><p class="display {color}">{escape(verdict.upper())}</p>
<code>exit={code}</code></div>
</section>
<footer>Real gate output. Message details omitted.<br>
Nu checks HTML. An HTML-only result says nothing about axe.</footer>'''
    return document("divorce — the ruling", body, "ruling")


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
            for metric, _, _ in METRICS:
                value = data["arms"][arm][metric]
                if type(value) is not int or value < 0:
                    raise ValueError(f"arms.{arm}.{metric} must be a non-negative integer")
    except (KeyError, TypeError) as error:
        raise ValueError(f"invalid or missing summary field: {error}") from error
    return data


def numbers_card(data):
    groups = []
    for metric, label, direction in METRICS:
        maximum = max(data["arms"][arm][metric] for arm in ("with", "without"))
        bars = []
        for arm in ("without", "with"):
            value = data["arms"][arm][metric]
            width = 100 * value / (maximum or 1)
            bars.append(f'''<div class="bar-row"><span>{arm}</span>
<div class="track" aria-hidden="true"><span class="bar {arm}" style="width: {width:.2f}%"></span></div>
<span class="value">{value}</span></div>''')
        groups.append(f'''<section class="metric" id="{metric}"><h2>{label}</h2>
<p class="direction">{direction} · scale 0–{maximum}</p>{NEWLINE.join(bars)}</section>''')
    body = f'''<p class="label">With / without the skill</p>
<h1>Same tasks.<br>The measured difference.</h1>
{NEWLINE.join(groups)}
<footer>Model: {escape(data["model"])}<br>{escape(data["date"])} · {data["runs_per_case"]} runs per case · {data["cases"]} cases per arm.<br>
Raw counts. Each metric has its own scale, shared by both arms.</footer>'''
    return document("divorce — measured numbers", body, "benchmark")


def build(root=ROOT, out_dir=None):
    root = Path(root)
    out_dir = Path(out_dir) if out_dir is not None else root / "assets/cards/html"
    manifest = read_json(root / "examples/manifest.json")
    measured = read_json(root / "examples/axe-measured.json")
    records = read_json(root / "assets/data/gate-real.json")
    rows, caught, missed = evidence(manifest, measured)
    pages = {"hero.html": hero(rows, caught, missed, measured),
             "social.html": hero(rows, caught, missed, measured, social=True),
             "cases.html": cases_card(rows, missed, measured),
             "ruling.html": ruling_card(records)}
    summary = root / "evals/results/summary.json"
    if summary.exists():
        pages["numbers.html"] = numbers_card(validate_summary(read_json(summary)))
    out_dir.mkdir(parents=True, exist_ok=True)
    if "numbers.html" not in pages:
        (out_dir / "numbers.html").unlink(missing_ok=True)
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
