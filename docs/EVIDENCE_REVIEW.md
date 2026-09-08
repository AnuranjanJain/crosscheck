# Evidence Review

Reviewed on 2026-09-09. `evaluation/cases.json` records source fingerprints, exact text-layer quotations, context, expected labels, and reasoning. This is an acceptance manifest, not extracted output. A case is demonstrated only after the normal pipeline produces matching stored facts and a relationship.

## Starter Cases

- Delhivery postal coverage: annual report PDF index 21 reports 18,793 PIN codes as of March 31, 2024. Earnings PDF index 7 reports the same count in Q4 FY24. This is cross-document corroboration from the same publisher; source independence is not claimed.
- India GDP: RBI PDF index 7 gives 6.5 percent for 2024-25. IMF PDF index 4 gives 6.5 in the 2024/25 column and explicitly defines April-March fiscal years. Both corroborate the value, but may share underlying official data.
- India estimate revision: Survey PDF index 3 explicitly uses the first advance estimate (6.4 percent); RBI index 7 explicitly uses the February 28, 2025 second advance estimate (6.5 percent). This is contextual reconciliation, not a contradiction.
- Delhivery capacity: prospectus index 42 gives 3.70 million shipments/day as of December 31, 2021; annual report index 21 gives 7.1 million as of March 31, 2024. The dates differ.

The development revenue label needs extra care: the earnings presentation says revenue from services, while the annual report says revenue from operations. Earnings PDF index 16 reports FY24 traded-goods revenue as a dash and revenue from customers as 8,142 crore. This supports reconciliation, but the postal-count example is cleaner and does not require assuming service revenue and operations revenue are always interchangeable.

## Additional Contradiction Evidence

The [SEC complaint against Satyam](https://www.sec.gov/files/litigation/complaints/2011/comp21915.pdf), filed April 5, 2011, is a real public PDF outside the starter data. It has 16 pages and SHA-256 `d0b597b95398b32a2c57b71923dd0a313219b688793955fd5a00276e978581f5`.

At PDF index 10 (printed page 11), paragraph 27 and its table explicitly compare Bank of Baroda account statements with Satyam's reported balances for the same dates. The March 31, 2008 row gives USD 10,972,784 per bank statements and USD 214,506,068 per Satyam, with USD 203,533,283 labeled overstatement. These are competing claims about the same account, date, and currency. Keep the SEC attribution: the application is reading a complaint, not independently auditing the account.

This case is within one source PDF. The assignment expressly requires cross-document corroboration, but does not impose that restriction on contradiction. Supporting within-document contradiction should require different assertions, not comparing a claim with itself. A published audit dispute provides more defensible evidence than incorrectly calling forecast revisions contradictory.

Text extraction introduces a capital `I` in `3/3I/08`. The tabular structure is recoverable with pdfplumber, but the rendered page must be checked before normalizing this date. A request without an identifying User-Agent returned HTTP 403; a request with an identifying research User-Agent succeeded. This external download is therefore not guaranteed on every network; retain provenance and expose a manual-download route.

## Evaluation Integrity

Exact (filename, PDF index, quote) comparison found seven shared unique passages between Delhivery development and held-out files and fourteen between India development and held-out files. These files must be described as reviewed regression samples, not independent held-out evaluation. Source overlap and prior development exposure prevent a claim of unseen accuracy.

The IMF first page has no extractable text; report the missing coverage and continue with readable pages. Do not infer why text is absent without rendering the original. Actual relationship discovery, extraction precision, and successful live processing must be measured separately from these manually reviewed expectations.
