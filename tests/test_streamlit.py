"""Exercise the evidence controls through Streamlit's actual script runner."""
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from crosscheck.db import Store
from crosscheck.models import Document, Evidence, Fact, Relationship, RelationshipKind


def test_repeated_fact_previews_and_filters(tmp_path):
    database = tmp_path / "test.db"
    store = Store(database)
    for name in ("a", "b", "c", "unrelated"):
        store.save_document(Document(id=name, filename=f"{name}.pdf", sha256=name, page_count=1))
        store.save_evidence(Evidence(id=name, document_id=name, page_index=0, text="Revenue was 100 million in FY24."))
        store.save_fact(Fact(id=name, document_id=name, evidence_id=name, subject="Revenue", predicate="revenue",
                             original_text="Revenue was 100 million in FY24.", value_number=100, unit="million", period="FY24"))
    for name in ("b", "c"):
        store.save_relationship(Relationship(id=name, left_fact_id="a", right_fact_id=name,
                                             kind=RelationshipKind.CORROBORATION, confidence=0.9,
                                             explanation="Matching revenue claims."))
    store.close()
    with patch("crosscheck.db.Store", side_effect=lambda *args: Store(database)):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
        assert not app.exception
        assert len(app.toggle) == 5
        app.toggle(key="show-page-b-left-a").set_value(True).run()
        assert not app.exception
        assert any("unavailable" in warning.value for warning in app.warning)
        app.text_input[0].set_value("missing term").run()
        assert not app.exception
        assert any("No matching facts" in info.value for info in app.info)
