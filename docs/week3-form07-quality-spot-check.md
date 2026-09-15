# Week 3 FORM-07 quality spot check

Model: open-mistral-nemo

FORM-07's mechanism (extraction, anchoring, precondition gating, the
grading-language-safe operator-grounded prompt) is fully tested and works
end-to-end against the live model -- see `checks/llm/form_07.py` and
`gateway/model_gateway.py::judge_form_07`. Its **judgement quality** has not
been hand-graded, the same open item the German-quality spot check
(`docs/week2-german-quality-spot-check.md`) already carries for KOMP-01.

Grade each row: does the model's chosen operator for the Erwartungshorizont
side genuinely match the performance the graded points reward, or is the
model over-reading short factual phrases as a higher-order operator
("erläutern"/"planen") than the plain, list-like content actually
represents? Both flags below were raised on real corpus items and were
flagged as *possibly* false positives on first read during Week 3
development (see `notepad/handdown03.md`'s continuation notes) -- they need
an actual domain grader's read, not just a second guess from the same
pipeline that produced them.

## A-01 ag.1.ta.3

**Teilaufgabe (operator: planen, Anforderungsbereich III):** Planen Sie 3 Schritte fuer ein Beratungsgespraech mit der Tochter von Frau Ostermann zur Frage des Umzugs.

**Erwartungshorizont:**
- Anliegen und Sorgen der Tochter erheben (3.0)
- Wunsch von Frau Ostermann als Ausgangspunkt darstellen (4.0)
- Versorgungsalternativen im ambulanten Setting aufzeigen (3.0)

**Model judged Erwartungshorizont operator:** erläutern (Anforderungsbereich II) -> flagged as mismatch.

**Grade (correct mismatch / false positive / unsure):**

---

## A-01 ag.1.ta.4

**Teilaufgabe (operator: erläutern, Anforderungsbereich II):** Erlaeutern Sie 2 Moeglichkeiten, wie Sie Frau Ostermann bei der Wiederaufnahme sozialer Kontakte unterstuetzen.

**Erwartungshorizont:**
- Kontakt zum Chor ueber ein Telefonat oder einen Besuchsdienst herstellen (3.0)
- Begleitung beim Verlassen der Wohnung organisieren (3.0)

**Model judged Erwartungshorizont operator:** planen (Anforderungsbereich III) -> flagged as mismatch.

**Grade (correct mismatch / false positive / unsure):**

---

## C-03 ag.1.ta.3

**Teilaufgabe (operator: nennen, Anforderungsbereich I):** Nennen Sie 2 rechtliche Grundlagen fuer freiheitsentziehende Massnahmen.

**Erwartungshorizont:**
- richterliche Genehmigung erforderlich (3.0)
- rechtfertigender Notstand als Ausnahme (3.0)

**Model judged Erwartungshorizont operator:** erläutern (Anforderungsbereich II) -> flagged as mismatch.

**Grade (correct mismatch / false positive / unsure):**

---

## C-03 ag.1.ta.4

**Teilaufgabe (operator: nennen, Anforderungsbereich I):** Nennen Sie 2 Aspekte zur Einbeziehung der Tochter von Herrn Petrovic.

**Erwartungshorizont:**
- altersgerechte Information (2.5)
- Schweigepflicht beachten (2.5)

**Model judged Erwartungshorizont operator:** erläutern (Anforderungsbereich II) -> flagged as mismatch.

**Grade (correct mismatch / false positive / unsure):**

---

## Working hypothesis, unverified

All four flags share a pattern: the model called the Erwartungshorizont's
operator "erläutern" or "planen" (Anforderungsbereich II/III) against short,
list-like Erwartungspunkte that could plausibly still be "nennen"-level
(Anforderungsbereich I) -- i.e. a possible systematic bias toward reading
substantive-sounding short phrases as a higher cognitive level than their
actual form warrants. If a grader confirms several of these as false
positives, the fix is likely in `FORM_07_PROMPT_TEMPLATE`
(`gateway/model_gateway.py`) -- e.g. making explicit that a short, ungrounded
factual phrase is "nennen" even if its subject matter sounds substantive --
not a change to the extraction or comparison logic, which are deterministic
and already verified.
