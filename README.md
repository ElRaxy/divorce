# divorce

> Your agent is in a toxic relationship with `<div>`. It's not you, it's the spec.

A skill for web developers using coding agents such as Claude Code and Codex. Before writing, it guides the agent toward the smallest native HTML/CSS/JS/ARIA solution that follows web standards. Before calling the work done, a deterministic gate checks served HTML with Nu HTML Checker and the rendered DOM with axe-core. Exit 0: pass. Exit 1: fail. Exit 2: not measured. Missing evidence never counts as a pass.

## A 30-second before / after

Start with [heading-order](examples/heading-order/before.html). An `<h3>` follows an `<h1>`. The [fix](examples/heading-order/after.html) changes it to `<h2>`.

Real `gate.py` output with Nu HTML Checker 26.11.4 is shown below. `input` preserves the supplied relative path.

```sh
python3 skills/divorce/scripts/gate.py html examples/heading-order/before.html
```

```json
{
  "html": [
    {
      "input": "examples/heading-order/before.html",
      "errors": 1,
      "warnings": 0,
      "messages": [
        {
          "type": "error",
          "message": "The heading “h3” (with computed level 3) follows the heading “h1” (with computed level 1), skipping 1 heading level.",
          "line": 10,
          "column": 6,
          "extract": "de</h1>\n  <h3>Delive"
        }
      ]
    }
  ],
  "verdict": "fail",
  "reasons": [
    "html_errors"
  ]
}
```

Exit: 1.

```sh
python3 skills/divorce/scripts/gate.py html examples/heading-order/after.html
```

```json
{
  "html": [
    {
      "input": "examples/heading-order/after.html",
      "errors": 0,
      "warnings": 0,
      "messages": []
    }
  ],
  "verdict": "pass",
  "reasons": []
}
```

Exit: 0.

The second example saves a draft and displays its status. These lines come from [before.html](examples/div-button/before.html) and [after.html](examples/div-button/after.html).

Before:

```html
<div onclick="document.getElementById('result').textContent = 'Saved'">Save</div>
```

After:

```html
<button type="button" onclick="document.getElementById('result').textContent = 'Saved'">Save</button>
```

The HTML validator passes both documents. Their difference appears in accessibility checks with axe and manual keyboard tests. The button supplies native semantics and keyboard activation; the plain div does not. Automated checks do not reliably infer that this div should be a button.

Actual `gate.py` output with the fake `vnu` in [test_gate.py](tests/test_gate.py), selected through `VNU`, is shown below in compact form. The fake returns no messages for these files. This checks the output contract, not HTML validity.

```sh
python3 skills/divorce/scripts/gate.py html examples/div-button/before.html
```

```json
{"html": [{"input": "examples/div-button/before.html", "errors": 0, "warnings": 0, "messages": []}], "verdict": "pass", "reasons": []}
```

Exit: 0.

```sh
python3 skills/divorce/scripts/gate.py html examples/div-button/after.html
```

```json
{"html": [{"input": "examples/div-button/after.html", "errors": 0, "warnings": 0, "messages": []}], "verdict": "pass", "reasons": []}
```

Exit: 0. No axe, keyboard or visual check was run for this demonstration. No axe output is claimed. See the [example notes](examples/README.md).

## What it does

**Before writing:** stop at the first adequate solution in the ladder.

1. Is it needed? If not, omit it.
2. Does the project already have it? Reuse it.
3. Is there a native element for it?
4. Can CSS do it without JavaScript?
5. Does an installed dependency cover it?
6. Only then, write the minimum that works. Add a small test for logic.

Pick elements by their behavior:

| Behavior | Element |
| --- | --- |
| Perform an action | `<button type="button">` |
| Navigate | `<a href>` |
| Disclose related content | `<details>` / `<summary>` |
| Open a temporary task on top | `<dialog>` or the Popover API |
| Collect input | Native controls in `<form>`, each with a `<label>` |

ARIA refines native semantics. Accessibility, boundary validation and handling errors that could lose data stay in place. The [skill](skills/divorce/SKILL.md) also guides CSS, state styling and the distinction between specifications and conventions.

**Before finishing:** Nu checks served HTML. axe-core checks the rendered DOM using WCAG 2.2 A/AA tags, including earlier WCAG versions, plus best-practice rules. The gate reads their evidence and applies a fixed policy. Serious and critical axe violations fail by default.

## What it is not

It is not a component library, a CSS validator, a JavaScript correctness check, a performance audit or a design review. It does not prove full WCAG conformance. Manual keyboard, focus and visual checks remain necessary. The gate cannot enforce every decision in the writing ladder.

## Install

Choose one route. Shell commands below run from the root of an existing divorce checkout.

### Claude Code plugin

```text
/plugin marketplace add ElRaxy/divorce
/plugin install divorce@divorce
```

