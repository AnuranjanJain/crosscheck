# Submission builder log

## 2026-09-09: evidence checkpoint

Baseline pytest discovery failed on old generated-output directories. Restricted discovery to tests; 29 existing tests and Ruff then passed. All four label files passed source-quote validation.

Added an acceptance manifest independently of the extractor. Reviewed cross-document postal coverage and GDP agreement, estimate revisions, time-dependent capacity, an SEC-reported bank balance discrepancy, and an unextractable page. AI assistance was used for code inspection and source review.

The label audit found 7 overlapping Delhivery and 14 overlapping India passages between development and held-out files. These are regression samples, not independent held-out evidence. The manifest explicitly marks pipeline demonstration as unverified.

Checkpoint commit: `docs: establish reviewed evidence and submission acceptance cases`.

## Extraction and comparison checkpoint

Added date/period-aligned table extraction with explicit units and source precision, plus attributed comparison of distinct assertions within a table. Excluded unreadable dates instead of repairing characters silently. Verified the SEC page render: its final row prints 9/30/09. The engine preserves that date exactly after normalization.

The pipeline now resolves EBITDA corroboration and period reconciliation across the annual report and earnings deck, the SEC table discrepancy, and the empty-page failure. Other reviewed targets remain unresolved in the case report. Added currency incompatibility protection and exact metric candidate retrieval for one-word metrics such as EBITDA.

On a real table-adjacent excerpt, qwen2.5-coder:1.5b accepted 2 facts and rejected 3 quotations in 15.68 seconds; qwen2.5-coder:7b timed out at 60.03 seconds with no accepted facts. Retain baseline extraction as the default, with the installed 1.5b model optional. These are narrow observations, not accuracy or full-document throughput claims.

32 tests and Ruff pass. Checkpoint commit: `fix: ground extracted claims and compare matching contexts`.

## Processing checkpoint

Processing now emits typed stage/page/count/elapsed events and stores downloadable run logs. Content plus extraction/model configuration determines cache reuse. Replacement writes occur in a transaction after extraction and comparison; interruption and injected write failure tests prove previous facts survive. Model failures and extraction warnings result in completed-with-issues rather than a misleading success message.

Logs are retained for reruns. A force-killed process can leave a nonterminal log and must be retried; automatic chunk resume and concurrent worker scheduling are not implemented. The UI bounds the visible log to 40 events, while the download contains the full run.

Checkpoint commit: `feat: add reliable processing states and authentic run logs`.
