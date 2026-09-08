# Crosscheck Handoff For Claude Code

> Historical handoff: implementation has changed since this snapshot. Read README.md, the latest BUILDER_LOG.md repair entry, and the current source before acting on the tasks below. Current runtime checks pass, but model inference, four real demo cases, and submission links are not all verified.

## What This Project Is

Crosscheck is a local, evidence-first fact knowledge layer for the Superjoin VIT 2026 Engineering Intern assignment.

The user uploads unfamiliar PDFs. Crosscheck extracts numerical claims, preserves the original source wording, links each accepted fact to a PDF page and evidence passage, and compares claims across documents. The intended reviewer experience is a small research workbench where every relationship can be inspected instead of a black-box answer or a graph-only visualization.

The project is deliberately local-first. PDF content and the SQLite database stay on the machine. Ollama support is optional and must never allow an unsupported or ungrounded claim into the database.

## What Has Been Built

- Streamlit workspace with Documents, Facts, and Compare views.
- PDF upload, content hashing, duplicate detection, local storage, and processing progress.
- Page-level text extraction with `pdfplumber`.
- Source-page rendering with `pypdfium2`.
- Pydantic contracts for `Document`, `Evidence`, `Fact`, `Relationship`, and `ProcessingIssue`.
- SQLite persistence with resumable facts/evidence, document warnings, and retry support for failed documents.
- Deterministic numerical extraction with support for common units including `Cr`, `Mn`, `Bn`, crore, lakh, million, and billion.
- Basic fiscal-period and reporting-scope extraction.
- Indexed candidate matching by shared subject terms.
- Relationship labels: corroboration, likely contradiction, contextual reconciliation, and insufficient evidence.
- Optional schema-constrained Ollama extraction using `qwen2.5:3b`; model evidence must occur verbatim in the source text.
- Evaluation, export, and relationship-rebuild scripts under `scripts/`.
- Project-level Streamlit configuration disables usage telemetry, which is required in the restricted environment.
- README, architecture notes, evaluation protocol, demo script, and a contemporaneous builder log.

## Current Verified State

Environment:

- Python virtual environment: `.venv`
- Streamlit server: `http://127.0.0.1:8501`
- Hardware used for the benchmark: 16 GB RAM, NVIDIA RTX 3050 4 GB

Checks currently passing:

- `python -m pytest -q`: 11 passed
- `ruff check .`: clean
- `python -m compileall -q crosscheck app.py scripts`: clean
- Live Streamlit HTTP check: status 200
- Source-page rendering produced valid PNG output

Starter-dataset benchmark:

- Six PDFs, 511 pages total
- 24,137 deterministic fact candidates
- 199.21 seconds for first extraction run
- Indexed relationship rebuild completed in approximately 2 seconds
- Current deterministic baseline found 200 contextual reconciliations, 0 corroborations, and 0 likely contradictions

The last point is a limitation, not a success claim. Do not tell reviewers that all four assignment cases have been demonstrated.

## Assignment Acceptance Matrix

| Assignment requirement | Current state | Meaning |
|---|---|---|
| Accept new PDFs through UI/API | Working | Streamlit upload and processing path exists. |
| Extract meaningful numerical facts | Partially working | Strongest for explicit numeric prose and simple table rows; complex tables remain weak. |
| Extract semantic facts | Partial | Optional Ollama adapter exists; deterministic baseline is mostly numerical. |
| Link every fact to source evidence | Working for accepted facts | Facts reference stored evidence and PDF page index. |
| Corroboration case | Not yet demonstrated | Must be manually validated or improved through semantic retrieval. |
| Genuine/likely contradiction case | Not yet demonstrated | Do not manufacture one from a period, unit, scope, or estimate difference. |
| Contextual reconciliation case | Working in the comparison engine | Still needs a reviewer-ready, manually verified example. |
| Extraction/reasoning failure case | Working | Image-only page warning is a real example; OCR is not enabled. |
| Generalization beyond starter files | Architecture supports it | Must be tested with at least one unfamiliar PDF. |
| README and video | README/script prepared | Add the real demo URL and video after the four cases are verified. |

## What To Build Next

Work in this order. Preserve the current deterministic baseline while adding improvements behind explicit, testable boundaries.

### 1. Create a reviewed evaluation set — DONE

Completed under `evaluation/`:

- `evaluation/schema.json`
- `evaluation/labels/delhivery.development.v1.json`
- `evaluation/labels/delhivery.held_out.v1.json`
- `evaluation/labels/india_macroeconomy.development.v1.json`
- `evaluation/labels/india_macroeconomy.held_out.v1.json`
- validator: `python scripts/validate_evaluation_labels.py`

