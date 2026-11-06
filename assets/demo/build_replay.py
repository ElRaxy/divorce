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


def read_trace(path):
    steps, final = [], ""
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
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
    result = {"steps": steps, "final": sanitize(final)}
    validate_public(result)
    return result


TEMPLATE = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>divorce — two recorded runs</title>
<style>
@font-face { font-family: 'Bricolage Grotesque'; font-weight: 700;
  font-style: normal; font-display: block;
  src: url("../fonts/bricolage-grotesque-latin-700-normal.woff2") format("woff2"); }
@font-face { font-family: 'Bricolage Grotesque'; font-weight: 800;
  font-style: normal; font-display: block;
  src: url("../fonts/bricolage-grotesque-latin-800-normal.woff2") format("woff2"); }
@font-face { font-family: 'JetBrains Mono'; font-weight: 400;
  font-style: normal; font-display: block;
  src: url("../fonts/jetbrains-mono-latin-400-normal.woff2") format("woff2"); }
@font-face { font-family: 'JetBrains Mono'; font-weight: 700;
  font-style: normal; font-display: block;
  src: url("../fonts/jetbrains-mono-latin-700-normal.woff2") format("woff2"); }
:root { color-scheme: dark; --bg: #0b0b0c; --card: #141416; --line: #26262a;
  --text: #f4f4f5; --muted: #9a9aa2; --red: #ff4d4d; --green: #3ddc84; }
* { box-sizing: border-box; }
html { background: var(--bg); }
body { width: 880px; height: 500px; margin: 0; background: var(--bg);
  color: var(--text); font: 12px/1.4 'JetBrains Mono', monospace; }
main { height: 500px; padding: 22px 24px 16px; }
h1 { margin: 0 0 14px; font: 800 22px/1 'Bricolage Grotesque', sans-serif;
  letter-spacing: -.045em; }
.split { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.terminal { height: 397px; background: var(--card); border: 1px solid var(--line);
  border-radius: 12px; padding: 14px; display: flex; flex-direction: column; }
h2 { margin: 0 0 12px; font: 700 12px/18px 'JetBrains Mono', monospace;
  letter-spacing: .08em; }
.steps { margin: 0; padding: 0; list-style: none; }
.steps li { margin-bottom: 8px; display: grid;
  grid-template-columns: 42px minmax(0, 1fr); gap: 8px; }
.tool { color: var(--muted); font-weight: 700; }
pre { margin: 1px 0 0; white-space: pre-wrap; overflow-wrap: anywhere;
  font: 11px/14px 'JetBrains Mono', monospace; }
.final { font-size: 11px; line-height: 15px; margin: 6px 0 0; }
.status { margin: auto 0 0; border-top: 1px solid var(--line); padding-top: 10px;
  font-size: 11px; font-weight: 700; }
.red { color: var(--red); } .green { color: var(--green); }
footer { color: var(--muted); font-size: 10px; margin-top: 14px; text-align: center; }
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
<p class="status red" id="without-status"></p>
</section>
<section class="terminal" aria-labelledby="with-title">
<h2 id="with-title">WITH DIVORCE</h2>
<ol class="steps" id="with-steps"></ol>
<p class="final" id="with-final"></p>
<p class="status green" id="with-status"></p>
</section>
</div>
<footer>Replay of two recorded runs from the benchmark (same task, same model).</footer>
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
    document.getElementById(arm + '-status').textContent = complete
      ? (arm === 'without' ? 'claimed done · checks: none' : 'checks: not_measured · not claimed') : '';
  }
};
window.setFrame(0);
</script>
</body>
</html>
'''


def build(with_trace, without_trace, out_dir=ROOT):
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
    parser.add_argument("with_trace", type=Path, help="Recorded run with the skill")
    parser.add_argument("without_trace", type=Path, help="Recorded run without the skill")
    parser.add_argument("--out-dir", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        build(args.with_trace, args.without_trace, args.out_dir)
    except (OSError, ValueError, TypeError, KeyError):
        parser.error("Invalid trace or unsafe replay data; no replay was published")
    print("Built data/modal-with.json, data/modal-without.json and replay.html")


if __name__ == "__main__":
    main()
