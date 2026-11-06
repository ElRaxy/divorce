<p align="center">
  <img src="assets/mascot.png" width="220" alt="A weary div with glasses signing separation papers with a red pen.">
</p>

<h1 align="center">divorce</h1>

<p align="center"><em>End your agent's toxic relationship with div soup. Write native HTML. Let code deliver the verdict.</em></p>

<p align="center">
  <picture><source media="(prefers-color-scheme: dark)" srcset="assets/cards/hero-dark.png"><img src="assets/cards/hero-light.png" width="880" alt="Validators catch 4 of these 9. The other 5 look fine to every tool. A clickable div passes Nu and axe but has no button role and is skipped by Tab. A native button has a button role and is reached by Tab."></picture>
</p>

```text
/plugin marketplace add ElRaxy/divorce
/plugin install divorce@divorce
```

Works with Claude Code and Codex · [other agents →](#install)

## Numbers

<!-- With/without results pending. Add the Numbers card only after measured results exist. -->

## The evidence

<p align="center">
  <picture><source media="(prefers-color-scheme: dark)" srcset="assets/cards/cases-dark.png"><img src="assets/cards/cases-light.png" width="880" alt="5 of 9 invisible to every tool. The first five rows, in red, show nothing detected for button-link, custom-disclosure, custom-modal, div-button and div-list. Nu and axe detect heading-order and image-alt; axe detects input-label and positive-tabindex. Each row lists its recorded axe impact."></picture>
</p>

[Case file](examples/manifest.json) · [Measured axe results](examples/axe-measured.json). A finding is evidence; its impact and the gate policy determine the ruling.

## How it works

Read the code. Stop at the first rung that holds.

1. Does it need to exist? If not, omit it.
2. Does the project already have it? Reuse it.
3. Is there a native HTML element for it? Use it.
4. Can CSS do it without JavaScript?
5. Does an installed dependency cover it?
6. Only then: the smallest code that works, plus a small test for logic.

The [skill and element table](skills/divorce/SKILL.md#2-pick-the-element-by-what-it-does) set the terms. Accessibility, boundary validation and data-loss handling stay.

## The ruling

<p align="center">
  <picture><source media="(prefers-color-scheme: dark)" srcset="assets/cards/ruling-dark.png"><img src="assets/cards/ruling-light.png" width="880" alt="Recorded output / HTML only. Terminal result for the missing-image-alt example: 1 Nu error, 0 warnings. FAIL, reason html_errors, exit=1."></picture>
</p>

These cards are HTML. Validate them with divorce's own HTML gate.

[Recorded output](assets/data/gate-real.json), abbreviated on the card. Nu checks served HTML; axe checks the rendered DOM. Code issues the verdict. Missing evidence means `not_measured`, never a pass.

## Install

Choose one route. Run shell commands from an existing checkout's root. For the Claude Code plugin, use the commands at the top; names come from the [plugin](.claude-plugin/plugin.json) and [marketplace](.claude-plugin/marketplace.json) manifests. Validator setup is separate.

| Route | Command | Destination or effect |
| --- | --- | --- |
| Claude, user-wide | `sh install.sh --claude` | Copies the entire skill and scripts to `~/.claude/skills/divorce/`, recording the installation. |
| Claude, one project | `sh install.sh --claude --project DIR` | Copies to `DIR/.claude/skills/divorce/`. |
| Codex | `sh install.sh --codex` | Copies to `~/.codex/skills/divorce/`. `--project` is Claude-only. |
| Other agents | `sh install.sh --agents-md AGENTS.md` | Appends or replaces a marked block in the instruction file your agent reads. |

For a manual copy, copy the entire `skills/divorce/` directory, including scripts, to `~/.claude/skills/divorce/`. Instruction blocks point to the gate's absolute path in the checkout: keep the checkout in place.

The standalone installer does not register a plugin, install validators or add an automatic gate hook. Copies do not update themselves. See [update, dry-run and removal behavior](docs/faq.md#does-installing-it-make-the-gate-run-itself).

<details>
<summary>Requirements and validator setup</summary>

- Python 3.9+ for the standalone installer; Python 3 for the gate.
- A shell for the installation scripts.
- Nu HTML Checker: `VNU`, `vnu` on `PATH`, or `VNU_JAR` with Java.
- For Nu setup: network access, `curl`, and `shasum` or `sha1sum`. Native macOS/Linux archives also need `unzip`; `--jar` needs Java. The installer verifies the downloaded SHA-1 and checks the validator's version command.
- A rendered browser page and a way to evaluate the axe snippet. It loads axe-core 4.10.2 from a CDN unless that version is already present. Script loading must be allowed.

```sh
sh skills/divorce/scripts/install-vnu.sh
```

Set `VNU` to the binary path it prints, or put `vnu` on `PATH`. For a JAR installation, use `--jar` and set `VNU_JAR` to the printed JAR path; Java must be available.
</details>

<details>
<summary>Commands: prepare the evidence</summary>

With the served version of `examples/div-button/after.html` already loaded in your verification browser session:

```sh
python3 skills/divorce/scripts/gate.py html examples/div-button/after.html
agent-browser eval "$(python3 skills/divorce/scripts/gate.py axe-snippet)" > axe.json
python3 skills/divorce/scripts/gate.py axe axe.json
python3 skills/divorce/scripts/gate.py check --html examples/div-button/after.html --axe axe.json --axe-max-impact serious
```

For your project, replace the HTML input with its served URL or built HTML file. Capture genuine axe evidence from that same page and state. Outside the checkout, use your installed skill's script path. Browser automation is separate: the gate does not open a page, run axe itself or refresh a capture.

See [all commands and flags](docs/how-it-works.md#commands).
</details>

## FAQ

<details>
<summary>What does the verdict cover?</summary>

| Exit | JSON verdict | Meaning |
| --- | --- | --- |
| 0 | `pass` | The invoked check passed its configured policy. |
| 1 | `fail` | HTML errors or axe violations at or above the impact threshold. |
| 2 | `not_measured` | Missing tools, unavailable input or unusable evidence. Never a pass. |

[gate.py](skills/divorce/scripts/gate.py) parses Nu's JSON messages and axe's violations. Missing or invalid measurement takes priority, even when a failure was also observed. Otherwise, blocking findings fail; with neither condition, the check passes. The model does not choose the verdict.

The JSON retains counts and reasons. axe totals count violated rules; each rule also records affected nodes. The snippet selects WCAG 2.2 A/AA tags, including earlier versions, plus best-practice rules. Serious and critical violations fail by default; lower-impact findings remain visible. HTML warnings do not fail the check.

A complete gate needs both HTML and axe evidence. An HTML-only pass does not establish an axe pass. The caller must supply genuine evidence for the intended page; the gate does not authenticate it or prove it is current. See [exact reasons and evidence limits](docs/how-it-works.md).

This is not a component library, CSS validator, JavaScript correctness check, performance audit or design review. It does not prove full WCAG conformance or enforce every ladder decision. Manual keyboard, focus, interaction and visual checks remain necessary.
</details>

<details>
<summary>Where are the with/without results?</summary>

The [with/without suite](evals/README.md) compares identical tasks under the same model and run conditions. Results are not published; its model grading is separate from the deterministic gate. No figures are entered into the record until measured.

```sh
claude plugin eval . --ablation with-without --allow-tools Write Edit Bash --no-publish --keep-temp
```
</details>

<details>
<summary>Frameworks, conventions and maintenance</summary>

- [Framework support](docs/faq.md#can-react-vue-wordpresselementor-and-php-keep-the-house): check served HTML and the rendered DOM.
- [Automated coverage](docs/faq.md#does-a-green-result-mean-wcag-and-i-are-married-forever): a passing gate is not full WCAG conformance.
- [Source versus served HTML](docs/faq.md#why-check-the-served-html-instead-of-the-family-source-tree): validate output, not unrendered templates.
- [Spec versus convention](docs/faq.md#spec-or-convention-who-gets-the-cursor): cite the spec and preserve project conventions.
- [Installation and maintenance](docs/faq.md#does-installing-it-make-the-gate-run-itself): no automatic hook.
- [Not measured](docs/faq.md#can-not-measured-sign-the-pass-papers): never a pass.

[Full FAQ](docs/faq.md) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)
</details>

## License

[MIT](LICENSE). Third-party components retain their own licenses as described in [NOTICE](NOTICE).

A cousin of [ponytail](https://github.com/DietrichGebert/ponytail) (MIT), which removes code. divorce guides the code that remains toward the spec. The decision ladder is adapted from ponytail; semantic HTML and modern CSS guidance is adapted from [kemiljk/skills](https://github.com/kemiljk/skills) (MIT).

Nu HTML Checker comes from validator/validator (MIT). axe-core is MPL-2.0. Neither validator is bundled here. See [NOTICE](NOTICE) for attribution and component details.
