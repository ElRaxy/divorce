#!/usr/bin/env python3
"""Build a deterministic, frame-controlled replay from two stream-json traces."""

import argparse
import json
from pathlib import Path, PurePosixPath
import re


ROOT = Path(__file__).resolve().parent
UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", re.I)
ABSOLUTE = re.compile(
    r'''(?P<url>https?://[^\s`"'<>]+)|(?P<path>file://[^\s`"'<>;|&()\[\]{}]*|'''
    r'''(?:(?<![\w~./<])|(?<=-[IL]))(?:[A-Za-z]:[\\/]|\\\\|/)[^\s`"'<>;|&()\[\]{}]*)''')
IDENTIFIERS = re.compile(r"\b(?:session_id|cwd|uuid)\b", re.I)


def sanitize(text):
    def replace_path(match):
        if match.group("url"):
            return match.group()
        name = PurePosixPath(match.group().replace("\\", "/")).name
        return name if "." in name or name in ("vnu", "python3", "gate.py") else "~/project"

    return UUID.sub("[redacted]", ABSOLUTE.sub(replace_path, text))


def validate_public(value):
    """Reject residual paths and metadata before publishing any output."""
    if isinstance(value, dict):
        for key, item in value.items():
            validate_public(key)
            validate_public(item)
    elif isinstance(value, list):
        for item in value:
            validate_public(item)
    elif isinstance(value, str):
        if (any(match.group("path") is not None for match in ABSOLUTE.finditer(value))
                or UUID.search(value) or IDENTIFIERS.search(value)):
            raise ValueError("Replay contains a private path or identifier")


def summarize(name, inputs):
    if name == "Write":
        filename = PurePosixPath(str(inputs.get("file_path", "")).replace("\\", "/")).name
        content = str(inputs.get("content", ""))
        lines = [line.strip() for line in content.splitlines()
                 if re.search(r"<(?:button|dialog)\b", line)]
        if not lines:
            lines = [line.strip() for line in content.splitlines() if line.strip()][:2]
        return sanitize(filename + "\n" + "\n".join(lines[:2]))
    if name == "Skill":
        return sanitize(str(inputs.get("skill", "")) + "\n" + str(inputs.get("args", "")))
    if name == "Bash":
        return sanitize(str(inputs.get("description", "")) + "\n" + str(inputs.get("command", "")))
    return sanitize(json.dumps(inputs, ensure_ascii=False, sort_keys=True))[:240]


def extract_facts(events):
    facts = {"gate_ran": False, "gate_verdict": None, "nu_errors": None,
             "gate_exit": None, "axe_ran": False}
    gate_id, results = None, {}
    for event in events:
        for item in event.get("message", {}).get("content", []):
            if event.get("type") == "assistant" and item.get("type") == "tool_use":
                inputs = item.get("input", {})
                if re.search(r"\baxe\b", json.dumps(inputs, ensure_ascii=False)):
                    facts["axe_ran"] = True
                if item.get("name") == "Bash" and "gate.py" in inputs.get("command", ""):
                    facts["gate_ran"] = True
                    gate_id = item.get("id")
            elif event.get("type") == "user" and item.get("type") == "tool_result":
                results[item.get("tool_use_id")] = item.get("content", "")
    content = results.get(gate_id, "") if gate_id is not None else ""
    if isinstance(content, list):
        content = "\n".join(item.get("text", "") for item in content if item.get("type") == "text")
    exit_match = re.search(r"\bexit\s*[:=]\s*(-?\d+)\s*\Z", content)
    if exit_match:
        facts["gate_exit"] = int(exit_match.group(1))
    start = content.find("{")
    if start >= 0:
        try:
            report, _ = json.JSONDecoder().raw_decode(content[start:])
        except ValueError:
            report = None
        if isinstance(report, dict):
            verdict = report.get("verdict")
            if isinstance(verdict, str):
                facts["gate_verdict"] = verdict
            html = report.get("html")
            if (isinstance(html, list) and all(isinstance(item, dict)
                    and type(item.get("errors")) is int for item in html)):
                facts["nu_errors"] = sum(item["errors"] for item in html)
    return facts


def footer(facts):
    if facts["gate_ran"]:
        text = (f'gate: {facts["gate_verdict"] or "null"} · '
                f'Nu errors: {json.dumps(facts["nu_errors"])} · exit {json.dumps(facts["gate_exit"])}')
    else:
        text = "gate: not run"
    if not facts["axe_ran"]:
        text += " · axe: not run"
    return text, facts["gate_verdict"] == "pass" and facts["gate_exit"] == 0


