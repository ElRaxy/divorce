#!/usr/bin/env python3
"""Build evidence cards from the manifest and measured axe results."""

import argparse
import json
from html import escape
from pathlib import Path


ASSETS = Path(__file__).resolve().parent
PALETTES = {
    "cases.svg": ("#f4efdf", "#fbf8ee", "#28271f", "#676254", "#c4baa4", "#8b3e2f"),
    "cases-dark.svg": ("#211f1a", "#2c2922", "#f2ead5", "#c2b79e", "#605746", "#e6ab82"),
}


def case_tag(case, measured):
    tools = []
    if case["before_html"] == "fail":
        tools.append("Nu")
    if measured[case["id"]]["before"]:
        tools.append("axe")
    return " + ".join(tools) or "no tool: the ladder"


def render(cases, measured, palette):
    paper, card, ink, muted, rule, accent = palette
    tags = [case_tag(case, measured) for case in cases]
    count = sum(tag != "no tool: the ladder" for tag in tags)
    headline = f"{count} of {len(cases)} caught by tools"
    rows = max(1, (len(cases) + 2) // 3)
    height = 241 + rows * 199
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="{height}" viewBox="0 0 1280 {height}" role="img" aria-labelledby="title description">',
        f"  <title id=\"title\">{headline}</title>",
        '  <desc id="description">Nu and axe measured. Coverage counts cases with Nu errors or measured axe violations in their before example. Each axe case shows its highest measured impact. Cases without a tool rely on the decision ladder and manual checks.</desc>',
        "  <style>",
        "    text { font-family: Georgia, 'Times New Roman', serif; }",
        "    .mono { font-family: 'Courier New', Courier, monospace; }",
        "  </style>",
        f'  <rect width="1280" height="{height}" fill="{paper}"/>',
        f'  <text x="48" y="100" font-size="60" fill="{ink}">{headline}</text>',
        f'  <text class="mono" x="48" y="151" font-size="28" fill="{muted}">Nu and axe measured</text>',
        f'  <path d="M48 175 H1232" stroke="{rule}" stroke-width="2"/>',
    ]
    for index, (case, tag) in enumerate(zip(cases, tags)):
        x = 48 + (index % 3) * 403
        y = 200 + (index // 3) * 199
        name = escape(case["id"].replace("-", " "))
        parts.extend([
            f'  <g transform="translate({x} {y})">',
            f'    <title>{escape(case["title"])}</title>',
            f'    <rect width="378" height="175" fill="{card}" stroke="{rule}"/>',
            f'    <text x="22" y="53" font-size="34" fill="{ink}">{name}</text>',
            f'    <path d="M22 72 H356" stroke="{rule}"/>',
            f'    <text class="mono" x="22" y="111" font-size="28" fill="{accent}">{tag}</text>',
        ])
        violations = measured[case["id"]]["before"]
        if violations:
            severity = {None: 0, "minor": 1, "moderate": 2, "serious": 3, "critical": 4}
            impact = max((item["impact"] for item in violations), key=lambda value: severity[value])
            parts.append(f'    <text class="mono" x="22" y="149" font-size="24" fill="{muted}">axe: {impact or "unreported"}</text>')
        parts.append("  </g>")
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ASSETS.parent / "examples" / "manifest.json")
    parser.add_argument("--axe-measured", type=Path, default=ASSETS.parent / "examples" / "axe-measured.json")
    parser.add_argument("--out-dir", type=Path, default=ASSETS)
    args = parser.parse_args()
    cases = json.loads(args.manifest.read_text(encoding="utf-8"))["cases"]
    measured = json.loads(args.axe_measured.read_text(encoding="utf-8"))["cases"]
    for case in cases:
        if case["id"] not in measured:
            parser.error(f"missing measured axe case: {case['id']}")
        if not isinstance(measured[case["id"]].get("before"), list):
            parser.error(f"missing or invalid measured axe before: {case['id']}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for filename, palette in PALETTES.items():
        (args.out_dir / filename).write_bytes(render(cases, measured, palette).encode("utf-8"))


if __name__ == "__main__":
    main()
