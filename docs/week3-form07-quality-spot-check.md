# Week 3 FORM-07 quality spot check

Model: open-mistral-nemo

FORM-07's mechanism (extraction, anchoring, precondition gating) is fully
tested and works end-to-end against the live model -- see
`checks/llm/form_07.py` and `gateway/model_gateway.py::judge_form_07`. Its
**judgement quality** has not been hand-graded, the same open item the
German-quality spot check (`docs/week2-german-quality-spot-check.md`)
already carries for KOMP-01.

This file now documents **two different prompt designs**, in the order they
were actually tried, because the second one is *not* a strict improvement on
the first -- see §2 below for real numbers. Every model call anywhere in the
gateway is now logged in full (exact prompt, exact response) to
`logs/model_calls_real_<timestamp>.txt` (`gateway/model_gateway.py::_log_call`)
-- the excerpts in this file are copied straight out of one such log, not
retyped or summarised, so they're safe to trust as literal transcripts.
**Only read the `_real_` files.** A pytest run writes
`logs/model_calls_fake_<timestamp>.txt` with hardcoded fixture responses
that look deceptively like transcripts; those say nothing about the model.
(Logs from before 2026-09-15 used one shared name,
`model_gateway_calls_<timestamp>.txt`, for both.)

---

## 1. Design iteration 1 (2026-09-14): grounded in the closed operator catalogue

The Teilaufgabe's own operator was extracted deterministically (still true in
iteration 2). The model was asked to pick **one word from the fixed
`rules/operators.yaml` operator list** to describe the Erwartungshorizont's
side, and the two sides were compared by Anforderungsbereich (I/II/III), not
by exact operator identity.

