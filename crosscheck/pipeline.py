from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from pydantic import BaseModel

from .compare import candidate_pairs
from .db import Store
from .facts import extract_facts
from .local_ai import extract_model_facts
from .pdf import extract_document, sha256_bytes

EXTRACTOR_VERSION = "baseline-2"


class ProcessingEvent(BaseModel):
    run_id: str
    filename: str
    stage: str
    message: str
    elapsed_seconds: float
    completed_pages: int = 0
    total_pages: int = 0
    facts: int = 0
    issues: int = 0


def process_pdf(path: str | Path, store: Store, filename: str | None = None,
                storage_root: str | Path = "data/documents", use_ollama: bool = False,
                ollama_model: str = "qwen2.5:3b", force: bool = False,
                on_progress: Callable[[ProcessingEvent], None] | None = None) -> str:
    source = Path(path)
    name = filename or source.name
    started = perf_counter()
    run_id = uuid4().hex
    events: list[dict] = []
    config = json.dumps({"extractor": EXTRACTOR_VERSION, "model": ollama_model if use_ollama else None}, sort_keys=True)

    def emit(stage: str, message: str, **counts: int) -> None:
        event = ProcessingEvent(run_id=run_id, filename=name, stage=stage, message=message,
                                elapsed_seconds=round(perf_counter() - started, 3), **counts)
        events.append(event.model_dump())
        store.save_run(run_id, name, stage, events)
        if on_progress:
            on_progress(event)

    try:
        emit("processing", "Fingerprinting PDF")
        data = source.read_bytes()
        existing = store.document_by_hash(sha256_bytes(data))
        if existing and not force and existing.status == "ready" and store.processing_config(existing.id) == config:
            emit("cached", "Reused results for matching content and extraction configuration")
            return existing.id
        emit("reading", "Reading PDF text and tables")
        document, evidence, issues = extract_document(source, data, on_progress=lambda message: emit("reading", message)) if on_progress else extract_document(source, data)
        document.filename = name
        destination_directory = Path(storage_root)
        destination_directory.mkdir(parents=True, exist_ok=True)
        destination = destination_directory / f"{document.sha256}.pdf"
        if not destination.exists():
            shutil.copyfile(source, destination)
        if document.status == "failed" and existing:
            emit("failed", "PDF extraction failed; previous results retained", issues=len(issues))
            return existing.id
        new_facts = []
        for index, item in enumerate(evidence):
            new_facts.extend(extract_facts(item))
            if use_ollama:
                emit("model", f"Calling {ollama_model} for PDF page {item.page_index + 1}",
                     completed_pages=index, total_pages=len(evidence))
                model_facts, model_issues = extract_model_facts(item, ollama_model)
                new_facts.extend(model_facts)
                issues.extend(model_issues)
                for issue in model_issues:
                    emit("warning", issue.message)
                if any(issue.code in {"ollama_failure", "ollama_not_installed"} for issue in model_issues):
                    use_ollama = False
                    emit("warning", "Model unavailable; remaining pages use baseline extraction")
            emit("extracting", f"Extracted PDF page {item.page_index + 1}", completed_pages=index + 1,
                 total_pages=len(evidence), facts=len(new_facts), issues=len(issues))
        emit("comparing", "Comparing new claims with stored knowledge", facts=len(new_facts))
        retained = [fact for fact in store.facts() if not existing or fact.document_id != existing.id]
        relationships = candidate_pairs(retained + new_facts, include_fact_ids={fact.id for fact in new_facts})
        if issues and document.status != "failed":
            document.status = "completed_with_issues"
        # Replace only after extraction and reasoning finish; all writes roll back together.
        with store.transaction():
            if existing:
                store.delete_document(existing.id)
            store.save_document(document)
            for item in evidence:
                store.save_evidence(item)
            for fact in new_facts:
                store.save_fact(fact)
            for issue in issues:
                store.save_issue(issue)
            for relationship in relationships:
                store.save_relationship(relationship)
            store.save_config(document.id, config)
        emit("failed" if document.status == "failed" else "completed_with_issues" if issues else "complete",
             f"Saved {len(new_facts)} facts and {len(relationships)} relationships",
             completed_pages=len(evidence), total_pages=document.page_count, facts=len(new_facts), issues=len(issues))
        return document.id
    except BaseException as exc:
        emit("interrupted" if not isinstance(exc, Exception) else "failed", f"Processing stopped: {type(exc).__name__}. Previous committed results retained.")
        raise
