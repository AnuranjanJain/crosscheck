# Evaluation protocol

## Submission measurement: 2026-09-09

`evaluation/results.json` contains actual stored case outputs, evidence records, document hashes and extraction configuration. Regenerate with `python scripts/submission_check.py`. The acceptance manifest is never read by extraction or comparison.

Four required case types resolve: Delhivery EBITDA corroboration (annual PDF page 36 versus earnings page 17), EBITDA time reconciliation (same pages, FY24 versus FY23), an SEC-attributed bank balance contradiction (additional public PDF page 11), and IMF empty text (PDF page 1). PDF page numbers here are one-based; records retain zero-based indexes. The SEC page was rendered and visually checked; its last table row prints 9/30/09. The complaint's assertions are attributed, not independently audited by this app.

| Dataset | Text coverage | Processing seconds | Development value/period/unit matches | Other regression split matches |
|---|---:|---:|---:|---:|
| Delhivery | 227/227 pages | 48.972 | 6/20 | 4/20 |
| India macroeconomy | 283/284 pages | 42.722 | 4/20 | 2/20 |
| Additional SEC complaint | 16/16 pages | 2.649 | Not labeled | Not labeled |

Times are observed per-document run-log totals, including comparison against the knowledge stored at that step. They are not isolated scalability benchmarks. Each of the four existing label files has 8 relationship targets; none resolved to a single stored classification under strict value/period/unit matching. Report these 32 unresolved targets as missed discovery, not 100% accuracy on an empty denominator. Overall semantic precision is unmeasured. Four chosen acceptance examples do not establish corpus accuracy.

The earlier held-out label files share 7 Delhivery and 14 India passages with development. They are exposed regression samples, not independent held-out evaluation. Preserve their filenames for compatibility, but do not describe their scores as unseen performance.

On one actual table-adjacent excerpt, the optional 1.5b coder model returned 2 accepted quotations and 3 rejected quotations in 15.68 seconds. The 7b model timed out after 60.03 seconds. Baseline extraction remains the reproducible demo default. Local AI is optional and its interpretation accuracy has not been measured.

Remaining limitations: heuristic entity identity, incomplete multi-column reconstruction, conservative unreadable-date rejection, weak macroeconomic coverage, and unmeasured semantic precision. The fixed examples show the requested behaviors; they do not remove these limits.

Evaluate Delhivery and India macroeconomy separately and report the same measures for each: extracted-fact grounding accuracy, relationship classification accuracy, abstention count, page coverage, and elapsed processing time.

Maintain two manually reviewed sets of at least 20 facts and 8 relationships per dataset. Use one set while improving extraction and keep the second hidden until final evaluation. Record each expected relationship, source PDF, PDF page index, exact passage, label, and rationale.

The final report must include actual measurements collected on the submission machine. Do not replace a missing genuine contradiction with a contextual difference. If an external PDF is needed, name it, retain provenance, and identify it separately from the starter data.

## Reviewed label package

Versioned labels live under [`evaluation/`](../evaluation/):

| File | Split | Dataset | Facts | Relationships |
|---|---|---|---:|---:|
| `labels/delhivery.development.v1.json` | development | delhivery | 20 | 8 |
| `labels/delhivery.held_out.v1.json` | held_out | delhivery | 20 | 8 |
| `labels/india_macroeconomy.development.v1.json` | development | india-macroeconomy | 20 | 8 |
| `labels/india_macroeconomy.held_out.v1.json` | held_out | india-macroeconomy | 20 | 8 |

Schema: [`evaluation/schema.json`](../evaluation/schema.json)

Each fact row includes `document_filename`, zero-based `pdf_page_index`, contiguous `evidence_quote`, expected fields (`subject`, `predicate`, `value_text`, `value_number`, `unit`, `period`, `scope`, `estimate_status`), and a short human rationale. Each relationship row names two fact ids, an `expected_label`, and a rationale.

Validate quotes and schema with:

```powershell
python scripts/validate_evaluation_labels.py
```

Rules for these labels:

- Quotes must occur contiguously in the pdfplumber page text for the listed page index.
- Do not treat the 24,137 deterministic candidates as an accuracy score.
- Keep development and held-out splits separate; do not tune against held-out.
- Do not label a period, unit, scope, or estimate-vintage difference as a contradiction.
- Current labels emphasize corroboration, contextual reconciliation, and insufficient evidence. They do not claim a reviewed likely-contradiction demo case yet.

## Current baseline measurement

On 2026-09-08, the earlier numeric-only deterministic extractor processed all six supplied PDFs (511 pages) in 199.21 seconds and stored 24,137 candidate facts. Its indexed reconciliation pass took about 2 seconds and produced 200 contextual reconciliations, with no automatic corroboration or likely-contradiction labels. These are pre-table-recovery processing measurements, not accuracy scores.

After adding table recovery, printed-page detection, and semantic-fact extraction, a smoke test processed the 27-page Delhivery Q4 FY24 earnings deck in 1.44 seconds. It recovered 58 tables, 895 candidate facts, 7 semantic facts, and no processing issues. This is a narrow smoke measurement; run the full benchmark again before final submission and report that result separately for both datasets.
