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
KEYBOARD_REGISTRY = "__divorce_keyboard_listeners"
NAVIGATION_PATTERN = (
    r"\blocation\s*=(?!=)|\blocation\.(?:href|pathname|search)\s*=(?!=)|"
    r"\blocation\.(?:assign|replace)\s*\(|\bwindow\.open\s*\("
)
KEYBOARD_ROLES = (
    "button", "link", "checkbox", "radio", "switch", "tab", "menuitem",
    "menuitemcheckbox", "menuitemradio", "option", "combobox", "slider",
    "spinbutton", "textbox", "treeitem",
)


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


def parse_capture(text):
    payload = parse_json(text)
    # agent-browser encodes the string returned by an eval one more time.
    if isinstance(payload, str):
        payload = parse_json(payload)
        if isinstance(payload, str):
            raise ValueError("Too many JSON string layers")
    return payload


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
        payload = parse_capture(text)
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


def keyboard_init():
    return """(() => {
  // divorce-keyboard: load before the page's scripts.
  const key = %s;
  if (window[key] instanceof WeakMap) return;
  const registry = new WeakMap();
  const original = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function(type, listener, options) {
    const result = original.apply(this, arguments);
    if (listener != null &&
        ['click', 'mousedown', 'mouseup', 'pointerdown', 'pointerup'].includes(type) &&
        this instanceof Element && !['html', 'body'].includes(this.localName)) {
      if (!registry.has(this)) registry.set(this, []);
      try {
        registry.get(this).push(String(typeof listener === 'function'
          ? listener : listener.handleEvent).slice(0, 2000));
      } catch (error) {}
    }
    return result;
  };
  window[key] = registry;
})()""" % json.dumps(KEYBOARD_REGISTRY)


def keyboard_snippet():
    return r"""(async () => {
  try {
    const registry = window[%s];
    const listenersTracked = registry instanceof WeakMap;
    const navigation = new RegExp(%s);
    const nativeSelector = 'a[href], area[href], button, input:not([type=hidden]), ' +
      'select, textarea, summary, iframe, [contenteditable]:not([contenteditable=false])';
    const selector = nativeSelector + ', [tabindex], ' +
      %s.map(role => '[role=' + role + ']').join(', ');
    const groups = '[role=tablist],[role=menu],[role=menubar],[role=toolbar],' +
      '[role=listbox],[role=radiogroup],[role=tree],[role=grid],[role=treegrid]';
    const visible = el => typeof el.checkVisibility === 'function'
      ? el.checkVisibility({visibilityProperty: true})
      : el.getClientRects().length > 0 &&
        !['hidden', 'collapse'].includes(getComputedStyle(el).visibility);
    const disabled = el => el.disabled === true || el.getAttribute('aria-disabled') === 'true';
    const hasFocusable = el => Array.from(el.querySelectorAll('*')).some(child =>
      child.tabIndex >= 0 && visible(child) && !disabled(child));
    const elements = [];
    for (const el of document.querySelectorAll('*')) {
      const tag = el.localName.toLowerCase();
      if (tag === 'html' || tag === 'body') continue;
      const click = [];
      const sources = [];
      if (el.hasAttribute('onclick')) {
        click.push('attribute');
        sources.push(el.getAttribute('onclick'));
      }
      if (typeof el.onclick === 'function') {
        click.push('property');
        try { sources.push(String(el.onclick)); } catch (error) {}
      }
      if (listenersTracked && registry.has(el)) {
        click.push('listener');
        sources.push(...registry.get(el));
      }
      const control = el.matches(selector);
      if (!control && click.length === 0) continue;
      const group = el.closest(groups);
      elements.push({
        tag, role: el.getAttribute('role'), id: el.getAttribute('id'),
        text: (el.getAttribute('aria-label') || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 60),
        native: el.matches(nativeSelector), control, click,
        navigates: sources.some(source => navigation.test(source)), visible: visible(el),
        tab_index: el.tabIndex, disabled: disabled(el),
        inert: el.closest('[inert]') !== null,
        aria_hidden: el.closest('[aria-hidden=true]') !== null,
        roving: group !== null && hasFocusable(group),
        focusable_descendant: hasFocusable(el)
      });
    }
    return JSON.stringify({tool: 'divorce-keyboard', version: 1,
      listeners_tracked: listenersTracked, elements});
  } catch (error) {
    return JSON.stringify({error: String(error)});
  }
})()""" % (json.dumps(KEYBOARD_REGISTRY), json.dumps(NAVIGATION_PATTERN),
            json.dumps(KEYBOARD_ROLES))