Grade each row: does the model's chosen operator for the Erwartungshorizont
side genuinely match the performance the graded points reward, or is the
model over-reading short factual phrases as a higher-order operator
("erläutern"/"planen") than the plain, list-like content actually
represents? Both flags below were raised on real corpus items and were
flagged as *possibly* false positives on first read during Week 3
development (see `notepad/handdown03.md`'s continuation notes) -- they need
an actual domain grader's read, not just a second guess from the same
pipeline that produced them.

### A-01 ag.1.ta.3

**Teilaufgabe (operator: planen, Anforderungsbereich III):** Planen Sie 3 Schritte fuer ein Beratungsgespraech mit der Tochter von Frau Ostermann zur Frage des Umzugs.

**Erwartungshorizont:**
- Anliegen und Sorgen der Tochter erheben (3.0)
- Wunsch von Frau Ostermann als Ausgangspunkt darstellen (4.0)
- Versorgungsalternativen im ambulanten Setting aufzeigen (3.0)

**Model judged Erwartungshorizont operator:** erläutern (Anforderungsbereich II) -> flagged as mismatch.

**Grade (correct mismatch / false positive / unsure):**

---

### A-01 ag.1.ta.4

**Teilaufgabe (operator: erläutern, Anforderungsbereich II):** Erlaeutern Sie 2 Moeglichkeiten, wie Sie Frau Ostermann bei der Wiederaufnahme sozialer Kontakte unterstuetzen.

**Erwartungshorizont:**
- Kontakt zum Chor ueber ein Telefonat oder einen Besuchsdienst herstellen (3.0)
- Begleitung beim Verlassen der Wohnung organisieren (3.0)

**Model judged Erwartungshorizont operator:** planen (Anforderungsbereich III) -> flagged as mismatch.

**Grade (correct mismatch / false positive / unsure):**

---

### C-03 ag.1.ta.3

**Teilaufgabe (operator: nennen, Anforderungsbereich I):** Nennen Sie 2 rechtliche Grundlagen fuer freiheitsentziehende Massnahmen.

**Erwartungshorizont:**
- richterliche Genehmigung erforderlich (3.0)
- rechtfertigender Notstand als Ausnahme (3.0)

**Model judged Erwartungshorizont operator:** erläutern (Anforderungsbereich II) -> flagged as mismatch.

**Grade (correct mismatch / false positive / unsure):**

---

### C-03 ag.1.ta.4

**Teilaufgabe (operator: nennen, Anforderungsbereich I):** Nennen Sie 2 Aspekte zur Einbeziehung der Tochter von Herrn Petrovic.

**Erwartungshorizont:**
- altersgerechte Information (2.5)
- Schweigepflicht beachten (2.5)

**Model judged Erwartungshorizont operator:** erläutern (Anforderungsbereich II) -> flagged as mismatch.

**Grade (correct mismatch / false positive / unsure):**

---

### Working hypothesis, unverified (iteration 1)

All four flags share a pattern: the model called the Erwartungshorizont's
operator "erläutern" or "planen" (Anforderungsbereich II/III) against short,
list-like Erwartungspunkte that could plausibly still be "nennen"-level
(Anforderungsbereich I) -- i.e. a possible systematic bias toward reading
substantive-sounding short phrases as a higher cognitive level than their
actual form warrants.

---

## 2. Design iteration 2 (2026-09-15): full context + explicit goal, no vocabulary restriction

Per an explicit product decision: iteration 1's "restrict the model to a
closed vocabulary" approach was replaced with a prompt that instead gives
the model **everything it needs and a clearly stated goal**, on the theory
that a well-informed model naturally avoids both bad judgement calls and
grading-register language, without needing to be mechanically restricted.
Concretely, the new prompt (`FORM_07_PROMPT_TEMPLATE` in
`gateway/model_gateway.py`) gives the model, in one call:

- the rule's own wording, quoted from the catalogue (`rule_text`), not paraphrased
- the full Teilaufgabe text (not just its extracted operator)
- the deterministically-extracted operator(s) + Anforderungsbereich, as *given* context
- the full Erwartungshorizont text
- an explicit framing: "there is no candidate and no exam performance being
  graded here -- you are checking the internal consistency of the item's
  own construction"
- free-form `begruendung` (no closed word list to pick from)

**Real result, against the same 3-item smoke set (`scripts/smoke_run.py`),
model unchanged (`open-mistral-nemo`):** every Teilaufgabe with an
Erwartungshorizont got flagged (8 of 8 calls returned `mismatch: true`).

> **Correction (2026-09-15, later): two claims originally made in this
> section were wrong, and §3 supersedes them.** (1) The headline statistic
> "4/7 → 8/8" was malformed: the 4 flags spanned A-01 *and* C-03 while the
> denominator 7 was A-01's Teilaufgabe count alone. The like-for-like A-01
> numbers are iteration 1 = 2/7, iteration 2 = 7/7. (2) The explanation
> below -- that terse bullet-point Erwartungshorizonte inherently defeat
> free-form judgement -- is **disproven** by the A/B test in §3: the same
> model on the same items, with only the prompt changed, produces zero false
> positives. The over-firing was caused by this prompt, not by the model or
> by the shape of an Erwartungshorizont.

- **The grading-language crash still happened, on the 8th call**, and the
  actual transcript (below) shows *why* full context didn't prevent it: the
  Teilaufgabe that triggered it literally uses the catalogue operator
  **"bewerten"** as one of its two operators. There is no way to
  faithfully describe what that operator demands without using a word built
  on "bewerten" -- "Bewertung" is not a euphemism for grading a candidate
  here, it is the honest noun form of the exam's own approved verb. Full
  context did not, and structurally *cannot*, make the model stop
  describing an operator by its own name. This suggests the collision
  identified in iteration 1 is not a prompt-wording problem at all: it's
  that `schemas/flag.py`'s `GRADING_WORDS` list (`bewertung`, among others)
  blanket-forbids a word that is sometimes describing a grading judgement
  (correctly forbidden) and sometimes describing this exam's own named
  cognitive operator (a false positive on the guard itself).

### Real transcript 1 -- A-01 ag.1.ta.1 (mismatch found; plausible either way)

From `logs/model_gateway_calls_20260915T083757Z.txt`, copied verbatim:

```
PROMPT:
Kontext: Du unterstützt die Qualitätssicherung einer staatlichen Pflegeprüfung (PflAPrV Anlage 2), bevor sie geschrieben wird. Es gibt in dieser Aufgabe keinen Prüfling und keine Antwort eines Kandidaten zu beurteilen -- du prüfst ausschließlich, ob die Teilaufgabe und ihr Erwartungshorizont in sich konsistent konstruiert sind.

Zu prüfende Regel: Der Erwartungshorizont muss die Leistung abbilden, die die Teilaufgabe verlangt. Verlangt die Teilaufgabe eine Aufzaehlung, darf der Erwartungshorizont keine Begruendung bepunkten, und umgekehrt.

Teilaufgabe (die Aufgabenstellung, wie ein Prüfling sie liest):
"""Beschreiben Sie 4 Beobachtungen aus der Fallsituation, die die Selbstversorgung von Frau Ostermann betreffen."""

Erkannter Operator der Teilaufgabe: 'beschreiben' (Anforderungsbereich I).

Erwartungshorizont (die bepunkteten Erwartungspunkte -- was die Korrigierenden als richtige Antwort erwarten):
"""bereitet Mahlzeiten selbstaendig zu
nutzt den Rollator innerhalb der Wohnung
verlaesst das Treppenhaus seit 3 Monaten nicht
erhaelt zweimal taeglich Unterstuetzung durch den Pflegedienst"""

Deine Aufgabe: Verlangt die Art von Leistung, die im Erwartungshorizont bepunktet wird, tatsächlich das, was der oben genannte Operator von der Teilaufgabe fordert (verlangt der Operator z. B. eine Aufzählung von Fakten, bepunktet der Erwartungshorizont aber eine Begründung mit Ursache-Wirkungs-Zusammenhang, dann liegt ein Widerspruch vor)? Begründe sachlich und technisch, bezogen ausschließlich auf die Konstruktion der Aufgabe. Sprich niemals über die Qualität einer Antwort, eines Prüfungskandidaten oder eine Note -- es geht ausschließlich um die interne Konsistenz der Aufgabenkonstruktion selbst, nicht um eine Prüfungsleistung.

Antworte ausschließlich mit JSON in der Form {"mismatch": <true|false>, "begruendung": "<ein bis zwei sachliche Sätze zur Konstruktion, nicht zu einer Prüfungsleistung>"}.

RESPONSE:
{
  "mismatch": true,
  "begruendung": "Die Teilaufgabe verlangt eine **Beschreibung von 4 Beobachtungen** (faktische Aufzählung), während der Erwartungshorizont **konkrete Handlungen oder Zustände** als punktierte Antworten vorgibt, die zwar als Aufzählung formuliert sind, aber keine eigenständigen Beobachtungen darstellen. Beobachtungen erfordern eine **kontextbezogene Beschreibung** (z. B. *wie* Frau Ostermann die Mahlzeiten zubereitet oder *unter welchen Umständen* sie den Rollator nutzt), nicht bloße Nennungen von Aktivitäten."
}
```

**Grade (correct mismatch / false positive / unsure):**

### Real transcript 2 -- C-03 ag.1.ta.1 (the crash: legitimate use of "bewerten")

Same log file. This is the call whose response made `Flag()` raise
`ValidationError: finding uses grading language 'Bewertung'` --
`checks/runner.py`/`scripts/smoke_run.py` correctly did **not** swallow that
error, per `schemas/flag.py`'s own instruction to fix the prompt rather than
hide the failure:

```
PROMPT:
Kontext: Du unterstützt die Qualitätssicherung einer staatlichen Pflegeprüfung (PflAPrV Anlage 2), bevor sie geschrieben wird. Es gibt in dieser Aufgabe keinen Prüfling und keine Antwort eines Kandidaten zu beurteilen -- du prüfst ausschließlich, ob die Teilaufgabe und ihr Erwartungshorizont in sich konsistent konstruiert sind.

Zu prüfende Regel: Der Erwartungshorizont muss die Leistung abbilden, die die Teilaufgabe verlangt. Verlangt die Teilaufgabe eine Aufzaehlung, darf der Erwartungshorizont keine Begruendung bepunkten, und umgekehrt.

Teilaufgabe (die Aufgabenstellung, wie ein Prüfling sie liest):
"""Nennen Sie 3 Beobachtungen bei Herrn Petrovic und bewerten Sie diese hinsichtlich einer Eigen- oder Fremdgefaehrdung."""

Erkannter Operator der Teilaufgabe: 'nennen', 'bewerten' (Anforderungsbereich I, III).

Erwartungshorizont (die bepunkteten Erwartungspunkte -- was die Korrigierenden als richtige Antwort erwarten):
"""naechtliche Unruhe
lautes Ansprechen und Umwerfen eines Stuhls
Wahnerleben bezogen auf die Nachbarn"""

Deine Aufgabe: Verlangt die Art von Leistung, die im Erwartungshorizont bepunktet wird, tatsächlich das, was der oben genannte Operator von der Teilaufgabe fordert (verlangt der Operator z. B. eine Aufzählung von Fakten, bepunktet der Erwartungshorizont aber eine Begründung mit Ursache-Wirkungs-Zusammenhang, dann liegt ein Widerspruch vor)? Begründe sachlich und technisch, bezogen ausschließlich auf die Konstruktion der Aufgabe. Sprich niemals über die Qualität einer Antwort, eines Prüfungskandidaten oder eine Note -- es geht ausschließlich um die interne Konsistenz der Aufgabenkonstruktion selbst, nicht um eine Prüfungsleistung.

Antworte ausschließlich mit JSON in der Form {"mismatch": <true|false>, "begruendung": "<ein bis zwei sachliche Sätze zur Konstruktion, nicht zu einer Prüfungsleistung>"}.

RESPONSE:
{
	"mismatch": true,
	"begruendung": "Die Teilaufgabe verlangt explizit eine **Aufzählung von 3 Beobachtungen** (Operator 'nennen') **sowie eine Bewertung** (Operator 'bewerten') dieser Beobachtungen. Der Erwartungshorizont liefert jedoch **nur die geforderten Beobachtungen als Faktenliste**, ohne eine **bewertende Abbildung der Eigen- oder Fremdgefährdung** (Anforderungsbereich III) oder eine strukturierte Begründung. Die Bewertung fehlt vollständig, obwohl sie durch den Operator gefordert ist."
}
```

Note this is arguably a **substantively correct finding** -- the Teilaufgabe
does ask for both "nennen" and "bewerten," and the Erwartungshorizont only
rewards the "nennen" half -- undermined only by the validator rejecting the
honest word for the second operator. That's a strong sign the fix belongs in
`schemas/flag.py::GRADING_WORDS`, not in the prompt.

---

## 3. The evaluation itself was invalid until now (2026-09-15)

Everything in §1 and §2 was measured **without a positive control and
without labelled negatives**, which means none of it measured judgement
quality at all. Two specific defects in the test setup:

**The one item in the whole corpus with a deliberately planted FORM-07
defect was never run.** `items/manifest.json`'s `known_weaknesses` records
exactly one: **C-02 ag.1.ta.1** ("asks to name causes; its Erwartungshorizont
rewards begruenden, bewerten and ableiten"). `scripts/smoke_run.py`'s set is
A-01 / C-03 / D-01 -- C-02 is not in it. So FORM-07 was only ever pointed at
items carrying no FORM-07 defect, and it was never once verified that it
catches the real thing.

**The items it *was* pointed at are labelled clean.** A-01/A-02/A-03 have no
entry in `known_weaknesses` at all. Every flag raised against them is, by the
corpus's own ground truth, a false positive -- but nothing in the pipeline
compared verdicts against that ground truth, so the over-firing read as an
open "needs a human grader" question rather than as a measurable failure.

### Measured results, positive + negative controls, same model

Run over C-02 (positive control) and A-01/A-02/A-03 (labelled clean), calling
the judge directly so `Flag()`'s grading-word validator cannot mask a
judgement result. `open-mistral-nemo` in both rows; only the prompt differs:

| Prompt | True pos. | False neg. | True neg. | False pos. | Specificity |
|---|---|---|---|---|---|
| §2 prompt (in `gateway/model_gateway.py` today) | 1 | 0 | 2 | **23** | **8%** |
| Revised prompt (below) | 1 | 0 | 25 | **0** | **100%** |

**The model is not the problem. The prompt was.** Three concrete defects in
the §2 prompt, each fixed in the revised one:

1. **One-sided priming.** It gave exactly one worked example, a *mismatch*,
   and none of a legitimate match. The model then echoed that example's own
   vocabulary back as its justification: for A-01 ag.1.ta.2 it wrote that the
   Erwartungshorizont has "keine analytischen Ursache-Wirkungs-Zusammenhänge"
   -- lifting the phrase straight from the prompt -- about an
   Erwartungshorizont that literally reads "Anleitung zum sicheren
   Rollatorgebrauch, **weil** erhaltene Mobilitaet die Selbstversorgung
   traegt". That is not a borderline judgement call; it is a false statement
   about text in the prompt, produced by priming.
2. **It never said what an Erwartungshorizont is.** An Erwartungshorizont is
   a marking scheme in note form -- always terse, always list-shaped, even
   for Anforderungsbereich-III operators. Without being told that, the model
   read normal note-form brevity as missing depth. The revised prompt states
   outright that terseness is never evidence of a mismatch.
3. **No evidence requirement, no default.** It asked an open yes/no question
   with no conservative default and no obligation to point at anything. The
   revised prompt requires a literal quote from the Erwartungshorizont
   (`beleg_zitat`) and instructs `mismatch=false` when none can be produced
   -- the same "no flag without evidence" discipline the rest of the project
   already enforces structurally (`schemas/flag.py`), applied to the model's
   own reasoning step rather than only to the Flag built afterwards.

**Landed 2026-09-15.** The revised prompt is now `FORM_07_PROMPT_TEMPLATE` in
`gateway/model_gateway.py`; `checks/llm/form_07.py` enforces "no quote, no
flag"; `tests/test_gateway_form_07.py` pins the three ingredients so they
can't be silently dropped. End-to-end through `checks/runner.py`: C-02 -> 1
flag on ag.1.ta.1 quoting the offending Erwartungspunkt; A-01 -> 0; C-03 -> 0
(and no grading-word crash, because no flag is built there any more).

### Caveats on these numbers

- **Sensitivity rests on n=1.** 25 labelled negatives is a solid specificity
  measurement; one planted defect is not a sensitivity measurement. Both
  prompts caught it, which distinguishes neither. More positive controls are
  needed before claiming FORM-07 detects what it should -- every rule already
  carries a `mutation` field (`MUT-FORM-07`) precisely so a harness can
  generate them, and that harness (`mutations/`) is still unbuilt.
- **The "bewerten" grading-word collision is unaffected** by any of this. It
  bites when a Flag is *constructed*, not when the judgement is made, so a
  0% false-positive rate makes it rarer without resolving it. A genuine
  finding on a Teilaufgabe whose operator is "bewerten"/"beurteilen" will
  still be rejected by `schemas/flag.py::GRADING_WORDS`. Still open, still a
  decision about that shared validator.
- **The §1/§2 grading rows above are now largely moot** as quality evidence:
  by ground truth every one of them is a false positive on a clean item. They
  are kept as a record of what was tried, not as an open grading task.
