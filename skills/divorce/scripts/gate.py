#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 divorce contributors
# Integrates validator/validator (MIT) and axe-core (MPL-2.0).
"""Report deterministic HTML and accessibility checks as JSON."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlsplit


AXE_VERSION = "4.10.2"
VALIDATOR_TIMEOUT = 60
IMPACTS = ("critical", "serious", "moderate", "minor")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError("Invalid JSON constant")


def parse_json(text):
    return json.loads(text, object_pairs_hook=unique_object,
                      parse_constant=invalid_constant)


def validator_command():
    for candidate in (os.environ.get("VNU"), "vnu"):
        if candidate:
            executable = shutil.which(candidate)
            if executable:
                return [executable]
    jar = os.environ.get("VNU_JAR")
    java = shutil.which("java")
    if jar and java and Path(jar).is_file():
        return [java, "-jar", str(Path(jar).absolute())]
    return None


def coordinate(message, last, first):
    value = message.get(last, message.get(first))
    if value is not None and (type(value) is not int or value < 1):
        raise ValueError("Invalid message position")
    return value


def html_messages(payload, entry):
    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
        raise ValueError("Invalid validator response")
    root_url = payload.get("url", entry)
    if not isinstance(root_url, str) or not root_url:
        raise ValueError("Invalid document URL")
    groups = {}
    unreachable = False
    for message in payload["messages"]:
        if not isinstance(message, dict):
            raise ValueError("Invalid validator message")
        kind = message.get("type")
        if kind not in ("error", "info", "non-document-error"):
            raise ValueError("Unknown validator message type")
        text = message.get("message")
        extract = message.get("extract", "")
        url = message.get("url", root_url)
        if not all(isinstance(value, str) for value in (text, extract, url)) or not url:
            raise ValueError("Invalid validator message fields")
        # Each validator invocation measures only the supplied entry.
        group = groups.setdefault(entry, {
            "input": entry, "errors": 0, "warnings": 0, "messages": [],
        })
        group["errors"] += int(kind == "error")
        group["warnings"] += int(kind == "info" and message.get("subType") == "warning")
        unreachable = unreachable or kind == "non-document-error"
        group["messages"].append({
            "type": kind, "message": text,
            "line": coordinate(message, "lastLine", "firstLine"),
            "column": coordinate(message, "lastColumn", "firstColumn"),
            "extract": extract[:200],
        })
    if not groups:
        groups[entry] = {"input": entry, "errors": 0,
                         "warnings": 0, "messages": []}
    return list(groups.values()), unreachable


def measure_html(entries):
    command = validator_command()
    if command is None:
        return [], ["validator_missing"]
    facts, infra = [], []
    for entry in entries:
        try:
            # Absolute paths prevent filenames from becoming validator options.
            target = entry if urlsplit(entry).scheme else str(Path(entry).absolute())
            process = subprocess.run(
                command + ["--format", "json", "--exit-zero-always", target],
                capture_output=True, text=True, encoding="utf-8",
                timeout=VALIDATOR_TIMEOUT, check=False,
            )
            if process.returncode != 0:
                infra.append("validator_failed")
            groups, unreachable = html_messages(parse_json(process.stderr), entry)
            facts.extend(groups)
            if unreachable:
                infra.append("input_unreachable")
        except (OSError, ValueError, TypeError, RecursionError, subprocess.TimeoutExpired):
            infra.append("validator_failed")
    return facts, infra


def node_count(rule):
    counts = []
    if "nodes" in rule:
        if not isinstance(rule["nodes"], list):
            raise ValueError("Invalid node list")
        counts.append(len(rule["nodes"]))
    for key in ("node_count", "n"):
        if key in rule:
            value = rule[key]
            if type(value) is not int or value < 0:
                raise ValueError("Invalid node count")
            counts.append(value)
    if not counts or len(set(counts)) != 1:
        raise ValueError("Missing or inconsistent node counts")
    return counts[0]


def measure_axe(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None, ["axe_json_missing"]
    except UnicodeError:
        return None, ["axe_json_invalid"]
    try:
        payload = parse_json(text)
        if isinstance(payload, dict) and "error" in payload:
            if payload["error"] == "axe_version_mismatch":
                return None, ["axe_version_mismatch"]
            return None, ["axe_snippet_error"]
        violations = payload.get("violations") if isinstance(payload, dict) else payload
        if not isinstance(violations, list):
            raise ValueError("Missing violations list")
        rules = []
        totals = {impact: 0 for impact in IMPACTS}
        totals["null"] = 0
        for rule in violations:
            if not isinstance(rule, dict):
                raise ValueError("Invalid axe rule")
            identifier = rule.get("id")
            impact = rule["impact"]
            tags = rule.get("tags", [])
            if not isinstance(identifier, str) or not identifier:
                raise ValueError("Invalid rule ID")
            if impact is not None and impact not in IMPACTS:
                raise ValueError("Unknown impact")
            if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
                raise ValueError("Invalid tags")
            rules.append({"id": identifier, "impact": impact,
                          "nodes": node_count(rule), "tags": tags})
            totals[impact if impact is not None else "null"] += 1
        infra = ["axe_impact_unknown"] if totals["null"] else []
        return {"rules": rules, "totals": totals}, infra
    except (ValueError, TypeError, KeyError, RecursionError):
        return None, ["axe_json_invalid"]


def axe_snippet():
    url = f"https://cdnjs.cloudflare.com/ajax/libs/axe-core/{AXE_VERSION}/axe.min.js"
    return """(async () => {
  const EXPECTED = %s;
  if (!(window.axe && window.axe.version === EXPECTED)) {
    await new Promise((resolve, reject) => {
      const script = document.createElement('script');
      const timer = setTimeout(() => {
        script.remove();
        reject(new Error('axe-core load timed out'));
      }, 15000);
      script.src = %s;
      script.onload = () => { clearTimeout(timer); resolve(); };
      script.onerror = () => {
        clearTimeout(timer);
        script.remove();
        reject(new Error('axe-core could not be loaded'));
      };
      (document.head || document.documentElement).appendChild(script);
    });
  }
  if (!window.axe || typeof window.axe.run !== 'function' || window.axe.version !== EXPECTED) {
    return JSON.stringify({error: "axe_version_mismatch", expected: EXPECTED,
      found: window.axe && window.axe.version != null ? window.axe.version : null});
  }
  const result = await window.axe.run(document, {
    runOnly: {type: 'tag', values: [
      'wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'
    ]}
  });
  return JSON.stringify(result.violations.map(v => ({
    id: v.id, impact: v.impact, tags: v.tags, n: v.nodes.length
  })));
})()""" % (json.dumps(AXE_VERSION), json.dumps(url))


def evaluate(args):
    result, infra, failures = {}, [], []
    if args.command in ("html", "check"):
        result["html"], errors = measure_html(args.html)
        infra.extend(errors)
        if any(entry["errors"] for entry in result["html"]):
            failures.append("html_errors")
    if args.command in ("axe", "check"):
        result["axe"], errors = measure_axe(args.axe)
        infra.extend(errors)
        if result["axe"] is not None:
            blocked = IMPACTS[:IMPACTS.index(args.axe_max_impact) + 1]
            totals = result["axe"]["totals"]
            if any(totals[impact] for impact in blocked):
                failures.append("axe_violations:" + ",".join(
                    f"{impact}={totals[impact]}" for impact in blocked))
    code = 2 if infra else 1 if failures else 0
    result["verdict"] = {0: "pass", 1: "fail", 2: "not_measured"}[code]
    result["reasons"] = list(dict.fromkeys(infra + failures))
    return result, code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    html = commands.add_parser("html", help="Validate HTML files or URLs")
    html.add_argument("html", nargs="+", metavar="FILE_OR_URL")
    axe = commands.add_parser("axe", help="Read an axe.run result or violations list")
    axe.add_argument("axe", metavar="JSON_FILE")
    commands.add_parser("axe-snippet", help="Print JavaScript for agent-browser eval")
    check = commands.add_parser("check", help="Combine HTML and axe measurements")
    check.add_argument("--html", nargs="+", required=True, metavar="FILE_OR_URL")
    check.add_argument("--axe", required=True, metavar="JSON_FILE")
    for command in (axe, check):
        command.add_argument("--axe-max-impact", choices=("serious", "moderate", "minor"),
                             default="serious", help="Fail at this impact or higher (default: serious)")
    args = parser.parse_args()
    if args.command == "axe-snippet":
        print(axe_snippet())
        return 0
    result, code = evaluate(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
