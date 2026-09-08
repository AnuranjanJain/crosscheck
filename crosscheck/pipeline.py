from __future__ import annotations

from pathlib import Path
import shutil

from .compare import candidate_pairs
from .db import Store
from .facts import extract_facts
from .local_ai import extract_model_facts
from .pdf import extract_document


def process_pdf(path: str | Path, store: Store, filename: str | None = None, storage_root: str | Path = "data/documents", use_ollama: bool = False, ollama_model: str = "qwen2.5:3b", force: bool = False) -> str:
    source = Path(path)
    data = source.read_bytes()
    document, evidence, issues = extract_document(source, data)
    existing = store.document_by_hash(document.sha256)
    if existing and not force:
        return existing.id
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
        store.save_evidence(item)
        for fact in extract_facts(item):
            store.save_fact(fact)
            new_facts.append(fact)
        if use_ollama:
            model_facts, model_issues = extract_model_facts(item, ollama_model)
            for fact in model_facts:
                store.save_fact(fact)
                new_facts.append(fact)
            issues.extend(model_issues)
    for issue in issues:
        store.save_issue(issue)
    all_facts = store.facts()
    store.clear_relationships()
    for relationship in candidate_pairs(all_facts):
        store.save_relationship(relationship)
    return document.id