def measure_keyboard(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None, ["keyboard_json_missing"]
    except UnicodeError:
        return None, ["keyboard_json_invalid"]
    try:
        payload = parse_capture(text)
        if isinstance(payload, dict) and "error" in payload:
            return None, ["keyboard_snippet_error"]
        if (not isinstance(payload, dict) or
                set(payload) != {"tool", "version", "listeners_tracked", "elements"} or
                payload["tool"] != "divorce-keyboard" or
                type(payload["version"]) is not int or payload["version"] != 1 or
                type(payload["listeners_tracked"]) is not bool or
                not isinstance(payload["elements"], list)):
            raise ValueError("Invalid keyboard capture")
        boolean_fields = ("native", "control", "visible", "disabled", "inert",
                          "aria_hidden", "roving", "focusable_descendant", "navigates")
        keys = {"tag", "role", "id", "text", "click", "tab_index", *boolean_fields}
        facts = {
            "listeners_tracked": payload["listeners_tracked"],
            "controls_visible": 0, "in_tab_order": 0, "out_of_tab_order": [],
            "click_unreachable": [], "role_unreachable": [],
            "navigating_buttons": [],
            "not_measured": ["tab_sequence", "enter_space_activation", "escape",
                             "focus_return", "focus_visible"],
        }
        for record in payload["elements"]:
            if (not isinstance(record, dict) or set(record) != keys or
                    any(type(record[key]) is not bool for key in boolean_fields) or
                    type(record["tab_index"]) is not int or
                    not isinstance(record["tag"], str) or not record["tag"] or
                    record["tag"] != record["tag"].lower() or
                    not isinstance(record["text"], str) or
                    any(record[key] is not None and not isinstance(record[key], str)
                        for key in ("role", "id")) or
                    not isinstance(record["click"], list) or
                    any(not isinstance(value, str) or value not in
                        ("attribute", "property", "listener") for value in record["click"]) or
                    len(set(record["click"])) != len(record["click"])):
                raise ValueError("Invalid keyboard element")
            summary = {key: record[key] for key in ("tag", "role", "id", "text")}
            in_tab_order = (record["visible"] and record["tab_index"] >= 0 and
                            not record["disabled"] and not record["inert"])
            facts["controls_visible"] += int(record["visible"] and record["control"])
            facts["in_tab_order"] += int(in_tab_order)
            if record["visible"] and record["navigates"] and (
                    record["tag"] in ("button", "input") or record["role"] == "button"):
                facts["navigating_buttons"].append(summary)
            # Inert content can be neither clicked nor focused: it is out of play, not unreachable.
            if (not record["visible"] or record["disabled"] or record["aria_hidden"] or
                    record["inert"]):
                continue
            if record["control"] and record["tab_index"] < 0:
                facts["out_of_tab_order"].append(summary)
            if in_tab_order or record["roving"]:
                continue
            if record["click"] and not record["focusable_descendant"] and record["tag"] != "label":
                facts["click_unreachable"].append(summary)
            if not record["native"] and record["role"] in KEYBOARD_ROLES:
                facts["role_unreachable"].append(summary)
        return facts, []
    except (ValueError, TypeError, KeyError, RecursionError):
        return None, ["keyboard_json_invalid"]


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
    if args.command == "keyboard" or (args.command == "check" and args.keyboard is not None):
        result["keyboard"], errors = measure_keyboard(args.keyboard)
        infra.extend(errors)
        if result["keyboard"] is not None:
            for kind in ("click_unreachable", "role_unreachable"):
                count = len(result["keyboard"][kind])
                if count:
                    failures.append(f"keyboard_{kind}:{count}")
            count = len(result["keyboard"]["navigating_buttons"])
            if count:
                result["warnings"] = [f"keyboard_button_navigates:{count}"]
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
    commands.add_parser("keyboard-init", help="Print the listener tracking init script")
    commands.add_parser("keyboard-snippet", help="Print JavaScript to collect keyboard facts")
    keyboard = commands.add_parser("keyboard", help="Read keyboard facts from a rendered page")
    keyboard.add_argument("keyboard", metavar="JSON_FILE")
    check = commands.add_parser("check", help="Combine HTML and axe measurements")
    check.add_argument("--html", nargs="+", required=True, metavar="FILE_OR_URL")
    check.add_argument("--axe", required=True, metavar="JSON_FILE")
    check.add_argument("--keyboard", metavar="JSON_FILE")
    for command in (axe, check):
        command.add_argument("--axe-max-impact", choices=("serious", "moderate", "minor"),
                             default="serious", help="Fail at this impact or higher (default: serious)")
    args = parser.parse_args()
    if args.command == "axe-snippet":
        print(axe_snippet())
        return 0
    if args.command == "keyboard-init":
        print(keyboard_init())
        return 0
    if args.command == "keyboard-snippet":
        print(keyboard_snippet())
        return 0
    result, code = evaluate(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
