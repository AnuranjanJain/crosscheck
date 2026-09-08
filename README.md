# Crosscheck

Crosscheck is a local, evidence-first fact knowledge layer for comparing claims across PDFs. It extracts numerical and semantic facts, keeps every accepted fact tied to a source passage and PDF page, and classifies cross-document relationships as corroboration, likely contradiction, contextual reconciliation, or insufficient evidence.

## Setup and Run Instructions

Python 3.11+ is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Upload PDFs in the Documents tab. All data is stored in the local `crosscheck.db` SQLite file. The core extractor works without Ollama. Local-model extraction is optional; embedding retrieval is not implemented.

To enable local-model extraction, install `requirements-local-ai.txt`, start Ollama, then download the model once:

```powershell
python -m pip install -r requirements-local-ai.txt
ollama pull qwen2.5:3b
```

Select **Use local Ollama extraction**, then choose a model from the installed-model selector before processing. The app rejects a model-produced claim unless its quoted evidence occurs verbatim in the source page text. Installing the Python client does not download model weights; an existing Ollama model can be selected instead of downloading the suggested model.

If a PDF is already stored, select **Reprocess existing documents** to apply a changed extractor or enable model extraction for it. Model requests use localhost with a 60-second timeout. If the model is unavailable, the document records an issue and remaining pages use the baseline extractor. A matching quote verifies the citation, not every interpretation made by the model.

For development checks:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check .
```

Run a reproducible local benchmark and export inspected results with:

```powershell
python scripts/evaluate.py path\to\first.pdf path\to\second.pdf
python scripts/export_results.py outputs\evaluation.db
python scripts/reconcile.py outputs\evaluation.db
```

## Video Demo

Add the final public demo link here after recording a video no longer than 3 minutes. The current walkthrough shows upload/processing status, grounded fact search, contextual reconciliation with dual evidence, and one extraction failure with its handling. Do not claim corroboration or likely-contradiction demos until those cases are manually verified in the live Compare view.

## Approach

The pipeline fingerprints each PDF, extracts page text plus recoverable table rows and locations, and stores evidence before creating facts. It keeps PDF page indexes separate from best-effort printed page labels. The deterministic baseline extracts normalized numerical claims and grounded semantic claims; optional Ollama extraction must return an exact source quote before a fact is accepted. Pydantic models make the data contract explicit.

The comparison engine requires an explicit metric identity before drawing a numerical conclusion. It checks period, scope, unit, and estimate status before a contradiction label, and derives rounding intervals from source precision instead of using a fixed percentage tolerance. New uploads compare only their new facts against stored facts; the explicit `scripts/reconcile.py` command remains available when comparison rules change. The UI shows the exact quote, metadata, source text, recovered tables, and an on-demand page render for each relationship.

## Limitations and Next Steps

The first release does not OCR image-only pages, reconstruct complex multi-page tables, or promise perfect semantic extraction. The baseline parser is intentionally conservative and may miss facts in unusual prose. Reviewed development and held-out labels now live under `evaluation/labels/` with a validator at `scripts/validate_evaluation_labels.py`. The supplied PDFs still do not have a reviewed likely-contradiction case, so the final demo must add a provenance-backed example before submission rather than mislabel an estimate, period, unit, or scope difference. A production follow-up would add OCR, stronger table reconstruction, embedding retrieval, model calibration, and held-out scoring.

## Additional Notes

AI assistance was used for implementation, debugging, and regression checks. Tests use synthetic fixtures for repeatability; they are not submission evidence or accuracy measurements.

Submission remains incomplete until real corroboration and likely-contradiction examples are verified, held-out accuracy is measured, and the GitHub and video links are added. Successful runtime checks do not establish those requirements.

The starter ZIP contains Delhivery and India macroeconomy datasets. The provided excerpts retain printed page labels from their original reports, so Crosscheck stores the PDF page index separately. No credentials, PDFs, model weights, or generated databases belong in this repository.
