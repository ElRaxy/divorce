#!/usr/bin/env python3
"""Draw the six literal decision rungs from the skill, using only the stdlib."""

import argparse
from html import escape
from pathlib import Path
import re
import textwrap


ASSETS = Path(__file__).resolve().parent
PALETTES = {
    "ladder.svg": ("#f4efdf", "#fbf8ee", "#28271f", "#676254", "#c4baa4", "#8b3e2f"),
    "ladder-dark.svg": ("#211f1a", "#2c2922", "#f2ead5", "#c2b79e", "#605746", "#e6ab82"),
}


def read_rungs(skill):
    section = skill.split("## 1. Before writing: the ladder\n", 1)[1].split("\n## 2.", 1)[0]
    rungs = re.findall(r"^\d+\. (.+)$", section, re.MULTILINE)
    if len(rungs) != 6:
        raise ValueError("The decision ladder must contain exactly six rungs")
    return rungs


def render(rungs, palette):
    paper, card, ink, muted, rule, accent = palette
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="1080" viewBox="0 0 1280 1080" role="img" aria-labelledby="title description">',
        '  <title id="title">Before a single tag</title>',
        f'  <desc id="description">Stop at the first rung that holds. {escape(" ".join(f"{i}. {rung}" for i, rung in enumerate(rungs, 1)))}</desc>',
        f'  <rect width="1280" height="1080" fill="{paper}"/>',
        f'  <text x="48" y="90" font-family="Georgia, serif" font-size="60" fill="{ink}">Before a single tag</text>',
        f'  <text x="48" y="142" font-family="Georgia, serif" font-size="30" fill="{muted}">Stop at the first rung that holds.</text>',
    ]
    for index, rung in enumerate(rungs):
        x, y = 48 + index * 78, 185 + index * 132
        width = 1184 - index * 78
        lines = textwrap.wrap(rung, width=int((width - 105) / 14.5))
        parts.extend([
            f'  <g data-rung="{index + 1}">',
            f'    <rect x="{x}" y="{y}" width="{width}" height="132" fill="{card}"/>',
            f'    <path d="M{x} {y + 132} V{y} H1232" fill="none" stroke="{rule}" stroke-width="3"/>',
            f'    <text x="{x + 16}" y="{y + 48}" font-family="Courier New, monospace" font-size="32" fill="{accent}">{index + 1}</text>',
            f'    <text class="rung" x="{x + 72}" y="{y + 46}" font-family="Georgia, serif" font-size="28" fill="{ink}">',
        ])
        for line_index, line in enumerate(lines):
            parts.append(f'      <tspan x="{x + 72}" dy="{0 if line_index == 0 else 35}">{escape(line)}</tspan>')
        parts.extend(["    </text>", "  </g>"])
    parts.extend([
        f'  <path d="M438 977 H1232" stroke="{rule}" stroke-width="3"/>',
        f'  <text x="48" y="1035" font-family="Georgia, serif" font-size="26" fill="{muted}">Accessibility, boundary validation and data-loss handling stay.</text>',
        "</svg>",
    ])
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", type=Path, default=ASSETS.parent / "skills" / "divorce" / "SKILL.md")
    parser.add_argument("--out-dir", type=Path, default=ASSETS)
    args = parser.parse_args()
    rungs = read_rungs(args.skill.read_text(encoding="utf-8"))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for filename, palette in PALETTES.items():
        (args.out_dir / filename).write_bytes(render(rungs, palette).encode("utf-8"))


if __name__ == "__main__":
    main()
