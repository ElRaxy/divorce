# Changelog

## Unreleased

### Added

- Optional keyboard check on the rendered page: `gate.py keyboard-snippet`, `keyboard-init`, `keyboard` and `check --keyboard`. It fails on elements that react to clicks but are not in the Tab order, and warns on buttons whose click handler changes `location`. It does not press keys.
- `evals/measure.py` stores the gate JSON for every benchmark page; `evals/results/pages.json` holds Nu messages and axe rules for the recorded 5-run benchmark.
- `recipe-list` eval case for links versus buttons.
- Regression fixture for the two Nu errors found in the benchmark (`aria-expanded` with `popovertarget`, `aria-label` on a `div` popover).

### Fixed

- The axe reader accepts the JSON string that `agent-browser eval` prints; following SKILL.md literally used to end in `axe_json_invalid`.

## 1.0.0

### Added

- One-line install for Claude Code, Codex, Gemini CLI, GitHub Copilot, OpenCode and other agents with `npx skills add ElRaxy/divorce`.
- A recorded Tab and Enter demo of `examples/div-button` in Chrome.

### Changed

- README rewritten: one editorial banner, numbers and the nine example cases as tables derived from the repository's data.
- Social preview in the same editorial style, with Instrument Serif (SIL OFL 1.1).

## 0.1.0

### Added

- Agent guidance for minimal native HTML, CSS, JavaScript and ARIA, with a decision ladder and a behavior-to-element table.
- A deterministic gate for served HTML through Nu HTML Checker and rendered-DOM evidence from axe-core.
- JSON evidence and exit codes for pass, fail and not measured, with configurable axe impact thresholds.
- An axe-core snippet selecting WCAG 2.2 A/AA and best-practice tags, including earlier WCAG versions.
- A separate Nu installer with checksum verification.
- Claude Code plugin and marketplace manifests.
- Standalone installation for Claude Code, Codex and agent instruction files, with preview, replacement and removal modes.
- Native HTML examples, agent eval cases, and installer, gate, example and publication-hygiene tests.
- Public usage, FAQ, gate-flow and contribution documentation.
