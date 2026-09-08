from __future__ import annotations

import tempfile
import json
from collections import Counter
from pathlib import Path

import streamlit as st

from crosscheck.db import Store
from crosscheck.models import Fact, RelationshipKind
from crosscheck.pdf import render_page
from crosscheck.pipeline import ProcessingEvent, process_pdf
from crosscheck.local_ai import installed_models, ollama_status


st.set_page_config(page_title="Crosscheck", page_icon="C", layout="wide")
st.markdown("""
<style>
.block-container { max-width: 1440px; padding-top: 2.5rem; padding-bottom: 3rem; }
h1 { font-size: 2rem !important; font-weight: 700 !important; }
h2, h3 { font-size: 1.25rem !important; }
[data-baseweb="tab-list"] { gap: 1.5rem; border-bottom: 1px solid #d9dfe5; }
[data-baseweb="tab"] { padding: 0.75rem 0.25rem; font-weight: 600; }
[data-testid="stExpander"] { border-radius: 6px; }
[data-testid="stMetricValue"] { font-size: 1.6rem; }
button { border-radius: 6px !important; }
@media (max-width: 640px) {
    .block-container { padding: 1.5rem 1rem; }
    [data-baseweb="tab-list"] { gap: 1rem; }
}
</style>
""", unsafe_allow_html=True)
st.title("Crosscheck")
st.caption("Evidence-first fact checking across documents")

store = Store(Path("crosscheck.db"))


def show_fact_evidence(
    label: str,
    fact_id: str,
    facts_by_id: dict[str, Fact],
    widget_namespace: str,
) -> None:
    fact = facts_by_id.get(fact_id)
    if fact is None:
        st.warning("The referenced fact is no longer available.")
        return

    evidence = store.evidence(fact.evidence_id)
    document = store.document(fact.document_id)
    filename = document.filename if document else "unknown document"
    details = [
        f"period: {fact.period or 'not extracted'}",
        f"unit: {fact.unit or 'not extracted'}",
        f"scope: {fact.scope or 'not extracted'}",
    ]
    estimate_status = fact.attributes.get("estimate_status")
    if estimate_status:
        details.append(f"status: {estimate_status}")

    st.markdown(f"**{label}**")
    st.markdown(f"**{fact.subject}**")
    st.caption(" · ".join(details))
    st.caption("Exact grounded quote")
    st.code(fact.original_text, language=None)
    if fact.attributes.get("attribution"):
        st.caption(f"Source attribution: {fact.attributes['attribution']}")
    if fact.attributes.get("column_header"):
        st.caption(f"Source column: {fact.attributes['column_header']}")

    if not evidence:
        st.warning("The source evidence record is unavailable.")
        return

    printed = f" · printed page {evidence.printed_page}" if evidence.printed_page else ""
    st.caption(f"{filename} · PDF page {evidence.page_index + 1}{printed}")
    with st.expander("Source text and recovered tables"):
        st.text(evidence.text)
        for index, table in enumerate(evidence.tables, start=1):
            st.caption(f"Recovered table {index}")
            st.dataframe(table.rows, width="stretch", hide_index=True)

    preview_key = f"show-page-{widget_namespace}-{fact.id}"
    show_preview = st.toggle("Show source page", key=preview_key)
    if show_preview and document:
        source = Path("data/documents") / f"{document.sha256}.pdf"
        if not source.exists():
            st.warning("The cached source PDF is unavailable for preview.")
            return
        try:
            st.image(
                render_page(source, evidence.page_index),
                caption=f"{document.filename}, PDF page {evidence.page_index + 1}",
            )
        except Exception as exc:  # noqa: BLE001 - a preview failure must not hide the evidence
            st.warning(f"Source-page preview unavailable: {exc}")


tab_docs, tab_facts, tab_compare = st.tabs(["Documents", "Facts", "Compare"])

