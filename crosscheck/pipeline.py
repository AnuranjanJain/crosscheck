from __future__ import annotations

from pathlib import Path
from collections.abc import Callable
import shutil

from .compare import candidate_pairs
from .db import Store
from .facts import extract_facts
from .local_ai import extract_model_facts
from .pdf import extract_document, sha256_bytes


def process_pdf(path: str | Path, store: Store, filename: str | None = None, storage_root: str | Path = "data/documents", use_ollama: bool = False, ollama_model: str = "qwen2.5:3b", force: bool = False, on_progress: Callable[[str], None] | None = None) -> str:
    source = Path(path)
    data = source.read_bytes()
    existing = store.document_by_hash(sha256_bytes(data))
    if existing and not force:
        if on_progress:
            on_progress("Content hash already stored; reused existing results without extraction.")
        return existing.id
    if on_progress:
        on_progress(f"Extracting pages: {filename or source.name}")
    document, evidence, issues = extract_document(source, data, on_progress=on_progress) if on_progress else extract_document(source, data)
    if existing and force:
        store.delete_document(existing.id)
    document.filename = filename or source.name
    destination_directory = Path(storage_root)
    destination_directory.mkdir(parents=True, exist_ok=True)
    destination = destination_directory / f"{document.sha256}.pdf"
    if not destination.exists():
        shutil.copyfile(source, destination)
    store.save_document(document)
    new_facts = []
    for item in evidence:
        if on_progress:
            on_progress(f"Extracting facts: page {item.page_index + 1} of {document.page_count}")
        store.save_evidence(item)
        for fact in extract_facts(item):
            store.save_fact(fact)
            new_facts.append(fact)
        if use_ollama:
            if on_progress:
                on_progress(f"Calling Ollama ({ollama_model}): PDF page {item.page_index + 1}")
            model_facts, model_issues = extract_model_facts(item, ollama_model)
            if on_progress:
                on_progress(f"Ollama returned {len(model_facts)} accepted facts and {len(model_issues)} issues.")
                for issue in model_issues:
                    on_progress(issue.message)
            for fact in model_facts:
                store.save_fact(fact)
                new_facts.append(fact)
            issues.extend(model_issues)
            if any(issue.code in {"ollama_failure", "ollama_not_installed"} for issue in model_issues):
                use_ollama = False
                if on_progress:
                    on_progress("Model extraction stopped; remaining pages use the baseline extractor.")
        if on_progress:
            on_progress(f"Stored page {item.page_index + 1}; {len(new_facts)} total new facts so far.")
    for issue in issues:
        store.save_issue(issue)
    all_facts = store.facts()
    if on_progress:
        on_progress("Comparing grounded facts")
    new_fact_ids = {fact.id for fact in new_facts}
    relationships = candidate_pairs(all_facts, include_fact_ids=new_fact_ids)
    for relationship in relationships:
        store.save_relationship(relationship)
    if on_progress:
        on_progress(f"Stored {len(new_facts)} new facts, {len(relationships)} relationships and {len(issues)} issues.")
    return document.id
