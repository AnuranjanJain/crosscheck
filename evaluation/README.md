# Evaluation labels

Versioned, human-reviewed labels for Crosscheck.

## Layout

- `schema.json` — JSON Schema for every label file
- `labels/*.development.v1.json` — tuning set
- `labels/*.held_out.v1.json` — final-evaluation set

Each dataset file currently contains at least 20 facts and 8 relationships.

## Rules

- Quotes must occur contiguously in the pdfplumber page text for the listed `pdf_page_index`.
- Do not treat the 24,137 deterministic candidates as an accuracy score.
- Keep development and held-out splits separate.
- Do not label a period, unit, scope, or estimate-vintage difference as a contradiction.

## Validation

```powershell
python scripts/validate_evaluation_labels.py
```
