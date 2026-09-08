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

Upload PDFs in the Documents tab. All data is stored in the local `crosscheck.db` SQLite file. The core extractor works without Ollama; the optional local model and embeddings are planned enhancement adapters.

To enable local-model extraction, install `requirements-local-ai.txt`, start Ollama, then download the model once:

```powershell
python -m pip install -r requirements-local-ai.txt
ollama pull qwen2.5:3b
```

Select **Use local Ollama extraction** before processing. The app rejects a model-produced claim unless its quoted evidence occurs verbatim in the source page text.

Run a reproducible local benchmark and export inspected results with:

```powershell
python scripts/evaluate.py path\to\first.pdf path\to\second.pdf
python scripts/export_results.py outputs\evaluation.db
python scripts/reconcile.py outputs\evaluation.db
```

## Video Demo

Add the final public demo link here after recording a video no longer than 3 minutes. The current walkthrough shows upload/processing status, grounded fact search, contextual reconciliation with dual evidence, and one extraction failure with its handling. Do not claim corroboration or likely-contradiction demos until those cases are manually verified in the live Compare view.

## Approach

The pipeline fingerprints each PDF, extracts page-level text with pdfplumber, stores evidence before creating facts, validates facts against that evidence, normalizes common units, and compares claims only when their extracted context makes the comparison meaningful. SQLite makes incremental processing and local inspection simple. Pydantic models make the data contract explicit. The UI deliberately shows source text beside every relationship so explanations remain auditable.

The deterministic baseline is the reliable path for the assignment. Install `requirements-local-ai.txt` after a local benchmark to add Ollama and sentence-transformer dependencies; model output must remain schema-constrained and evidence-validated.

## Limitations and Next Steps

The first release does not OCR image-only pages, reconstruct complex multi-page tables, or promise perfect semantic extraction. The baseline parser is intentionally conservative and may miss facts in unusual prose. Reviewed development and held-out labels now live under `evaluation/labels/` with a validator at `scripts/validate_evaluation_labels.py`. A production follow-up would add OCR, table structure recovery, embedding retrieval, model calibration, and scoring against those held-out labels.

## Additional Notes

The starter ZIP contains Delhivery and India macroeconomy datasets. The provided excerpts retain printed page labels from their original reports, so Crosscheck stores the PDF page index separately. No credentials, PDFs, model weights, or generated databases belong in this repository.