def read_trace(path):
    steps, final = [], ""
    events = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]
    for event in events:
        if event.get("type") == "assistant":
            for item in event.get("message", {}).get("content", []):
                if item.get("type") == "tool_use":
                    name = item["name"]
                    steps.append({"tool": name, "summary": summarize(name, item.get("input", {}))})
                elif item.get("type") == "text":
                    final = item.get("text", "")
        elif event.get("type") == "result" and isinstance(event.get("result"), str):
            final = event["result"]
    if not steps or not final:
        raise ValueError("Trace needs recorded tool steps and a final message")
    facts = extract_facts(events)
    if facts["gate_verdict"] is not None:
        facts["gate_verdict"] = sanitize(facts["gate_verdict"])
    text, ok = footer(facts)
    result = {"steps": steps, "final": sanitize(final), "facts": facts,
              "footer": {"text": sanitize(text), "ok": ok}}
    validate_public(result)
    return result


TEMPLATE = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>divorce — two recorded runs</title>
<style>
@font-face { font-family: 'Geist'; font-weight: 400;
  font-style: normal; font-display: block;
  src: url("../fonts/geist-sans-latin-400-normal.woff2") format("woff2"); }
@font-face { font-family: 'Geist'; font-weight: 500;
  font-style: normal; font-display: block;
  src: url("../fonts/geist-sans-latin-500-normal.woff2") format("woff2"); }
@font-face { font-family: 'Geist'; font-weight: 600;
  font-style: normal; font-display: block;
  src: url("../fonts/geist-sans-latin-600-normal.woff2") format("woff2"); }
@font-face { font-family: 'Geist'; font-weight: 700;
  font-style: normal; font-display: block;
  src: url("../fonts/geist-sans-latin-700-normal.woff2") format("woff2"); }
@font-face { font-family: 'Geist Mono'; font-weight: 400;
  font-style: normal; font-display: block;
  src: url("../fonts/geist-mono-latin-400-normal.woff2") format("woff2"); }
@font-face { font-family: 'Geist Mono'; font-weight: 500;
  font-style: normal; font-display: block;
  src: url("../fonts/geist-mono-latin-500-normal.woff2") format("woff2"); }
:root { color-scheme: dark; --bg: #0d1117; --surface: #161b22;
  --surface-2: #1c2128; --hairline: rgba(240,246,252,0.08);
  --text: #f5f5f7; --text-2: #a1a1a6; --text-3: #6e6e73;
  --green: #30d158; --red: #ff453a;
  --red-tint: rgba(255,69,58,0.12); --green-tint: rgba(48,209,88,0.12); }
* { box-sizing: border-box; }
html { background: var(--bg); }
body { width: 880px; height: 500px; margin: 0; background: var(--bg);
  color: var(--text); font: 400 17px/1.45 'Geist', sans-serif;
  letter-spacing: 0; text-align: center; }
main { height: 500px; padding: 24px 64px 16px; background: var(--bg); }
h1 { margin: 0 0 24px; font-size: 28px; line-height: 1.08;
  font-weight: 700; letter-spacing: -0.025em; }
.split { display: grid; grid-template-columns: repeat(2, 368px); gap: 16px;
  justify-content: center; }
.terminal { height: 374px; background: var(--surface); border: 1px solid var(--hairline);
  border-radius: 20px; padding: 24px; display: flex; flex-direction: column;
  min-width: 0; }