Those names come from the [plugin manifest](.claude-plugin/plugin.json) and [marketplace manifest](.claude-plugin/marketplace.json). Validator setup is separate.

### Manual copy or standalone installer

Copy the entire `skills/divorce/` directory, including its scripts, to `~/.claude/skills/divorce/`. The standalone installer performs that copy and records the installation:

```sh
sh install.sh --claude
```

For a single Claude project, use `--project DIR` with `--claude`. Its destination is `DIR/.claude/skills/divorce/`.

### Codex

```sh
sh install.sh --codex
```

This copies the skill to `~/.codex/skills/divorce/`. `--project` is supported only for Claude.

### Other agents

Pass the path to the instruction file your agent reads:

```sh
sh install.sh --agents-md AGENTS.md
```

This appends or replaces a marked instruction block. It points to the gate by its absolute path in the checkout. Keep the checkout in place. See the [FAQ](docs/faq.md#does-installing-it-make-the-gate-run-itself) for update and removal behavior.

The standalone installer does not register a plugin, install validators or add an automatic gate hook.

## Use in four commands

First prepare Nu separately:

```sh
sh skills/divorce/scripts/install-vnu.sh
```

The installer prints the installed binary path. Set `VNU` to that path, or make `vnu` available on `PATH`. For a JAR installation, use `--jar` and set `VNU_JAR` to the printed JAR path; Java must be available.

With the intended page already loaded in your verification browser session, run:

```sh
python3 skills/divorce/scripts/gate.py html examples/div-button/after.html
agent-browser eval "$(python3 skills/divorce/scripts/gate.py axe-snippet)" > axe.json
python3 skills/divorce/scripts/gate.py axe axe.json
python3 skills/divorce/scripts/gate.py check --html examples/div-button/after.html --axe axe.json --axe-max-impact serious
```

Here the browser must contain the served version of `examples/div-button/after.html`. For your project, replace that input with its served URL or built HTML file. Capture axe evidence from the same page and state. Use your installed skill's script path if working outside the checkout. Browser automation is a separate tool; the gate does not open a page.

## Exit codes

| Exit | JSON verdict | Meaning |
| --- | --- | --- |
| 0 | `pass` | The invoked check passed its configured policy. |
| 1 | `fail` | HTML errors or axe violations at or above the impact threshold. |
| 2 | `not_measured` | Missing tools, unavailable input or unusable evidence. Never a pass. |

A complete gate needs both HTML and axe evidence. An HTML-only pass does not establish an axe pass.

## How the verdict is built

[gate.py](skills/divorce/scripts/gate.py) parses Nu's JSON messages and axe's violations. It counts HTML errors and axe rules by impact. Missing or invalid measurement takes priority and returns 2, even when an observed failure is also present. Otherwise, blocking findings return 1. With neither condition, it returns 0. The model does not choose the verdict.

The JSON retains counts and reasons. axe totals count violated rules; each rule also has an affected-node count. The caller must supply genuine evidence for the intended page. See [how it works](docs/how-it-works.md) for the exact reasons and evidence limits.

## Requirements

- Python 3.9+ for the standalone installer; Python 3 for the gate.
- A shell for the installation scripts.
- Nu HTML Checker: `VNU`, `vnu` on `PATH`, or `VNU_JAR` with Java.
- For Nu setup: network access, `curl`, and `shasum` or `sha1sum`. Native macOS/Linux archives also need `unzip`; `--jar` needs Java. The installer verifies the downloaded SHA-1 and checks the validator's version command.
- A rendered browser page and a way to evaluate the axe snippet. It loads axe-core 4.10.2 from a CDN unless that version is already present. Script loading must be allowed.

## Benchmark

A benchmark is planned. It will compare the same tasks with and without the skill, under the same model and run conditions. Results will include `gate.py` verdicts, raw evidence, failures and unmeasured cases from both groups. The [eval cases](evals/README.md) are a starting point; their model grading is separate from the deterministic gate. No benchmark results are published here.

## FAQ

[Read the FAQ](docs/faq.md) for framework support, automated coverage, source versus served HTML, and spec versus convention. See [CONTRIBUTING.md](CONTRIBUTING.md) for changes and [CHANGELOG.md](CHANGELOG.md) for version history.

## Credits

A cousin of [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail), licensed under MIT. ponytail removes code. divorce makes the code that remains meet the spec. The decision ladder is adapted from ponytail.

Semantic HTML and modern CSS guidance is adapted from kemiljk/skills (MIT). Nu HTML Checker comes from validator/validator (MIT). axe-core is MPL-2.0. Neither validator is bundled here. See [NOTICE](NOTICE) for attribution and component details.

## License

[MIT](LICENSE). Third-party components retain their own licenses as described in [NOTICE](NOTICE).