with tab_docs:
    st.subheader("Add documents")
    uploads = st.file_uploader("Upload one or more PDFs", type=["pdf"], accept_multiple_files=True)
    use_ollama = st.checkbox(
        "Use local Ollama extraction",
        help="Requires Ollama and a locally downloaded model. Ungrounded model claims are rejected.",
    )
    reprocess = st.checkbox("Reprocess existing documents", value=False)
    ollama_model = "qwen2.5:3b"
    if use_ollama:
        try:
            model_options = installed_models()
        except (OSError, ValueError, KeyError, TypeError):
            model_options = []
        if model_options:
            ollama_model = st.selectbox("Local model", model_options)
        available, message = ollama_status(ollama_model)
        (st.success if available else st.warning)(message)
    if st.button("Process documents", type="primary", disabled=not uploads):
        with st.status("Processing documents", expanded=True) as status:
            live_log = st.empty()
            page_progress = st.empty()
            lines: list[str] = []
            outcomes: list[str] = []

            def report(event: ProcessingEvent) -> None:
                lines.append(f"{event.elapsed_seconds:7.2f}s | {event.filename} | {event.stage} | {event.message}")
                live_log.code("\n".join(lines[-40:]), language=None)
                if event.total_pages:
                    page_progress.progress(event.completed_pages / event.total_pages,
                                           text=f"{event.stage}: {event.completed_pages}/{event.total_pages} pages")
                if event.stage in {"complete", "completed_with_issues", "failed", "cached", "interrupted"}:
                    outcomes.append(event.stage)

            for upload in uploads or []:
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
                    handle.write(upload.getvalue())
                    temporary_path = Path(handle.name)
                try:
                    process_pdf(temporary_path, store, filename=upload.name, use_ollama=use_ollama,
                                ollama_model=ollama_model, force=reprocess, on_progress=report)
                except Exception as exc:
                    st.error(f"Processing failed: {type(exc).__name__}. See the run log.")
                finally:
                    temporary_path.unlink(missing_ok=True)
            failed = any(outcome in {"failed", "interrupted"} for outcome in outcomes)
            has_issues = "completed_with_issues" in outcomes
            status.update(label="Processing failed" if failed else "Completed with issues" if has_issues else "Processing complete",
                          state="error" if failed else "complete", expanded=failed or has_issues)
    runs = store.runs()
    if runs:
        with st.expander("Processing history"):
            for run in runs:
                st.caption(f"{run['filename']} | {run['status']}")
                st.download_button("Download run log", data=run["events"],
                                   file_name=f"crosscheck-{run['id']}.json", mime="application/json",
                                   key=f"log-{run['id']}")
            st.code("\n".join(event["message"] for event in json.loads(runs[0]["events"])[-40:]), language=None)
    documents = store.documents()
    if documents:
        st.dataframe(
            [
                {
                    "file": doc.filename,
                    "pages": doc.page_count,
                    "text pages": store.evidence_count(doc.id),
                    "status": doc.status,
                    "issues": len(store.issues(doc.id)),
                    "facts": store.document_stats(doc.id)["facts"],
                    "tables": store.document_stats(doc.id)["tables"],
                }
                for doc in documents
            ],
            width="stretch",
            hide_index=True,
        )
        for document in documents:
            with st.expander(f"{document.filename} details"):
                issues = store.issues(document.id)
                stats = store.document_stats(document.id)
                st.caption(f"{stats['facts']:,} grounded facts · {stats['tables']:,} recovered tables · {stats['text_pages']:,}/{document.page_count:,} pages with text")
                st.caption(f"SHA-256: {document.sha256}")
                if not issues:
                    for warning in document.warnings:
                        st.warning(warning)
                for issue in issues:
                    page = f"PDF page {issue.page_index + 1}: " if issue.page_index is not None else ""
                    message = "No extractable text. This page was skipped; OCR is not enabled." if issue.code == "empty_page" else issue.message
                    (st.warning if issue.recoverable else st.error)(page + message)
                if document.status == "failed":
                    source = Path("data/documents") / f"{document.sha256}.pdf"
                    if st.button("Retry failed document", key=f"retry-{document.id}") and source.exists():
                        process_pdf(source, store, filename=document.filename, use_ollama=use_ollama, ollama_model=ollama_model, force=True)
                        st.rerun()
    else:
        st.info("Upload the starter PDFs or any compatible PDF to begin.")

