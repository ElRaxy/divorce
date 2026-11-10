# Contributing

Keep changes focused. Read [SKILL.md](skills/divorce/SKILL.md) for the writing rules and [how it works](docs/how-it-works.md) for the measurement contract.

## The golden rule

Every change to a criterion must cite the relevant specification section. Link to the exact section and explain how the proposed behavior follows from it. Separate normative requirements, project policy and conventions. A convention must not be presented as a validity error.

The source order is WHATWG HTML, W3C/CSSWG specifications, WAI-ARIA and its Authoring Practices Guide, WCAG 2.2, then MDN. Blog posts and Q&A are not specification evidence. The [cursor example](docs/faq.md#spec-or-convention-who-gets-the-cursor) shows the distinction.

## Run the tests

From the repository root, run each existing test file directly:

```sh
python3 tests/test_install.py
python3 tests/test_examples.py
python3 tests/test_publish_clean.py
python3 tests/test_measure.py
python3 tests/test_popover_rules.py
python3 skills/divorce/scripts/tests/test_gate.py
```

Each file uses Python's standard-library `unittest` runner. These commands require no test framework installation.

| File | Coverage and dependencies |
| --- | --- |
| `tests/test_install.py` | Installer contracts in temporary directories, including instruction-block preservation, replacement and removal. Requires Python 3.9+. |
| `tests/test_examples.py` | Example inventory, generated index consistency, complete documents and inline JavaScript size. Real HTML checks use Nu through the gate and skip when the measurement returns 2. Inspect skips before claiming HTML validation. |
| `tests/test_publish_clean.py` | Published text hygiene. Uses Git to enumerate files when available, with a file-system fallback. |
| `tests/test_measure.py` | Per-page benchmark measurement (`evals/measure.py`) against a fake eval result and a fake validator. |
| `tests/test_popover_rules.py` | The two Nu errors from the 5-run benchmark, reproduced in `tests/fixtures/popover-menu/`; real-validator checks skip when Nu is missing. |
| `skills/divorce/scripts/tests/test_gate.py` | CLI and JSON contracts with a fake validator and temporary fixtures. Node.js enables snippet harness checks. A real-validator integration check runs only when Nu is available. Neither replaces a rendered-page axe run. |

To enable real-validator checks, provide `VNU`, `vnu` on `PATH`, or `VNU_JAR` with Java. The separate Nu setup script is:

```sh
sh skills/divorce/scripts/install-vnu.sh
```

It prints the binary path. Use that path as `VNU`. For the JAR route, pass `--jar` and set `VNU_JAR` to the printed JAR path. Native installation needs `curl`, `unzip` and `shasum` or `sha1sum`; the JAR route needs Java instead of `unzip`.

## Changes and evidence

- Preserve the exit meanings: 0 pass, 1 fail, 2 not measured. Missing measurement must never become a pass.
- Add contract coverage when changing parsing, reason strings, thresholds or installer behavior. Include invalid and missing input where relevant.
- Keep HTML validity, automated accessibility findings and manual interaction evidence distinct. Do not invent axe findings for examples that were not measured.
- If an example changes, keep its inventory and generated index consistent. Follow [examples/README.md](examples/README.md).
- Keep documentation in English. Update [CHANGELOG.md](CHANGELOG.md) for user-visible behavior. Do not add a release date before a release exists.
- Preserve license notices and third-party attribution in [NOTICE](NOTICE).

Report the exact commands run, exit codes and skips. For UI behavior, also state which browser states, keyboard interactions and focus paths were checked, and what remains unmeasured. A test result or model-based eval score is not proof of full WCAG conformance.
