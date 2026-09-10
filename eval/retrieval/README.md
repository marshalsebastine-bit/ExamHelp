# Expanding the Retrieval Evaluation Set

`queries.jsonl` is the manually labelled retrieval test set for the RAG prototype.
It lets us measure whether expected sources and their metadata appear in the top results
before and after a change to ingestion or ranking.

## File format

The file uses JSON Lines (JSONL): one complete JSON object on each line.
Do not surround all lines with `[` and `]`, and do not add commas between lines.

```json
{"query":"Was verlangt der Operator analysieren?","expected_sources":["Operatoren"],"expected_content_type":"operator","expected_operator":"analysieren"}
```

## Supported fields

| Field | Required | Meaning |
| --- | --- | --- |
| `query` | Yes | A natural-language query to retrieve evidence for. |
| `expected_sources` | Yes | One or more filename fragments that may match the expected source. |
| `expected_content_type` | No | Expected semantic chunk type, such as `operator`, `guidance`, or `checklist_item`. |
| `expected_operator` | No | Expected operator name, for example `begründen`. |
| `expected_section` | No | Expected value of `structure.section`, for example `Fallsituationen`. |
| `expected_source_locator` | No | Expected citation locator, for example `§ 4` or `Anhang 1`. |

`expected_sources` lists alternatives. The evaluator passes a source check when any one
of its entries matches. It does not require all listed sources to appear in one result.

## Examples

```json
{"query":"Welche Aufgaben gehören zur Erhebung und Feststellung des individuellen Pflegebedarfs?","expected_sources":["PflBG"],"expected_source_locator":"§ 4"}
{"query":"Welche Anforderungen gelten für die schriftlichen Aufsichtsarbeiten?","expected_sources":["PflAPrV"],"expected_source_locator":"§ 14"}
{"query":"Was verlangt der Operator analysieren?","expected_sources":["Operatoren"],"expected_content_type":"operator","expected_operator":"analysieren"}
{"query":"Wie sollen komplizierte Satzstrukturen in einer Fallsituation vermieden werden?","expected_sources":["Sprachsensibel"],"expected_content_type":"guidance","expected_section":"Fallsituationen"}
{"query":"Muss eine Aufgabenstellung die Anzahl der verlangten Antworten nennen?","expected_sources":["Sprachsensibel"],"expected_content_type":"checklist_item","expected_source_locator":"Anhang 1"}
```

## Labelling guidance

- Use questions that teachers, exam authors, or reviewers would actually ask.
- Add paraphrases rather than only copying terms from the source document.
- Cover each important legal provision with several queries.
- Include the document's distinctive structures: operators, checklist items, guidance,
  and legal provisions.
- Record the most specific metadata you can verify. This makes the test more useful.
- Include ordinary punctuation and capitalisation variations; user queries will contain both.
- Have a subject-matter expert review the expected source and locator.

Start with 20–30 labelled queries: about 10 legal queries, 10 Handreichung queries,
and 5–10 operator/checklist-focused queries.

## Run the evaluation

From the `rag_phase1` directory:

```bash
HF_HUB_OFFLINE=1 python3 scripts/evaluate.py --top-k 3
```

The command reports the rank of the first matching result for each line and returns a
non-zero exit code if any test does not meet the top-k threshold.
