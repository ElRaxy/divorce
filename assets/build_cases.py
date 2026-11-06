#!/usr/bin/env python3
"""Build the evidence cards from the manifest, without external dependencies."""

import argparse
import json
from html import escape
from pathlib import Path


ASSETS = Path(__file__).resolve().parent
PALETTES = {
    "cases.svg": ("#f4efdf", "#fbf8ee", "#28271f", "#676254", "#c4baa4", "#8b3e2f"),
    "cases-dark.svg": ("#211f1a", "#2c2922", "#f2ead5", "#c2b79e", "#605746", "#e6ab82"),
}


def case_tag(case):
    tools = []
    if case["before_html"] == "fail":
        tools.append("Nu")
    if case["axe_rules"]:
        tools.append("axe")
    return " + ".join(tools) or "no tool: the ladder"


def render(cases, palette):
    paper, card, ink, muted, rule, accent = palette
    tags = [case_tag(case) for case in cases]
    count = sum(tag != "no tool: the ladder" for tag in tags)
    headline = f"{count} of {len(cases)} caught by tools"
    rows = max(1, (len(cases) + 2) // 3)
    height = 241 + rows * 165
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="{height}" viewBox="0 0 1280 {height}" role="img" aria-labelledby="title description">',
        f"  <title id=\"title\">{headline}</title>",
        '  <desc id="description">Manifest coverage: Nu results are measured; axe rules are expected, not run. Cases without a tool rely on the decision ladder and manual checks.</desc>',
        "  <style>",
        "    text { font-family: Georgia, 'Times New Roman', serif; }",
        "    .mono { font-family: 'Courier New', Courier, monospace; }",
        "  </style>",
        f'  <rect width="1280" height="{height}" fill="{paper}"/>',
        f'  <text x="48" y="100" font-size="60" fill="{ink}">{headline}</text>',
        f'  <text class="mono" x="48" y="151" font-size="28" fill="{muted}">Nu measured · axe expected, not run</text>',
        f'  <path d="M48 175 H1232" stroke="{rule}" stroke-width="2"/>',
    ]
    for index, (case, tag) in enumerate(zip(cases, tags)):
        x = 48 + (index % 3) * 403
        y = 200 + (index // 3) * 165
        name = escape(case["id"].replace("-", " "))
        parts.extend([
            f'  <g transform="translate({x} {y})">',
            f'    <title>{escape(case["title"])}</title>',
            f'    <rect width="378" height="141" fill="{card}" stroke="{rule}"/>',
            f'    <text x="22" y="53" font-size="34" fill="{ink}">{name}</text>',
            f'    <path d="M22 72 H356" stroke="{rule}"/>',
            f'    <text class="mono" x="22" y="111" font-size="28" fill="{accent}">{tag}</text>',
            "  </g>",
        ])
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ASSETS.parent / "examples" / "manifest.json")
    parser.add_argument("--out-dir", type=Path, default=ASSETS)
    args = parser.parse_args()
    cases = json.loads(args.manifest.read_text(encoding="utf-8"))["cases"]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for filename, palette in PALETTES.items():
        (args.out_dir / filename).write_bytes(render(cases, palette).encode("utf-8"))


if __name__ == "__main__":
    main()
