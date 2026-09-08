# Evaluation protocol

Evaluate Delhivery and India macroeconomy separately and report the same measures for each: extracted-fact grounding accuracy, relationship classification accuracy, abstention count, page coverage, and elapsed processing time.

Maintain two manually reviewed sets of at least 20 facts and 8 relationships per dataset. Use one set while improving extraction and keep the second hidden until final evaluation. Record each expected relationship, source PDF, PDF page index, exact passage, label, and rationale.

The final report must include actual measurements collected on the submission machine. Do not replace a missing genuine contradiction with a contextual difference. If an external PDF is needed, name it, retain provenance, and identify it separately from the starter data.

## Current baseline measurement

On 2026-09-08, the deterministic extractor processed all six supplied PDFs (511 pages) in 199.21 seconds and stored 24,137 candidate facts. The current indexed reconciliation pass took about 2 seconds and produced 200 contextual reconciliations, with no automatic corroboration or likely-contradiction labels. These are processing measurements, not accuracy scores. Manual development and held-out labels still need to be completed before submission.
