<p align="center"><img src="assets/cards/banner.png" width="880" alt="divorce. Native first. Then proven. A skill for Claude Code and Codex."></p>
<p align="center"><a href="#install">Install</a> · <a href="#numbers">Numbers</a> · <a href="#what-validators-miss">What validators miss</a> · <a href="#how-it-works">How it works</a> · <a href="evals/README.md">Evaluation</a></p>

> Your agent writes `<div onclick>`. Every validator says it's fine. Someone using a keyboard can't reach it.
>
> **divorce** makes the agent pick the native element first, then proves it with Nu and axe.
## Install

```text
/plugin marketplace add ElRaxy/divorce
/plugin install divorce@divorce
```
Other agents and install routes: [Details](#details).
## Numbers

|  | HTML | JavaScript | ARIA | axe violations |
| --- | :---: | :---: | :---: | :---: |
| **With divorce** | −29% | −41% | −33% | −76% |

Over 5 runs of 8 tasks. Nu errors: 3 of 40 pages with divorce, 0 of 40 without. Method and limits in [evals](evals/README.md).
## What validators miss

Both of these pass the Nu HTML Checker and axe. Only one can be reached with Tab.

Without divorce:
```html
<div onclick="document.getElementById('result').textContent = 'Saved'">Save</div>
```
With divorce:
```html
<button type="button" onclick="document.getElementById('result').textContent = 'Saved'">Save</button>
```

| Case | Nu | axe |
| --- | --- | --- |
| [Use a link for navigation](examples/button-link/) | — | — |
| [Use details for a disclosure](examples/custom-disclosure/) | — | — |
| [Use dialog for a modal task](examples/custom-modal/) | — | — |
| [Use a button for an action](examples/div-button/) | — | — |
| [Represent a list with ul and li](examples/div-list/) | — | — |
| [Keep heading levels in order](examples/heading-order/) | flags it | flags it (moderate) |
| [Provide an image text alternative](examples/image-alt/) | flags it | flags it (critical) |
| [Associate a label with its control](examples/input-label/) | — | flags it (critical) |
| [Follow document order for focus](examples/positive-tabindex/) | — | flags it (serious) |

5 of 9 pass both checkers. divorce picks the element before anything is checked.
## How it works

1. Does it need to exist? If not, omit it.
2. Does the project already have it? Reuse it.
3. Is there a native HTML element for it? Use it.
4. Can CSS do it without JavaScript?
5. Does an installed dependency cover it?
6. Only then: the smallest code that works, plus a small test for logic.

Then the gate checks the result: Nu on the HTML, axe on the rendered page. Code, not the model, delivers the verdict: `pass`, `fail` or `not_measured` ([exit codes](#details)).

## Details

<details>
<summary>All agents, installation routes and gate commands</summary>

<h3>Evidence</h3>

- See the <a href="evals/README.md">with/without evaluation</a> for the measurements and limits.
- <a href="examples/manifest.json">Case file</a> · <a href="examples/axe-measured.json">Measured axe results</a>: findings and the gate policy determine the ruling.
- <a href="assets/data/gate-real.json">Recorded output</a>: Nu checks HTML, axe checks the rendered DOM, and missing evidence means <code>not_measured</code>, never a pass.
- <a href="assets/demo/replay.gif">Two recorded runs</a> of the same modal task, same prompt and model.

<h3>Install</h3>

Use the plugin commands above in Claude Code, or run one standalone route from an existing checkout's root; validator setup is separate.

- Claude, user-wide: `sh install.sh --claude` — Copies the skill and scripts to `~/.claude/skills/divorce/`, recording the installation.
- Claude, one project: `sh install.sh --claude --project DIR` — Copies to `DIR/.claude/skills/divorce/`.
- Codex: `sh install.sh --codex` — Copies to `~/.codex/skills/divorce/`; `--project` is Claude-only.
- Other agents: `sh install.sh --agents-md AGENTS.md` — Appends or replaces a marked block in the instruction file.

For a manual copy, copy the entire `skills/divorce/` directory, including scripts, to `~/.claude/skills/divorce/`. Instruction blocks point to the gate's absolute path: keep the checkout in place. The standalone installer does not register a plugin, install validators or add an automatic gate hook; copies do not update themselves ([maintenance](docs/faq.md#does-installing-it-make-the-gate-run-itself)).

With the served version of `examples/div-button/after.html` already loaded in your verification browser session:

```sh
python3 skills/divorce/scripts/gate.py html examples/div-button/after.html
agent-browser eval "$(python3 skills/divorce/scripts/gate.py axe-snippet)" > axe.json
python3 skills/divorce/scripts/gate.py axe axe.json
python3 skills/divorce/scripts/gate.py check --html examples/div-button/after.html --axe axe.json --axe-max-impact serious
```

Replace the HTML input with your served URL or built file and capture genuine axe evidence from that same page and state. Outside the checkout, use the installed script path. The gate does not open a browser, run axe or refresh a capture; see [all commands and flags](docs/how-it-works.md#commands).

<h3>FAQ</h3>

Coverage, frameworks and maintenance

A passing gate is not full WCAG conformance, a CSS or JavaScript correctness check, a performance audit or a design review. Manual keyboard, focus, interaction and visual checks remain necessary; accessibility, boundary validation and data-loss handling stay in scope.

- [Frameworks and served HTML](docs/faq.md#can-react-vue-wordpresselementor-and-php-keep-the-house): React, Vue, WordPress/Elementor and PHP.
- [Spec versus convention](docs/faq.md#spec-or-convention-who-gets-the-cursor): cite the spec and preserve project conventions.
- [Benchmark](evals/README.md): five runs; model grading is separate from HTML and axe measurements.
- [Full FAQ](docs/faq.md) · [Skill and element table](skills/divorce/SKILL.md#2-pick-the-element-by-what-it-does) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md).

<h3>Exit codes</h3>

What the verdict covers

- 0: `pass` — The invoked check passed its configured policy.
- 1: `fail` — HTML errors or axe violations at or above the impact threshold.
- 2: `not_measured` — Missing tools, unavailable input or unusable evidence; never a pass.

Missing or invalid measurement takes priority over observed failures. Otherwise, blocking findings fail; with neither condition, the check passes. Serious and critical axe violations fail by default; lower impacts remain visible. HTML warnings do not fail. axe totals count violated rules and each rule records affected nodes.

A complete gate needs HTML and axe evidence; an HTML-only pass says nothing about axe. The caller supplies evidence for the intended page: the gate does not authenticate it or prove it is current ([exact reasons and limits](docs/how-it-works.md)).

<h3>Requirements</h3>

Runtime and validator setup

- Python 3.9+ for the standalone installer; Python 3 for the gate; a shell for installation scripts.
- Nu HTML Checker: `VNU`, `vnu` on `PATH`, or `VNU_JAR` with Java.
- Nu setup needs network access, `curl`, and `shasum` or `sha1sum`; native archives also need `unzip`, while `--jar` needs Java.
- A rendered page and a way to evaluate the axe snippet; it loads axe-core 4.10.2 unless that version is already present, so script loading must be allowed.

```sh
sh skills/divorce/scripts/install-vnu.sh
```

The installer verifies the download's SHA-1 and the validator's version command. Set `VNU` to its printed binary path or add `vnu` to `PATH`; for `--jar`, set `VNU_JAR` to the printed JAR path. The axe snippet selects WCAG 2.2 A/AA, including earlier versions, and best-practice rules.
</details>

<!-- Star History: star-history.com cannot read a private repo and renders a broken image. Uncomment when the repo goes public.
## Star History

<a href="https://star-history.com/#ElRaxy/divorce&Date"><picture><source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=ElRaxy/divorce&amp;type=Date&amp;theme=dark"><img src="https://api.star-history.com/svg?repos=ElRaxy/divorce&amp;type=Date" alt="Star history of ElRaxy/divorce"></picture></a>
-->

## License

[MIT](LICENSE); see [NOTICE](NOTICE) for third-party licenses: the decision ladder is adapted from [ponytail](https://github.com/DietrichGebert/ponytail) (MIT), semantic HTML and modern CSS guidance from [kemiljk/skills](https://github.com/kemiljk/skills) (MIT); Nu is MIT and axe-core is MPL-2.0, and neither validator is bundled.