with tab_facts:
    st.subheader("Grounded facts")
    query = st.text_input("Search facts", placeholder="revenue, GDP, customers")
    total_facts = store.fact_count(query)
    display_limit = 200
    facts = store.facts(query, limit=display_limit)
    st.caption(f"Showing {len(facts):,} of {total_facts:,} matching facts.")
    if not facts:
        st.info("No matching facts." if query else "No facts extracted yet.")
    if facts:
        st.dataframe(
            [
                {
                    "subject": fact.subject,
                    "value": fact.value_text or fact.original_text[:80],
                    "unit": fact.unit or "",
                    "period": fact.period or "",
                    "scope": fact.scope or "",
                    "status": fact.status,
                    "fact_id": fact.id,
                }
                for fact in facts
            ],
            width="stretch",
            hide_index=True,
        )
        inspector_facts_by_id = {fact.id: fact for fact in facts}
        selected_fact_id = st.selectbox(
            "Inspect a fact",
            options=list(inspector_facts_by_id),
            format_func=lambda identifier: f"{inspector_facts_by_id[identifier].subject} · {identifier[:8]}",
        )
        show_fact_evidence("Grounded fact", selected_fact_id, inspector_facts_by_id, "fact-inspector")

with tab_compare:
    st.subheader("Cross-document relationships")
    relationships = store.relationships()
    result_path = Path("evaluation/results.json")
    reviewed = {}
    if result_path.exists():
        saved = json.loads(result_path.read_text(encoding="utf-8"))
        live_ids = {item.id for item in relationships}
        reviewed = {case["id"]: case["relationship"]["id"] for case in saved["cases"]
                    if case.get("demonstrated") and case.get("relationship", {}).get("id") in live_ids}
    selected_case = st.selectbox("Verified demonstration", ["All relationships"] + list(reviewed))
    counts = Counter(item.kind for item in relationships)
    st.caption(
        " | ".join(
            f"{kind.value.replace('_', ' ')}: {counts.get(kind, 0)}"
            for kind in RelationshipKind
        )
    )
    kind_options = ["all"] + [kind.value for kind in RelationshipKind]
    selected_kind = st.selectbox(
        "Relationship filter",
        options=kind_options,
        index=0,
    )
    show_low_evidence = st.checkbox(
        "Show low-evidence candidates",
        value=False,
        help="These candidates are retained for review but do not have enough context for a conclusion.",
    )
    filtered = relationships
    if selected_case in reviewed:
        filtered = [item for item in filtered if item.id == reviewed[selected_case]]
    if selected_kind != "all" and selected_case not in reviewed:
        filtered = [item for item in filtered if item.kind.value == selected_kind]
    if not show_low_evidence:
        filtered = [item for item in filtered if item.kind != RelationshipKind.INSUFFICIENT_EVIDENCE]
    display_relationships = filtered[:50]
    st.caption(f"Showing {len(display_relationships)} of {len(filtered)} filtered relationship records.")
    needed_ids = [item.left_fact_id for item in display_relationships] + [
        item.right_fact_id for item in display_relationships
    ]
    facts_by_id = {fact.id: fact for fact in store.facts_by_ids(needed_ids)}
    if not display_relationships:
        st.info("No relationships match the current filter. Try another label or enable low-evidence candidates.")
    for relationship in display_relationships:
        with st.expander(f"{relationship.kind.value.replace('_', ' ').title()} · {relationship.confidence:.0%}"):
            st.write(relationship.explanation)
            left_column, right_column = st.columns(2)
            with left_column:
                show_fact_evidence(
                    "Claim A",
                    relationship.left_fact_id,
                    facts_by_id,
                    f"{relationship.id}-left",
                )
            with right_column:
                show_fact_evidence(
                    "Claim B",
                    relationship.right_fact_id,
                    facts_by_id,
                    f"{relationship.id}-right",
                )

store.close()
