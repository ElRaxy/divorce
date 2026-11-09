#!/usr/bin/env python3
"""Build the two deterministic editorial HTML banners. No browser required."""

import argparse
from datetime import date
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
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
CSS = """@font-face { font-family: 'Instrument Serif'; font-weight: 400;
  font-style: normal; font-display: block;
  src: url("../../fonts/instrument-serif-latin-400-normal.woff2") format("woff2"); }
@font-face { font-family: 'Instrument Serif'; font-weight: 400;
  font-style: italic; font-display: block;
  src: url("../../fonts/instrument-serif-latin-400-italic.woff2") format("woff2"); }
@font-face { font-family: 'Geist'; font-weight: 500;
  font-style: normal; font-display: block;
  src: url("../../fonts/geist-sans-latin-500-normal.woff2") format("woff2"); }
body { margin: 0; width: 880px; height: 400px; background: #f6f3ec; }
.b { display: grid; grid-template-columns: 300px 1fr; align-items: center;
  gap: 8px; padding: 44px 64px 44px 40px; height: 312px; }
img { width: 300px; display: block; }
h1 { font: 400 76px/0.95 "Instrument Serif", serif; letter-spacing: -0.02em;
  color: #1b1a17; margin: 0 0 22px; text-wrap: balance; }
h1 em { color: #d8432f; }
p { font: 500 15px/1.5 Geist, sans-serif; color: #6b665c; margin: 0; }
p b { color: #1b1a17; font-weight: 500; }
"""
SOCIAL_CSS = """body { width: 1280px; height: 640px; }
.b { grid-template-columns: 420px 1fr; gap: 12px;
  padding: 62px 90px 62px 56px; height: 516px; }
img { width: 420px; }
h1 { font-size: 108px; margin-bottom: 31px; }
p { font-size: 21px; }
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


def document(social=False):
    css = CSS + (SOCIAL_CSS if social else "")
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>divorce — Native first. Then proven.</title>
<style>{css}</style>
</head>
<body>
<main class="b"><img src="../../mascot.png" alt=""><div>
<h1>Native first.<br><em>Then proven.</em></h1>
<p><b>divorce</b> &nbsp;·&nbsp; a skill for Claude Code and Codex</p>
</div></main>
</body>
</html>
'''


def build(root=ROOT, out_dir=None):
    root = Path(root)
    out_dir = Path(out_dir) if out_dir is not None else root / "assets/cards/html"
    pages = {"banner.html": document(), "social.html": document(social=True)}
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, content in sorted(pages.items()):
        (out_dir / name).write_bytes(content.encode("utf-8"))
    return sorted(pages)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Project root")
    parser.add_argument("--out-dir", type=Path, help="Default: assets/cards/html under the project root")
    args = parser.parse_args()
    try:
        names = build(args.root, args.out_dir)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print("Built " + ", ".join(names))


if __name__ == "__main__":
    main()
