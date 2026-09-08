from unittest.mock import patch

import pytest

from crosscheck.db import Store
from crosscheck.models import Document, Evidence
from crosscheck.pdf import sha256_bytes
from crosscheck.pipeline import process_pdf


def test_cache_configuration_and_interruption_preserve_results(tmp_path):
    source = tmp_path / "example.pdf"
    source.write_bytes(b"sample")
    store = Store(tmp_path / "state.db")

    def extract(path, data, **kwargs):
        return Document(id="doc", filename="sample.pdf", sha256=sha256_bytes(data), page_count=1, status="ready"), [
            Evidence(id="ev", document_id="doc", page_index=0, text="Revenue was 100 million in FY24.")], []

    try:
        with patch("crosscheck.pipeline.extract_document", side_effect=extract) as extraction:
            events = []
            process_pdf(source, store, storage_root=tmp_path, on_progress=events.append)
            original = store.facts()
            process_pdf(source, store, storage_root=tmp_path, on_progress=events.append)
            assert extraction.call_count == 1
            assert events[-1].stage == "cached"
            with patch("crosscheck.pipeline.extract_model_facts", side_effect=KeyboardInterrupt):
                with pytest.raises(KeyboardInterrupt):
                    process_pdf(source, store, storage_root=tmp_path, use_ollama=True)
            assert extraction.call_count == 2
            assert store.facts() == original
            assert store.runs()[0]["status"] == "interrupted"
            with patch.object(store, "save_fact", side_effect=RuntimeError("write failure")):
                with pytest.raises(RuntimeError):
                    process_pdf(source, store, storage_root=tmp_path, force=True)
            assert store.facts() == original
    finally:
        store.close()
