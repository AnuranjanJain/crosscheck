# Architecture decisions

Crosscheck processes PDFs locally. It stores the document content hash, page-level evidence, extracted facts, relationships, and failures in SQLite. Facts contain their original source wording and a small extensible attributes object. Relationships always point to two facts, which in turn point to evidence.

The baseline parser recognizes numerical claims and common reporting periods. It performs unit normalization for crore, lakh, and billion when the source specifies those units. The comparison engine only labels a numerical discrepancy as a likely contradiction when both period and normalized unit match. Different periods are reported as contextual reconciliation, not an error.

Ollama and semantic embeddings are dependencies reserved for a later adapter. This preserves a runnable, inspectable core when a reviewer does not have a local model installed. Any future model output must validate against page evidence before storage.