Each file has >=20 facts and >=8 relationships with filenames, zero-based PDF page indexes, exact contiguous evidence quotes, expected fields, labels, and rationales. Development and held-out are separate. Do not call the 24,137 candidates an accuracy score. These labels do not yet claim a reviewed likely-contradiction demo case.

### 2. Improve candidate retrieval

Add a local embedding adapter using a small sentence-transformer model, but keep the deterministic token index as a fallback. Retrieve only plausible cross-document pairs before comparison. Test that unrelated Delhivery and macroeconomy claims are not compared merely because both contain numbers.

### 3. Improve context extraction

Extract and validate reporting period, entity, scope, units, estimate/actual/projection status, and table headers. Use explicit context to classify relationships:

- same subject, same context, same normalized value -> corroboration;
- same subject, same context, different normalized value -> likely contradiction;
- same subject with explicit period, unit, scope, or estimate-status difference -> contextual reconciliation;
- missing context -> insufficient evidence.

Use `Decimal` or equivalent exact arithmetic where rounding affects a comparison. Preserve both claims and their source evidence.

### 4. Produce the four required cases

Find cases in the supplied documents first. If a genuine contradiction is not defensible, use clearly identified additional public PDFs with provenance and say so in the README. The final demo must show the evidence passage for both sides and the system explanation for the first three cases.

### 5. Add OCR only if it helps a demonstrated gap

The current IMF page-1 warning is an honest failure example. Add OCR only after measuring that it improves an important fact. Keep OCR optional and expose OCR failures as `ProcessingIssue` records.

### 6. Finish reviewer-facing polish

- Add relationship filtering by label and confidence.
- Show a compact relationship summary count.
- Make the evidence panel show document filename, PDF page index, printed page label when available, quote, and rendered page together.
- Add a clear provenance badge for deterministic versus Ollama extraction.
- Show processing elapsed time and cache hits.
- Keep low-evidence candidates behind an explicit control.

### 7. Complete the submission package

Update `README.md` with the real video URL, setup verification, evaluation results, four-case evidence table, limitations, and AI-tool disclosure. Update `docs/EVALUATION.md` with measured accuracy and abstention results. Record every material decision in `BUILDER_LOG.md`; never reconstruct a fake history.

## Important Files

- `app.py`: Streamlit UI and user workflow.
- `crosscheck/models.py`: typed data contracts.
- `crosscheck/pdf.py`: hashing, page extraction, and rendering.
- `crosscheck/facts.py`: deterministic numeric and context extraction.
- `crosscheck/compare.py`: candidate retrieval and relationship classification.
- `crosscheck/local_ai.py`: optional grounded Ollama adapter.
- `crosscheck/db.py`: SQLite schema and persistence.
- `crosscheck/pipeline.py`: document processing orchestration.
- `tests/test_crosscheck.py`: regression suite.
- `scripts/evaluate.py`: local benchmark.
- `scripts/export_results.py`: JSON export.
- `scripts/reconcile.py`: rebuild relationships after comparison-rule changes.
- `scripts/validate_evaluation_labels.py`: schema + exact-quote checks for reviewed labels.
- `evaluation/schema.json` and `evaluation/labels/*.v1.json`: development/held-out reviewed labels.
- `README.md`: required assignment submission sections.
- `docs/DEMO_SCRIPT.md`: planned 2 minute 50 second walkthrough.
- `docs/EVALUATION.md`: evaluation protocol and label package notes.
- `BUILDER_LOG.md`: implementation decisions and verified observations.

## Commands

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest -q
ruff check .
python scripts/validate_evaluation_labels.py
streamlit run app.py
```

For a fresh evaluation:

```powershell
python scripts/evaluate.py path\to\first.pdf path\to\second.pdf --database outputs\evaluation.db
python scripts/reconcile.py outputs\evaluation.db
python scripts/export_results.py outputs\evaluation.db --output outputs\results.json
```

## Rules For The Next Agent

- Read the provided AGENTS instructions (and `AGENTS.md` if it exists), this file, `README.md`, and `docs/EVALUATION.md` before editing.
- Do not hard-code starter filenames, expected facts, or demo labels into production logic.
- Do not call a difference a contradiction without checking period, unit, scope, and estimate status.
- Do not claim the four required cases until each has a source quote and a human-reviewed rationale.
- Keep secrets, PDFs, model weights, databases, and generated outputs out of Git.
- Add a focused regression test for every extraction or classification repair.
- Run pytest and Ruff before reporting completion.
