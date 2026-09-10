# Word template: content-control tag specification

**Status:** specification only. No template file and no add-in is built in week 1
(tech doc 4.4). This exists because it costs almost nothing now and it is what
makes the week-5 docx path and the deferred Word task pane a drop-in rather than
a rewrite.

The generated tag table is in [`template_tags.md`](template_tags.md), produced by
`scripts/generate_template_spec.py` from `schemas/aufgabe.py`. Regenerate it
whenever the item schema changes.

---

## 1. Why a template at all

Free-form Word input has to be reverse-engineered into the item schema, and that
parsing step is the least interesting and least reliable part of the pipeline.
A template whose content-control tags *are* the schema's field names removes the
problem instead of solving it: structure becomes explicit at authoring time, and
the parser reads tags rather than guessing at headings (tech doc 4.4).

Two consequences worth stating plainly to a reviewer:

- **Structured template → the full catalogue runs.** Every rule's `requires` can
  be evaluated against real fields.
- **Free-form document → a degraded subset runs**, and the output has to say so.
  A tool that silently checks less than it appears to is worse than one that
  admits the gap (tech doc 4.3).

## 2. The one rule that governs the tag names

> A content control's `tag` is exactly the dotted path of the schema field it
> holds.

No abbreviations, no display names, no German aliases. `fallsituation.text`, not
`Fall` or `Situationstext`. The `title` of a control is the human-readable German
label shown to the author and may be anything; the `tag` is machine-facing and
is bound by the rule above.

This is what lets `scripts/generate_template_spec.py` derive the table from the
Pydantic model, which in turn means a field rename cannot leave the template
pointing at a field that no longer exists.

## 3. Repeating structures and the ID problem

`teilaufgaben` and `erwartungspunkte` are **repeating section content controls**.
Everything else is a plain-text or group control.

The item schema's IDs (`ta.2`, `ta.2.eh.3`) identify a structural *position*, and
their known weakness is that inserting or reordering a Teilaufgabe shifts every
later ID (`schemas/aufgabe.py` module docstring). In a one-shot run against a
submitted draft that does not bite. In a live task pane it would.

The template fixes it in the natural way: **each repeating instance carries its
own content-control tag, generated once and never reused.** The tag becomes an
opaque identifier that survives edits, and the visible number ("Teilaufgabe 2")
becomes display only. Concretely:

| | one-shot docx path (week 5) | task pane (deferred) |
|---|---|---|
| Anchor source | ordinal position in the parsed item | the content control's own tag |
| Survives reordering | no | yes |
| Flag comparison across runs | same draft only | across edits |

So the anchor grammar does not change; only where the anchor's identity comes
from. Both consumers of the check runner take anchors from the same
`Flag.anchor` field.

## 4. Writing flags back

The docx writer is a **consumer of the check runner's JSON contract**
(`schemas/flag.py`), not a second implementation of anything. It:

1. reads the `.docx`,
2. parses it into an `Aufsichtsarbeit` via the content-control tags,
3. calls the runner,
4. resolves each `Flag.anchor` to the content control with that tag,
5. adds a native Word comment on that range (`python-docx` 1.2.0 `add_comment()`),
6. renders the `NotChecked` list into a closing section, because a tool that
   silently omits coverage is worse than one that admits its gaps,
7. **saves a copy.** It never modifies the input file (tech doc 9).

Comment text carries the finding, the rule id, the quoted evidence and its
source, and any suggestions — the same fields the HTML report renders, because
both read one contract.

## 5. Fallback for untagged documents

When a control is absent, the field is simply absent from the parsed item. That
is not an error: every schema field is optional, so an untagged document parses
into a sparse `Aufsichtsarbeit` and the precondition gate reports what it could
not check. This is the same mechanism that makes the tool usable on a
half-written draft (tech doc 1.5.1), reused rather than duplicated.

## 6. Open questions for the template build

Carried from tech doc 12; none of them block week 1.

- Word environment at the target institutions: Microsoft 365 versus older
  perpetual Office, which decides whether repeating section controls and the
  add-in deployment path are available at all.
- Whether the Prüfungsausschuss authors in Word at all, or in a school
  information system that exports Word.
- Whether one document holds one Aufsichtsarbeit or all three of an exam. The
  schema supports both through `geschwister_aufgaben`, but the template's top
  level differs, and KOMP-05 needs the sibling set to be resolvable.
