# FAQ

## Is this just a custody dispute over divs?

No. The name is the joke; the scope is the web platform. The skill guides HTML, CSS, JavaScript and ARIA choices against WHATWG HTML, CSS specifications, WAI-ARIA and WCAG 2.2. Its gate validates served HTML with Nu HTML Checker and checks the rendered DOM with axe-core's WCAG 2.2 A/AA and best-practice tags. It does not validate all CSS or JavaScript behavior.

A div is appropriate when a generic container is needed. The main example fixes a skipped heading level and changes Nu's result from fail to pass. The second replaces a div used for an action with a button. Both pass HTML validation. Automated checks do not reliably infer that a generic element with a click handler should have been a button.

## Spec or convention: who gets the cursor?

CSS Basic User Interface Level 4 defines `pointer` as: “The cursor is a pointer that indicates a link”. See [the cursor section](https://drafts.csswg.org/css-ui-4/#cursor).

That definition does not require an arrow on every button or prohibit the common web convention of a hand on buttons. A button with `cursor: default` and one with `cursor: pointer` represent conventions that this skill does not impose. Keep the project's choice unless its owner decides to change it. Neither choice is treated as a validity error by this gate.

The rule is to cite a specification section for a specification claim and identify conventions as conventions.

## Why not just a linter and an amicable goodbye?

A source linter is useful. divorce also guides decisions before code exists: whether the feature is needed, whether the project already implements it, and which native element fits its behavior.

Its gate then checks the HTML actually served and accessibility evidence from the rendered DOM. A source linter cannot by itself establish what a builder, server or client-side framework produced. Keep existing linters; the gate serves a different stage of verification.

## Does a green result mean WCAG and I are married forever?

No. Automated checks cover only part of WCAG. The snippet selects WCAG 2.2 A/AA tags, including earlier versions, and best-practice rules. The default gate policy blocks serious and critical violations. Moderate and minor findings still appear in the JSON and can pass that default policy.

Check the keyboard path, including Tab, Enter, Space and Escape where relevant. Check focus movement and return. Inspect the page and test its actual interactions. Report what remains unchecked. A passing gate is not a claim of full WCAG conformance or proof of usability.

## Why check the served HTML instead of the family source tree?

The source is not always the document delivered to the browser. Templates, framework builds, WordPress themes and builder widgets can add or change markup. Nu checks a served URL or a built HTML file. axe checks the live DOM after rendering.

These are different inputs. A client-rendered application's initial HTML can pass while its live DOM has accessibility problems. Capture the relevant page state and keep the HTML input and axe evidence aligned. The gate does not verify that alignment for you.

## Can React, Vue, WordPress/Elementor and PHP keep the house?

Yes, the workflow targets their output. Reuse an existing project component when it fits. Verify the real elements it renders. Pass served or built HTML to Nu, then collect axe evidence from the resulting browser page.

This is an output-based workflow, not a tested compatibility matrix or a framework adapter. The repository does not include integrations that render every stack for you.

## Is ponytail the ex?

It is a cousin. [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) removes code. divorce makes the code that remains meet the spec. The decision ladder is adapted from ponytail, which is MIT-licensed. Semantic HTML and CSS guidance also credits kemiljk/skills under MIT. See [NOTICE](../NOTICE) and [LICENSE](../LICENSE).

## Does installing it make the gate run itself?

No. The standalone installer copies a skill or writes an instruction block. It does not register a plugin, install Nu or add lifecycle hooks. The agent still needs to follow the instructions and run the gate. Plugin installation is a separate route through Claude Code's plugin manager.

Installed skill copies do not update when the checkout changes. From the checkout root, these are separate maintenance operations for a Claude installation:

```sh
sh install.sh --claude --dry-run
sh install.sh --claude --force
sh install.sh --claude --uninstall
```

`--dry-run` prints prospective actions without writing. `--force` replaces the destination, including local edits. `--uninstall` requires installation metadata and removes unchanged installed files while retaining modified or added files. A manual copy has no installer metadata. Use the mode and project destination of the original installation. Codex uses `--codex`; `--project DIR` is Claude-only.

For an instruction-file installation:

```sh
sh install.sh --agents-md AGENTS.md --uninstall
```

This removes the marked block and leaves surrounding content in place. Malformed or duplicate markers are rejected. The installed block points to the original checkout's gate, so moving the checkout requires updating the block.

## Can “not measured” sign the pass papers?

No. Exit 2 means the evidence is incomplete or unusable. Fix the missing tool, unavailable input or invalid capture, then measure again. An infrastructure problem takes priority over a detected failure without erasing that failure's reason. See the [exact reason table](how-it-works.md#exit-codes-and-reasons).

## Where are the benchmark receipts?

They are planned. The method will compare identical tasks with and without the skill and retain both groups' `gate.py` verdicts and evidence. The existing [eval documentation](../evals/README.md) describes a model-based grading fallback. That score is not a deterministic gate result, an axe run or a completed benchmark.
