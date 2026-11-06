# How it works

divorce separates writing guidance from measurement. The agent follows the ladder and element table in [SKILL.md](../skills/divorce/SKILL.md). Python composes the gate verdict from validator output. No model grades the gate result.

## Gate flow

1. Choose served HTML inputs: URLs or built HTML files. Do not substitute unrendered templates.
2. Run the HTML check. The gate finds Nu through `VNU`, then `vnu` on `PATH`, then an existing `VNU_JAR` with Java. Local input paths become absolute before Nu receives them.
3. Nu is invoked with `--format json --exit-zero-always`. The gate reads JSON from Nu's standard error. A nonzero validator process status is an infrastructure failure, even if the JSON also contains document errors. The timeout is 60 seconds per input.
4. Each Nu invocation validates one input. The gate assigns all its messages to that input and emits one fact per input. Each fact contains `input`, `errors`, `warnings` and `messages`. `input` is exactly the supplied path or URL, including for an empty message list. Nu's document URLs do not replace it. Messages retain `type`, `message`, `line`, `column` and `extract`. Extracts are limited to 200 characters. HTML warnings are reported but do not fail the check.
5. Collect axe evidence from the intended rendered page and state. `axe-snippet` only prints JavaScript; it does not open or inspect a browser. Evaluate it with your browser tooling and save its returned JSON.
6. Read the axe capture. The gate normalizes rule IDs, impacts, tags and node counts, then counts violated rules by impact.
7. Compose the verdict. Measurement problems return 2 first. Otherwise, HTML errors or axe rules at the selected blocking impacts return 1. Otherwise, return 0.

The implementation is [gate.py](../skills/divorce/scripts/gate.py). Shell examples here assume the checkout root.

## Commands

| Command | Input and scope |
| --- | --- |
| `python3 skills/divorce/scripts/gate.py html FILE_OR_URL` | One or more HTML files or URLs; HTML only. |
| `python3 skills/divorce/scripts/gate.py axe-snippet` | Prints browser JavaScript; no measurement verdict. |
| `python3 skills/divorce/scripts/gate.py axe JSON_FILE` | Reads an axe result object or a violations list; axe only. |
| `python3 skills/divorce/scripts/gate.py check --html FILE_OR_URL --axe JSON_FILE --axe-max-impact serious` | Combines HTML and captured axe evidence. `--html` accepts multiple inputs. |

`FILE_OR_URL` and `JSON_FILE` are placeholders. Both `axe` and `check` accept `--axe-max-impact`. Its choices are `serious` (default), `moderate` and `minor`. Each includes all higher impacts: serious includes critical; moderate includes serious and critical; minor includes all four impacts.

The HTML check runs Nu; the axe check reads a file. `check` does not run axe or refresh that file. A complete check needs both sources of evidence.

## axe capture and JSON

The snippet expects axe-core 4.10.2. It reuses that exact loaded version or attempts to load it from a CDN. It uses a script element, waits for loading and checks the version before running axe. Its load timeout is 15 seconds. A load rejection must be treated as a failed capture; it is not a clean violations list.

The selected tags are `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa` and `best-practice`. This selects automated rules associated with WCAG 2.2 A/AA, including earlier versions, plus best practices. It does not establish full WCAG coverage.

The snippet returns a violations list with `id`, `impact`, `tags` and `n` for each rule. The file reader also accepts an axe result object with a `violations` list. An affected-node count must be supplied through a `nodes` array, `node_count` or `n`. If several forms are present, their counts must agree. Counts must be nonnegative integers, not booleans.

Normalized output has `axe.rules` and `axe.totals`. Each rule has `id`, `impact`, `nodes` and `tags`. Here `nodes` is the normalized integer count, not an array. Totals use `critical`, `serious`, `moderate`, `minor` and `null`. Totals count violated rules, not affected nodes. A null impact is retained but makes the measurement incomplete.

The JSON parser rejects duplicate keys and invalid numeric constants. Invalid payload shapes or fields are not replaced with empty results.

## Exit codes and reasons

Measurement commands print JSON with `verdict` and `reasons`, plus `html`, `axe` or both. Reasons are deduplicated in encounter order, with measurement problems before detected failures.

| Exit | `verdict` | Condition |
| --- | --- | --- |
| 0 | `pass` | No measurement problems and no blocking findings for the invoked check. |
| 1 | `fail` | Blocking findings with usable measurements. |
| 2 | `not_measured` | At least one measurement problem, even if failures were also observed. |

These reason strings come directly from `gate.py`:

| Reason | Exit contribution | Meaning |
| --- | --- | --- |
| `validator_missing` | 2 | No usable validator command was found. |
| `validator_failed` | 2 | Nu returned nonzero, timed out, could not execute, or supplied invalid JSON, fields or positions. |
| `input_unreachable` | 2 | Nu reported a `non-document-error` for an input. |
| `axe_json_missing` | 2 | The capture could not be read because of a file-system error. |
| `axe_json_invalid` | 2 | The capture could not be decoded or parsed, or its structure, fields or counts were invalid. |
| `axe_version_mismatch` | 2 | The capture's `error` reports `axe_version_mismatch`. |
| `axe_snippet_error` | 2 | The capture contains another `error` value. |
| `axe_impact_unknown` | 2 | At least one violation has a null impact. |
| `html_errors` | 1 | At least one HTML input has an error. |
| `axe_violations:` followed by impact counts | 1 | At least one violated rule meets the impact threshold. |

For example, the default axe failure reason can be `axe_violations:critical=0,serious=1`. At a lower threshold it also lists the corresponding lower impacts. A result with `axe_json_missing` and `html_errors` returns 2 and keeps both reasons.

`axe-snippet` exits 0 when it prints the snippet. That is not a page pass. CLI argument errors are handled by the argument parser and do not use the measurement JSON contract.

## Why it fails closed

Missing evidence cannot establish a clean document. A missing validator is different from a validator that found no errors. An unreadable axe file is different from a measured empty violations list. Both failures to measure return 2 and must block a claim that the full gate passed.

The precedence is deliberate: measurement problems, then blocking findings, then pass. Observed failures remain visible when infrastructure is also broken. HTML warnings and axe findings below the chosen threshold stay in the evidence even when the verdict is pass.

## Evidence limits

The gate checks input structure and computes policy; it does not authenticate a capture, compare its URL with the HTML input, or prove it is current. The caller must collect genuine evidence from the same page and relevant state. An HTML-only pass covers only HTML. An axe-only pass covers only the supplied violations under the chosen impact policy.

The gate does not validate CSS, business logic, performance or visual design. Its output cannot prove every instruction in the skill was followed. Manual keyboard paths, focus return, interaction and visual inspection remain separate checks. Record the exit code, counts and messages, the manual checks performed, unchecked behavior and remaining risk.
