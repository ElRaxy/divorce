#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 divorce contributors
"""Store per-page HTML and accessibility measurements from retained eval runs."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


GATE = Path(__file__).resolve().parents[1] / "skills/divorce/scripts/gate.py"
ARMS = ("with", "without")


def read_result(path):
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict) or not isinstance(result.get("cases"), list):
        raise ValueError("Missing cases list")
    names = set()
    for case in result["cases"]:
        if not isinstance(case, dict):
            raise ValueError("Invalid case")
        name = case.get("name")
        if (not isinstance(name, str) or not name or name in (".", "..")
                or any(char in name for char in "/\\:\0")
                or name.startswith("-") or name in names):
            raise ValueError("Invalid case name")
        names.add(name)
        arms = case.get("arms")
        if not isinstance(arms, dict):
            raise ValueError("Missing arms")
        for arm in ARMS:
            runs = arms.get(arm)
            if not isinstance(runs, list) or any(not isinstance(run, dict) for run in runs):
                raise ValueError("Invalid runs list")
    return result


def write_json(path, value):
    path.write_text(json.dumps(value, indent=1, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def scrub(value, roots):
    """Drop local directory prefixes so stored evidence names pages, not machines."""
    if isinstance(value, str):
        prefixes = {prefix for root in roots
                    for path in (Path(root), Path(root).resolve())
                    for prefix in (str(path) + os.sep, "file:" + str(path) + os.sep,
                                   "file://" + str(path) + os.sep,
                                   path.as_uri() + "/")}
        for prefix in sorted(prefixes, key=lambda item: (-len(item), item)):
            value = value.replace(prefix, "")
        return value
    if isinstance(value, list):
        return [scrub(item, roots) for item in value]
    if isinstance(value, dict):
        return {scrub(key, roots): scrub(item, roots) for key, item in value.items()}
    return value


def run_gate(command, name, out, roots=()):
    try:
        process = subprocess.run(
            [sys.executable, str(GATE), command, name], cwd=out,
            capture_output=True, text=True, encoding="utf-8", timeout=120,
            check=False,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        return {"exit": 2, "result": None}
    try:
        result = json.loads(process.stdout)
    except (ValueError, RecursionError):
        result = None
    roots = (str(out) + os.sep,) + tuple(roots)
    return {"exit": process.returncode, "result": scrub(result, roots)}


def measure_axe(page, axe_dir, out):
    if axe_dir is None:
        return None, None
    path = axe_dir / f"{page}.axe.json"
    if not path.exists():
        return None, None
    gate = run_gate("axe", str(path), out, (str(axe_dir) + os.sep,))
    result = gate["result"]
    axe = result.get("axe") if isinstance(result, dict) else None
    if gate["exit"] in (0, 1) and isinstance(axe, dict):
        return {"exit": gate["exit"], "rules": axe["rules"]}, gate
    return None, gate


def measure_page(case, arm, number, run, source_dir, out, axe_dir):
    page = f"{case}-{arm}-{number}"
    axe, axe_gate = measure_axe(page, axe_dir, out)
    record = {
        "page": page, "case": case, "arm": arm, "run": number,
        "status": "html_missing", "html_sha256": None, "nu": None,
        "axe": axe, "axe_gate": axe_gate,
    }
    if run.get("error") is not None:
        record["status"] = "run_error"
        return record
    trace = run.get("tracePath")
    if not isinstance(trace, str) or not trace:
        return record
    try:
        trace_path = Path(trace)
        if not trace_path.is_absolute():
            trace_path = source_dir / trace_path
        source = trace_path.parents[1] / "sealed" / "home" / "cwd" / "index.html"
        content = source.read_bytes()
    except (OSError, ValueError, IndexError):
        return record
    name = f"{page}.html"
    (out / name).write_bytes(content)
    record["html_sha256"] = hashlib.sha256(content).hexdigest()
    gate = run_gate("html", name, out)
    write_json(out / f"{page}.gate.json", gate)
    result = gate["result"]
    groups = result.get("html") if isinstance(result, dict) else None
    if groups and isinstance(groups, list) and isinstance(groups[0], dict):
        group = groups[0]
        if all(key in group for key in ("errors", "warnings", "messages")):
            record["nu"] = {"exit": gate["exit"], "errors": group["errors"],
                            "warnings": group["warnings"], "messages": group["messages"]}
    record["status"] = ("measured" if gate["exit"] in (0, 1) and record["nu"] is not None
                        else "gate_not_measured")
    return record


def arm_totals(pages, arm):
    selected = [page for page in pages if page["arm"] == arm]
    measured = [page for page in selected if page["status"] == "measured"]
    axe = [page["axe"] for page in selected
           if page["axe"] is not None and page["axe"]["exit"] in (0, 1)]
    return {
        "pages": len(selected), "pages_measured": len(measured),
        "pages_with_nu_errors": sum(page["nu"]["errors"] > 0 for page in measured),
        "nu_errors": sum(page["nu"]["errors"] for page in measured),
        "pages_with_axe_violations": sum(bool(item["rules"]) for item in axe),
        "pages_axe_measured": len(axe),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_json", type=Path, metavar="RESULT_JSON")
    parser.add_argument("--out", type=Path, required=True, metavar="DIR")
    parser.add_argument("--axe-dir", type=Path, metavar="DIR")
    args = parser.parse_args()
    try:
        result = read_result(args.result_json)
    except (OSError, ValueError, RecursionError):
        print("Cannot read eval result: expected valid JSON with cases.", file=sys.stderr)
        return 2
    try:
        out = args.out.absolute()
        out.mkdir(parents=True, exist_ok=True)
        source_dir = args.result_json.resolve().parent
        axe_dir = args.axe_dir.absolute() if args.axe_dir is not None else None
        pages = [measure_page(case["name"], arm, number, run, source_dir, out, axe_dir)
                 for case in result["cases"] for arm in ARMS
                 for number, run in enumerate(case["arms"][arm], 1)]
        pages.sort(key=lambda page: (page["case"], page["arm"], page["run"]))
        write_json(out / "pages.json", {
            "claude_version": result.get("claudeVersion"),
            "started_at": result.get("startedAt"), "pages": pages,
            "totals": {arm: arm_totals(pages, arm) for arm in ARMS},
        })
    except (OSError, ValueError):
        print("Cannot write measurement output.", file=sys.stderr)
        return 2
    return 0 if all(page["status"] == "measured" for page in pages) else 2


if __name__ == "__main__":
    sys.exit(main())
