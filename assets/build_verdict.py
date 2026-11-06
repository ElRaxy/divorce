#!/usr/bin/env python3
"""Build the terminal ruling from the recorded gate evidence (stdlib only)."""

import argparse
import json
from html import escape
from pathlib import Path


ASSETS = Path(__file__).resolve().parent
PALETTES = {
    "verdict.svg": ("#f4efdf", "#fbf8ee", "#28271f", "#676254", "#c4baa4", "#8b3e2f"),
    "verdict-dark.svg": ("#211f1a", "#2c2922", "#f2ead5", "#c2b79e", "#605746", "#e6ab82"),
}
EXIT_CODES = {"pass": 0, "fail": 1, "not_measured": 2}


def render(record, palette):
    paper, card, ink, muted, rule, accent = palette
    finding = record["html"][0]
    excerpt = {
        "html": [{key: finding[key] for key in ("input", "errors", "warnings")}],
        "verdict": record["verdict"],
        "reasons": record["reasons"],
    }
    lines = [
        "$ python3 skills/divorce/scripts/gate.py html \\",
        f'    {finding["input"]}',
        "",
        *json.dumps(excerpt, indent=2, ensure_ascii=False).splitlines(),
        f'exit={EXIT_CODES[record["verdict"]]}',
    ]
    height = 263 + len(lines) * 30
    description = (
        f'Recorded HTML check of {finding["input"]}: {finding["errors"]} errors, '
        f'{finding["warnings"]} warnings, verdict {record["verdict"]}, '
        f'exit {EXIT_CODES[record["verdict"]]}. Message details omitted from the display. '
        'This is an HTML-only ruling; no axe result is claimed.'
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="{height}" viewBox="0 0 1280 {height}" role="img" aria-labelledby="title description">',
        '  <title id="title">The ruling</title>',
        f'  <desc id="description">{escape(description)}</desc>',
        f'  <rect width="1280" height="{height}" fill="{paper}"/>',
        f'  <text x="48" y="90" font-family="Georgia, serif" font-size="60" fill="{ink}">The ruling</text>',
        f'  <text x="48" y="140" font-family="Georgia, serif" font-size="28" fill="{muted}">Recorded HTML check. Message details omitted.</text>',
        f'  <rect x="48" y="174" width="1184" height="{height - 214}" rx="6" fill="{card}" stroke="{rule}"/>',
        f'  <g font-family="Courier New, Courier, monospace" font-size="26" fill="{ink}">',
    ]
    for index, line in enumerate(lines):
        color = accent if '"verdict"' in line or line.startswith("exit=") else ink
        parts.append(f'    <text xml:space="preserve" x="76" y="{221 + index * 30}" fill="{color}">{escape(line)}</text>')
    parts.extend(["  </g>", "</svg>"])
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ASSETS / "data" / "gate-real.json")
    parser.add_argument("--out-dir", type=Path, default=ASSETS)
    args = parser.parse_args()
    records = json.loads(args.input.read_text(encoding="utf-8"))
    record = next(item for item in records if item["html"][0]["input"] == "examples/image-alt/before.html")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for filename, palette in PALETTES.items():
        (args.out_dir / filename).write_bytes(render(record, palette).encode("utf-8"))


if __name__ == "__main__":
    main()
