# Native HTML examples

Generated from `examples/manifest.json`. Regenerate from the repository root:

```sh
python3 examples/build_readme.py > examples/README.md
```

Each pair changes one pattern. HTML validity does not establish accessibility.
Expected HTML verdicts were measured with Nu HTML Checker 26.11.4 (2026-11-06).
The listed axe rule IDs are documented in [axe-core 4.10.2](https://raw.githubusercontent.com/dequelabs/axe-core/v4.10.2/doc/rule-descriptions.md).
Their expected occurrence before and absence after remain **unverified**; axe has not been run.
Empty rule lists deliberately make no automated accessibility claim; see each note.
No browser, keyboard or assistive-technology checks are claimed by this index.

| Case | Rationale | Before HTML | After HTML | Expected axe rules in before | Note |
| --- | --- | --- | --- | --- | --- |
| `div-button` | [Use a button for an action](https://html.spec.whatwg.org/multipage/form-elements.html#the-button-element) | [pass](div-button/before.html) | [pass](div-button/after.html) | None asserted | HTML expectations measured with Nu HTML Checker 26.11.4 on 2026-11-06. No axe rule is asserted: a clickable div without an interactive role is not reliably reported as a button failure. |
| `button-link` | [Use a link for navigation](https://html.spec.whatwg.org/multipage/text-level-semantics.html#the-a-element) | [pass](button-link/before.html) | [pass](button-link/after.html) | None asserted | HTML expectations measured with Nu HTML Checker 26.11.4 on 2026-11-06. No axe rule is asserted: a named button used for navigation can pass automated accessibility checks. |
| `custom-modal` | [Use dialog for a modal task](https://html.spec.whatwg.org/multipage/interactive-elements.html#the-dialog-element) | [pass](custom-modal/before.html) | [pass](custom-modal/after.html) | None asserted | HTML expectations measured with Nu HTML Checker 26.11.4 on 2026-11-06. No axe rule is asserted: focus trapping, Escape and focus restoration require interaction checks. Native dialog supplies those behaviors. |
| `custom-disclosure` | [Use details for a disclosure](https://html.spec.whatwg.org/multipage/interactive-elements.html#the-details-element) | [pass](custom-disclosure/before.html) | [pass](custom-disclosure/after.html) | None asserted | HTML expectations measured with Nu HTML Checker 26.11.4 on 2026-11-06. No axe rule is asserted: omitted disclosure semantics on plain div elements are not reliably detected. |
| `input-label` | [Associate a label with its control](https://html.spec.whatwg.org/multipage/forms.html#the-label-element) | [pass](input-label/before.html) | [pass](input-label/after.html) | `label` | HTML expectations measured with Nu HTML Checker 26.11.4 on 2026-11-06. The label rule occurrence is unverified: axe has not been run. Missing a label is not itself a Nu HTML Checker syntax error. |
| `heading-order` | [Keep heading levels in order](https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships.html#intent) | [fail](heading-order/before.html) | [pass](heading-order/after.html) | `heading-order` | HTML expectations measured with Nu HTML Checker 26.11.4 on 2026-11-06. The heading-order rule occurrence is unverified: axe has not been run. Nu HTML Checker reports the skipped level (h1 to h3) as an error. |
| `image-alt` | [Provide an image text alternative](https://html.spec.whatwg.org/multipage/images.html#alt) | [fail](image-alt/before.html) | [pass](image-alt/after.html) | `image-alt` | HTML expectations measured with Nu HTML Checker 26.11.4 on 2026-11-06. Expected Nu error: an img element must have an alt attribute, except under certain conditions; this image has no applicable exception. The image-alt rule occurrence is unverified: axe has not been run. |
| `positive-tabindex` | [Follow document order for focus](https://html.spec.whatwg.org/multipage/interaction.html#the-tabindex-attribute) | [pass](positive-tabindex/before.html) | [pass](positive-tabindex/after.html) | `tabindex` | HTML expectations measured with Nu HTML Checker 26.11.4 on 2026-11-06. The tabindex rule occurrence is unverified: axe has not been run. A positive tabindex is valid HTML; removing it restores document order. |
| `div-list` | [Represent a list with ul and li](https://html.spec.whatwg.org/multipage/grouping-content.html#the-ul-element) | [pass](div-list/before.html) | [pass](div-list/after.html) | None asserted | HTML expectations measured with Nu HTML Checker 26.11.4 on 2026-11-06. No axe rule is asserted: list and listitem validate existing list markup; they do not infer a missing list from plain div elements. |
