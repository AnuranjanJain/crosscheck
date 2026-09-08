from __future__ import annotations

import tempfile
from collections import Counter
from pathlib import Path

import streamlit as st

from crosscheck.db import Store
from crosscheck.models import RelationshipKind
from crosscheck.pdf import render_page
from crosscheck.pipeline import process_pdf


st.set_page_config(page_title="Crosscheck", page_icon="C", layout="wide")
st.markdown(
    """
<style>
    .stApp { background: #f7f8f6; color: #17211c; }
    [data-testid="stHeader"] { background: rgba(247, 248, 246, 0.9); }
    h1 { font-family: Georgia, serif; color: #173b2a; margin-bottom: 0; }
    [data-baseweb="tab-list"] { gap: 1rem; border-bottom: 1px solid #dbe3dd; }
    [data-baseweb="tab"] { height: 3rem; padding: 0 0.2rem; font-weight: 600; }
    [data-baseweb="tab"]:hover { color: #1b6b47; }
    [aria-selected="true"] { color: #175e3d !important; border-bottom-color: #175e3d !important; }
    [data-testid="stDataFrame"] { border: 1px solid #dbe3dd; border-radius: 6px; }
    .stButton > button { border-radius: 5px; font-weight: 650; }
</style>
""",
    unsafe_allow_html=True,
)
st.title("Crosscheck")
st.caption("Evidence-first fact checking across documents")

store = Store(Path("crosscheck.db"))
tab_docs, tab_facts, tab_compare = st.tabs(["Documents", "Facts", "Compare"])

with tab_docs:
    st.subheader("Add documents")
    uploads = st.file_uploader("Upload one or more PDFs", type=["pdf"], accept_multiple_files=True)
    use_ollama = st.checkbox(
        "Use local Ollama extraction",
        help="Requires Ollama and a locally downloaded model. Ungrounded model claims are rejected.",
    )
    if st.button("Process documents", type="primary", disabled=not uploads):
        progress = st.progress(0, text="Preparing documents")
        for index, upload in enumerate(uploads or []):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
                handle.write(upload.getvalue())
                temporary_path = Path(handle.name)
            try:
                process_pdf(temporary_path, store, filename=upload.name, use_ollama=use_ollama)
            finally:
                temporary_path.unlink(missing_ok=True)
            progress.progress((index + 1) / len(uploads), text=f"Processed {upload.name}")
        progress.empty()
        st.success("Processing complete. Evidence is stored locally.")
    documents = store.documents()
    if documents:
        st.dataframe(
            [
                {
                    "file": doc.filename,
                    "pages": doc.page_count,
                    "status": doc.status,
                    "warnings": len(doc.warnings),
                }
                for doc in documents
            ],
            width="stretch",
            hide_index=True,
        )
        for document in documents:
            with st.expander(f"{document.filename} details"):
                for warning in document.warnings:
                    st.warning(warning)
                for issue in store.issues(document.id):
                    st.error(f"{issue.code}: {issue.message}")
                if document.status == "failed":
                    source = Path("data/documents") / f"{document.sha256}.pdf"
                    if st.button("Retry failed document", key=f"retry-{document.id}") and source.exists():
                        process_pdf(source, store, filename=document.filename, use_ollama=use_ollama, force=True)
                        st.rerun()
    else:
        st.info("Upload the starter PDFs or any compatible PDF to begin.")

with tab_facts:
    st.subheader("Grounded facts")
    query = st.text_input("Search facts", placeholder="revenue, GDP, customers")
    total_facts = store.fact_count(query)
    display_limit = 200
    if not query.strip():
        st.caption(f"{total_facts:,} facts stored. Enter a search term to inspect grounded claims.")
        facts = []
    else:
        facts = store.facts(query, limit=display_limit)
        shown = min(len(facts), display_limit)
        st.caption(f"Showing {shown:,} of {total_facts:,} matching facts.")
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

with tab_compare:
    st.subheader("Cross-document relationships")
    relationships = store.relationships()
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
        index=kind_options.index(RelationshipKind.CONTEXTUAL_RECONCILIATION.value)
        if RelationshipKind.CONTEXTUAL_RECONCILIATION.value in kind_options
        else 0,
    )
    show_low_evidence = st.checkbox(
        "Show low-evidence candidates",
        value=False,
        help="These candidates are retained for review but do not have enough context for a conclusion.",
    )
    filtered = relationships
    if selected_kind != "all":
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
            for label, fact_id in (("Claim A", relationship.left_fact_id), ("Claim B", relationship.right_fact_id)):
                fact = facts_by_id.get(fact_id)
                if not fact:
                    continue
                evidence = store.evidence(fact.evidence_id)
                st.markdown(f"**{label}:** {fact.original_text}")
                document = store.document(fact.document_id)
                filename = document.filename if document else "unknown document"
                if evidence:
                    printed = f", printed page {evidence.printed_page}" if evidence.printed_page else ""
                    st.caption(f"{filename} · PDF page {evidence.page_index + 1}{printed}")
                    st.code(evidence.text[:1600])
                    if document:
                        source = Path("data/documents") / f"{document.sha256}.pdf"
                        if source.exists():
                            try:
                                st.image(
                                    render_page(source, evidence.page_index),
                                    caption=f"{document.filename}, PDF page {evidence.page_index + 1}",
                                )
                            except Exception as exc:  # noqa: BLE001 - keep preview failures non-fatal
                                st.warning(f"Source-page preview unavailable: {exc}")

store.close()
