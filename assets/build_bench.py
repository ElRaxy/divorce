#!/usr/bin/env python3
"""Build Numbers cards from benchmark results, using only the standard library."""

import argparse
from datetime import date
from html import escape
import json
from pathlib import Path
import textwrap


ASSETS = Path(__file__).resolve().parent
PALETTES = {
    "bench.svg": ("#f4efdf", "#28271f", "#676254", "#c4baa4", "#8b3e2f"),
    "bench-dark.svg": ("#211f1a", "#f2ead5", "#c2b79e", "#605746", "#e6ab82"),
}
METRICS = (
    ("gate_pass", "Gate passes", "higher is better"),
    ("nu_errors", "Nu errors", "lower is better"),
    ("axe_violations", "axe violations", "lower is better"),
    ("native_choice", "Native choices", "higher is better"),
)


def validate(data):
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


def render(data, palette):
    paper, ink, muted, rule, accent = palette
    model_lines = textwrap.wrap(data["model"], width=68)
    height = 850 + 30 * len(model_lines)
    description = "; ".join(
        f'{label}: with {data["arms"]["with"][metric]}, without {data["arms"]["without"][metric]}'
        for metric, label, _ in METRICS
    )
    description += (
        f'. Model: {data["model"]}. Date: {data["date"]}. '
        f'{data["runs_per_case"]} runs per case; {data["cases"]} cases per arm. '
        "Raw counts; each metric has its own scale, shared by both arms."
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="{height}" viewBox="0 0 1280 {height}" role="img" aria-labelledby="title description">',
        '  <title id="title">Numbers</title>',
        f'  <desc id="description">{escape(description)}</desc>',
        "  <style>text { font-family: Georgia, 'Times New Roman', serif; } .mono { font-family: 'Courier New', Courier, monospace; }</style>",
        f'  <rect width="1280" height="{height}" fill="{paper}"/>',
        f'  <text x="48" y="100" font-size="60" fill="{ink}">Numbers</text>',
        f'  <text class="mono" x="48" y="150" font-size="24" fill="{muted}">Raw counts · with / without the skill · scale per metric</text>',
        f'  <path d="M48 175 H1232" stroke="{rule}" stroke-width="2"/>',
    ]
    for index, (metric, label, direction) in enumerate(METRICS):
        values = [data["arms"][arm][metric] for arm in ("with", "without")]
        maximum = max(values)
        y = 210 + index * 137
        parts.extend([
            f'  <g id="{metric}">',
            f'    <text x="48" y="{y}" font-size="30" fill="{ink}">{label}</text>',
            f'    <text class="mono" x="420" y="{y}" font-size="21" fill="{muted}">{direction} · scale 0–{maximum}</text>',
        ])
        for offset, (arm, value) in enumerate(zip(("with", "without"), values)):
            bar_y = y + 17 + offset * 39
            width = 640 * value / (maximum or 1)
            color = accent if arm == "with" else muted
            parts.extend([
                f'    <text class="mono" x="270" y="{bar_y + 22}" font-size="24" fill="{ink}">{arm}</text>',
                f'    <rect x="420" y="{bar_y}" width="640" height="26" fill="{rule}" opacity="0.3"/>',
                f'    <rect data-arm="{arm}" x="420" y="{bar_y}" width="{width:.2f}" height="26" fill="{color}"/>',
                f'    <text class="mono" x="1090" y="{bar_y + 22}" font-size="24" fill="{ink}">{value}</text>',
            ])
        parts.append("  </g>")
    parts.append(f'  <path d="M48 762 H1232" stroke="{rule}"/>')
    for index, line in enumerate(model_lines):
        prefix = "Model: " if index == 0 else "       "
        parts.append(f'  <text class="mono" xml:space="preserve" x="48" y="{803 + index * 30}" font-size="24" fill="{ink}">{escape(prefix + line)}</text>')
    footer = f'{data["date"]} · {data["runs_per_case"]} runs per case · {data["cases"]} cases per arm'
    parts.extend([
        f'  <text class="mono" x="48" y="{818 + len(model_lines) * 30}" font-size="24" fill="{muted}">{footer}</text>',
        "</svg>",
    ])
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ASSETS.parent / "evals" / "results" / "summary.json")
    parser.add_argument("--out-dir", type=Path, default=ASSETS)
    args = parser.parse_args()
    try:
        data = validate(json.loads(args.input.read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for filename, palette in PALETTES.items():
        (args.out_dir / filename).write_bytes(render(data, palette).encode("utf-8"))


if __name__ == "__main__":
    main()
