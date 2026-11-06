#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 divorce contributors
"""Print the example index generated from manifest.json."""

import json
from pathlib import Path


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def render(manifest):
    lines = [
        "# Native HTML examples", "",
        "Generated from `examples/manifest.json`. Regenerate from the repository root:",
        "", "```sh", "python3 examples/build_readme.py > examples/README.md", "```", "",
        "Each pair changes one pattern. HTML validity does not establish accessibility.",
        "Expected HTML verdicts were measured with Nu HTML Checker 26.11.4 (2026-11-06).",
        "The listed axe rule IDs are documented in [axe-core 4.10.2]"
        "(https://raw.githubusercontent.com/dequelabs/axe-core/v4.10.2/doc/rule-descriptions.md).",
        "Their expected occurrence before and absence after remain **unverified**; axe has not been run.",
        "Empty rule lists deliberately make no automated accessibility claim; see each note.",
        "No browser, keyboard or assistive-technology checks are claimed by this index.", "",
        "| Case | Rationale | Before HTML | After HTML | Expected axe rules in before | Note |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for case in manifest["cases"]:
        identifier = case["id"]
        rules = ", ".join(f"`{rule}`" for rule in case["axe_rules"]) or "None asserted"
        row = [f"`{identifier}`", f"[{case['title']}]({case['spec']})",
               f"[{case['before_html']}]({identifier}/before.html)",
               f"[{case['after_html']}]({identifier}/after.html)",
               rules, case.get("note", "")]
        lines.append("| " + " | ".join(map(cell, row)) + " |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    manifest_path = Path(__file__).with_name("manifest.json")
    print(render(json.loads(manifest_path.read_text(encoding="utf-8"))), end="")