h2 { margin: 0 0 16px; color: #86868b; font-size: 13px; line-height: 1.2;
  font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
.steps { margin: 0; padding: 0; list-style: none; }
.steps li { display: grid; grid-template-columns: max-content minmax(0, 1fr);
  align-items: center; gap: 8px; }
.steps li + li { margin-top: 16px; }
.tool { color: var(--text); background: var(--surface-2); border-radius: 6px;
  padding: 2px 8px; font: 400 13px/1.5 'Geist Mono', monospace; letter-spacing: 0; }
pre { margin: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  color: var(--text-2); font: 400 14px/1.45 'Geist', sans-serif; letter-spacing: 0; }
.final { font-size: 15px; line-height: 1.45; margin: 16px 0 0; color: var(--text);
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2;
  overflow: hidden; }
.status { margin: auto 0 0; padding: 8px; border-radius: 16px;
  font-size: 13px; line-height: 1.45; font-weight: 400; }
.status:empty { display: none; }
.status-fail { color: var(--red); background: var(--red-tint); }
.status-pass { color: var(--green); background: var(--green-tint); }
footer { color: #86868b; font-size: 13px; line-height: 1.2;
  margin-top: 16px; text-align: center; }
</style>
</head>
<body>
<main>
<h1>Same task. Two recorded runs.</h1>
<div class="split">
<section class="terminal" aria-labelledby="without-title">
<h2 id="without-title">WITHOUT DIVORCE</h2>
<ol class="steps" id="without-steps"></ol>
<p class="final" id="without-final"></p>
<p class="status" id="without-status"></p>
</section>
<section class="terminal" aria-labelledby="with-title">
<h2 id="with-title">WITH DIVORCE</h2>
<ol class="steps" id="with-steps"></ol>
<p class="final" id="with-final"></p>
<p class="status" id="with-status"></p>
</section>
</div>
<footer>Two recorded runs of the modal task, same prompt and model, no browser.</footer>
</main>
<script id="replay-data" type="application/json">__DATA__</script>
<script>
const runs = JSON.parse(document.getElementById('replay-data').textContent);
window.FRAMES = 75;
window.setFrame = function (n) {
  const frame = Math.max(0, Math.min(window.FRAMES - 1, Math.floor(Number(n) || 0)));
  for (const arm of ['without', 'with']) {
    const run = runs[arm];
    const list = document.getElementById(arm + '-steps');
    list.replaceChildren();
    run.steps.forEach(function (step, index) {
      if (frame < 6 + index * 8) return;
      const row = document.createElement('li');
      const label = document.createElement('span');
      label.className = 'tool';
      label.textContent = '$ ' + step.tool;
      const input = document.createElement('pre');
      const lines = step.summary.split('\\n');
      if (step.tool === 'Write') {
        input.textContent = lines[0] + '\\n' + lines.slice(1).map(line =>
          line.length > 47 ? line.slice(0, 46) + '…' : line).join('\\n');
      } else if (step.tool === 'Bash') {
        input.textContent = lines[0] + '\\n' + (lines[1].length > 47 ? lines[1].slice(0, 46) + '…' : lines[1]);
      } else {
        input.textContent = lines[0];
      }
      row.append(label, input);
      list.append(row);
    });
    const complete = frame >= 52;
    const firstSentence = run.final.match(/^.*?[.!?](?:\\s|$)/s);
    document.getElementById(arm + '-final').textContent = complete
      ? (firstSentence ? firstSentence[0].trim() : run.final) : '';
    const status = document.getElementById(arm + '-status');
    status.textContent = complete ? run.footer.text : '';
    status.className = 'status ' + (run.footer.ok ? 'status-pass' : 'status-fail');
  }
};
window.setFrame(0);
</script>
</body>
</html>
'''


def build(with_trace=None, without_trace=None, out_dir=ROOT):
    if (with_trace is None) != (without_trace is None):
        raise ValueError("Provide both traces or neither")
    if with_trace is None:
        runs = {arm: json.loads((ROOT / "data" / f"modal-{arm}.json").read_text(encoding="utf-8"))
                for arm in ("with", "without")}
        for run in runs.values():
            text, ok = footer(run["facts"])
            run["footer"] = {"text": sanitize(text), "ok": ok}
    else:
        runs = {"with": read_trace(with_trace), "without": read_trace(without_trace)}
    payload = json.dumps(runs, ensure_ascii=False, sort_keys=True).replace("<", "\\u003c")
    page = TEMPLATE.replace("__DATA__", payload)
    # Validate the public data before any output is replaced.
    validate_public(runs)
    out_dir = Path(out_dir)
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    for arm, run in runs.items():
        (out_dir / "data" / f"modal-{arm}.json").write_text(
            json.dumps(run, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "replay.html").write_text(page, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("with_trace", type=Path, nargs="?", help="Recorded run with the skill")
    parser.add_argument("without_trace", type=Path, nargs="?", help="Recorded run without the skill")
    parser.add_argument("--out-dir", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        build(args.with_trace, args.without_trace, args.out_dir)
    except (OSError, ValueError, TypeError, KeyError):
        parser.error("Invalid trace or unsafe replay data; no replay was published")
    print("Built data/modal-with.json, data/modal-without.json and replay.html")


if __name__ == "__main__":
    main()
