# UI eval cases

Eight ordinary UI requests measure whether the plugin is used without naming it
in the user prompt. Each request writes a standalone `index.html` in the run's
current working directory. The prompts require no external resources and prohibit
opening a browser.

| Case | Task | Prompt |
| --- | --- | --- |
| `modal` | Confirmation modal | [prompt](modal/prompt.md) |
| `navigation-menu` | Responsive site navigation | [prompt](navigation-menu/prompt.md) |
| `faq-accordion` | Independently expandable answers | [prompt](faq-accordion/prompt.md) |
| `signup-form` | Newsletter signup form | [prompt](signup-form/prompt.md) |
| `product-card` | Product details and local cart count | [prompt](product-card/prompt.md) |
| `tabs` | Three keyboard-operated information panels | [prompt](tabs/prompt.md) |
| `toast` | Non-blocking save notification | [prompt](toast/prompt.md) |
| `dropdown-menu` | Local note actions | [prompt](dropdown-menu/prompt.md) |

## Run on the evaluation machine

From the repository root, after reviewing the suite and configuring Claude Code:

```sh
claude plugin eval . --ablation with-without --allow-tools Write Edit Bash --no-publish --keep-temp
```

This command is documentation; it was not executed when authoring these cases.
The runner may ask whether the plugin is trusted. The command does not suppress
that prompt. `--no-publish` keeps the report local. `--keep-temp` retains run
directories for inspecting the produced files. The cases request write and shell
tools; the explicit operator grant enables them. No scaffold or real MCP server
is required.

Each case declares `runs: 3`, `max_turns: 12`, and `timeout_seconds: 300`.
The full comparison therefore requests 8 cases x 3 runs x 2 arms = 48 agent runs,
plus model grading. `--runs 1` overrides the repetitions for a smaller run;
`--case modal` selects one case. Neither variant was executed here.

`--ablation with-without` compares the plugin arm against the no-plugin arm.
Inspect `aggregate-result.json`: `suite.plugins` must include the intended plugin
without a `manifest_invalid`, `disabled_by_default`, or `will_not_load` problem.
An absent plugin invalidates the claimed comparison. Compare both-arm scores and
their delta separately from the display-only skill activation indicator. A tool
grant warning, timeout, or missing artifact must not be reported as a successful
measurement.

## Format evidence

The format was checked by reading `claude plugin eval --help` and the installed
Claude Code 2.1.319 executable's embedded eval-authoring documentation and schema.
The installation was a native executable, not an npm package; `npm root -g` did
not contain an `@anthropic-ai/claude-code` package. No init command, evaluation,
browser, validator, or test suite was run.

The help accepts `<eval dir>/**/case.yaml` or `prompt.md` with `graders/*.md`.
This suite uses the documented Markdown format:

- `prompt.md` frontmatter supplies `max_turns`, `timeout_seconds`, `allowed_tools`,
  and `runs`; its body is the user request.
- Grader frontmatter selects `file_exists`, `llm`, or `tool_used`.
- `focus: {source: file, path: index.html}` gives the model grader the file's
  contents. The string `focus: files` would provide only created file names.
- The optional plugin manifest field is
  `"experimental": {"evals": "evals"}`. Its value is a directory relative to the
  plugin root. The default is already `evals/`, so this suite requires no manifest
  change. `--eval-dir` can override that directory; a top-level `evals` field is
  not the documented manifest form.
- In the alternative `case.yaml` schema, `schema_version: "1.1"` identifies the
  supported schema, `execution` contains the prompt and execution limits, and
  `runs` is a top-level field. `context.scaffold_script` specifies preparation
  through an author-supplied Bash script. `--scaffold` opts in; `--no-scaffold`
  skips it. These cases start from an empty run directory and omit a scaffold.
  A scaffold is preparation, not a post-run grader.

## Grading and its limits

The installed grader schema supports `regex`, `tool_order`, `tool_used`,
`file_exists`, `llm`, and `baseline`. It has no command or script grader, so a
deterministic call to `gate.py` cannot be configured as a grader in this version.
No unsupported `command`, `script`, or exit-code mapping fields were invented.

Every case has these graders:

| File | Arm | Criterion |
| --- | --- | --- |
| `graders/file-exists.md` | Both | The run created `index.html`. |
| `graders/source-facts.md` | Both | All five source counts below are zero and observable. |
| `graders/skill-fired.md` | With plugin only | `Skill` was called with the exact or namespaced `divorce` skill identifier. |

The factual model grader counts noninteractive elements with inline `onclick`,
labelable `input`/`select`/`textarea` controls without an associated HTML label,
`img` elements without `alt`, positive `tabindex` values, and forward heading
level jumps. Its rubric defines exclusions and associations explicitly. It does
not grade aesthetics, code quality, or whether the implementation is fashionable.
All counts must be zero to pass; unknown counts are failures rather than zeros.
The file-existence grader additionally prevents a missing deliverable from passing.

The installed model-grader protocol requires a single `PASS` or `FAIL` response;
the counts are instructions to the judge, not structured numeric output fields.
This fallback remains model-based and can miscount. It is not deterministic
validation, an axe run, a complete accessibility audit, or a functional test.
The two scored graders have equal weight, so a case that creates the file but
fails the count criterion can receive a partial aggregate score. Use the default
threshold of 1.0 to require both criteria to pass.

Under ablation, `arm: with-only` makes skill activation a display-only indicator,
excluded from the quality score. The scored graders explicitly use `arm: both`.
Calling the skill does not prove that the generated page passes its gate. Conversely,
a source-fact pass does not prove skill activation or successful interaction.

## Deterministic HTML validation outside the runner

On the evaluation machine, retain an output as `evals/artifacts/modal/index.html`
and run the existing gate from the repository root:

```sh
python3 skills/divorce/scripts/gate.py html evals/artifacts/modal/index.html
```

The gate resolves the validator through `VNU`, then `vnu` on `PATH`, then
`VNU_JAR` with Java. Exit 0 means HTML pass; exit 1 means HTML errors; exit 2 means
infrastructure or an unmeasured result. Preserve the JSON output and exit code;
exit 2 is never a pass. Repeat for the retained artifacts from both arms. HTML
validity alone does not establish that the five source facts or accessibility
checks pass.

## Unverified and pending confirmation

- **unverified:** case discovery, frontmatter parsing, tool grants, skill identity
  matching, generated artifacts, and all scores have not been exercised by a run.
- **unverified:** no generated HTML has been measured with vnu or axe, and no
  interaction or visual checks have been performed.
- Confirm that the evaluation machine's installed version supports this same
  format before running it. The local format above was read, not trialed.
- If a future runner adds command graders, confirm its documented command field,
  working directory, post-run timing, result protocol, and infrastructure handling
  before wiring in the gate. Also confirm how it exposes the gate path and forwards
  `VNU`, `VNU_JAR`, `PATH`, and Java. Those fields are pending, not assumed here.
