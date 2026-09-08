# Evaluation protocol

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
