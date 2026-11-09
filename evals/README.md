# With/without benchmark

Five passes over eight cases in two arms produced **80 executions**: 40 with
divorce and 40 without. The recorded run used Claude Code 2.1.318 with the account's
default model on one machine. Results are in [results/summary.json](results/summary.json).

## Reproduce the comparison

From the repository root on the evaluation machine:

```sh
claude plugin eval . --ablation with-without --runs 5 -j 4 --allow-tools Write Edit Bash --no-publish --trust-plugin --keep-temp
```

The explicit `--runs 5` overrides the three repetitions declared in each prompt.
`--trust-plugin` grants trust to this reviewed plugin, `--no-publish` keeps the
report local, and `--keep-temp` retains the generated HTML for measurement.
Check that the runner actually loaded the plugin in the with arm; missing tools,
timeouts and missing artifacts must not be counted as successful measurements.

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

The prompts ask for a standalone `index.html`, require no external resources, and
prohibit opening a browser during generation. Each case allows 12 turns and 300
seconds. Browser measurement was a separate step after generation.

## Measure the HTML

Each generated page was checked with **Nu HTML Checker (vnu 26.11.4)** and
**axe-core 4.10.2 in Chrome 156**. The summary records HTML lines, JavaScript lines,
ARIA attributes, axe violation nodes and Nu errors. Each metric's `runs` list
contains the total over all eight cases for one pass; `mean`, `min` and `max`
describe the five pass totals. Page counts cover all 40 outputs per arm.

The Numbers card calculates rounded integer changes in the with-arm mean relative
to the without-arm mean: −29% HTML lines, −41% JavaScript lines, −33% ARIA attributes
and −76% axe violation nodes. Nu found errors on **3 of 40 pages with divorce and
0 of 40 without**; that regression remains visible alongside the reductions.

For a retained output, run the HTML gate from the repository root:

```sh
python3 skills/divorce/scripts/gate.py html evals/artifacts/modal/index.html
```

Supply an actual retained file at that path. Preserve the gate's JSON and exit
code: 0 is a pass for the invoked check, 1 a failure, and 2 `not_measured`.
An HTML-only pass does not establish an axe pass; axe requires the rendered page.

## What the graders tell us

The suite's scored graders give **1 to both arms**. They check file existence and
model-assessed source facts; they do not distinguish the measured HTML outcomes.
The measure is in the generated HTML and the Nu/axe results, not the grader score.
Skill activation is a separate, display-only indicator in the with arm.

The source-facts grader asks about inline click handlers on noninteractive elements,
unlabelled controls, images missing alt, positive tabindex and skipped heading
levels. It remains a model judgment and can miscount. Calling the skill is not
proof that its gate ran or passed. The recorded modal replay includes unsuccessful
checker attempts and explicitly unmeasured checks.

## Limits

Eight synthetic tasks, five repetitions, one model setting and one machine do not
establish a general quality improvement. Lines measure size, not quality; fewer
ARIA attributes alone do not prove better accessibility. Nu and axe findings do
not replace keyboard, focus, interaction or visual checks, and neither the model
scores nor these measurements prove full WCAG conformance. The replay is one pair
of recorded executions, not a summary of every run.
