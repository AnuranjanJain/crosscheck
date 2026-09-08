import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crosscheck.compare import candidate_pairs, compare_facts
from crosscheck.db import Store
from crosscheck.facts import extract_facts
from crosscheck.models import Document, Evidence, ExtractedTable, Fact, RelationshipKind
from crosscheck.pdf import detect_printed_page_label, sha256_bytes
from crosscheck.pipeline import process_pdf


class CrosscheckTests(unittest.TestCase):
    def fact(self, identifier: str, value: float, period: str, unit: str = "million") -> Fact:
        return Fact(id=identifier, document_id=f"doc-{identifier}", evidence_id=f"ev-{identifier}", subject="Revenue from contracts with customers", predicate="revenue from contracts with customers", original_text="Revenue was reported", value_text=str(value), value_number=value, unit=unit, period=period)

    def test_same_period_and_value_is_corroboration(self):
        self.assertEqual(compare_facts(self.fact("a", 81415.38, "FY24"), self.fact("b", 81415.38, "FY24")).kind, RelationshipKind.CORROBORATION)

    def test_same_context_different_value_is_likely_contradiction(self):
        left = self.fact("a", 6.4, "FY25", "percent")
        right = self.fact("b", 6.5, "FY25", "percent")
        left.scope = right.scope = "national accounts"
        left.attributes["estimate_status"] = right.attributes["estimate_status"] = "actual"
        self.assertEqual(compare_facts(left, right).kind, RelationshipKind.LIKELY_CONTRADICTION)

    def test_different_period_is_contextual_reconciliation(self):
        self.assertEqual(compare_facts(self.fact("a", 81415.38, "FY24"), self.fact("b", 72253.01, "FY23")).kind, RelationshipKind.CONTEXTUAL_RECONCILIATION)

    def test_hash_is_deterministic(self):
        self.assertEqual(sha256_bytes(b"crosscheck"), sha256_bytes(b"crosscheck"))

    def test_store_creates_missing_parent_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "new" / "crosscheck.db"
            store = Store(database_path)
            try:
                self.assertTrue(database_path.exists())
            finally:
                store.close()

    def test_delete_document_removes_its_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "crosscheck.db")
            fact = self.fact("a", 1, "FY24")
            store.save_document(Document(id=fact.document_id, filename="a.pdf", sha256="a", page_count=1))
            store.save_evidence(Evidence(id=fact.evidence_id, document_id=fact.document_id, page_index=0, text="Revenue was reported"))
            store.save_fact(fact)
            store.delete_document(fact.document_id)
            self.assertEqual(store.facts(), [])
            store.close()

    def test_crore_is_normalized_to_millions(self):
        evidence = Evidence(id="ev", document_id="doc", page_index=0, text="Revenue from services was ₹8,142 Cr in FY24.")
        fact = extract_facts(evidence)[0]
        self.assertEqual(fact.unit, "million")
        self.assertEqual(fact.value_number, 81420)

    def test_table_row_extracts_each_value_and_aligns_fiscal_periods(self):
        evidence = Evidence(id="ev", document_id="doc", page_index=0, text="Revenue from services (₹ Cr) 7,054 7,224 8,142 FY22 FY23 FY24")
        facts = extract_facts(evidence)
        self.assertEqual([fact.value_number for fact in facts], [70540, 72240, 81420])
        self.assertEqual([fact.period for fact in facts], ["FY22", "FY23", "FY24"])

    def test_fiscal_period_components_are_not_extracted_as_values(self):
        evidence = Evidence(
            id="ev",
            document_id="doc",
            page_index=0,
            text="Real GDP growth is projected at 6.6 percent in FY2025/26.",
        )
        facts = extract_facts(evidence)
        self.assertEqual([fact.value_number for fact in facts], [6.6])


    def test_different_reported_scope_is_reconciliation(self):
        left = self.fact("a", 74540.82, "FY24")
        right = self.fact("b", 81415.38, "FY24")
        left.scope, right.scope = "standalone", "consolidated"
        self.assertEqual(compare_facts(left, right).kind, RelationshipKind.CONTEXTUAL_RECONCILIATION)

    def test_same_value_for_different_metrics_is_insufficient(self):
        left = self.fact("a", 100, "FY24")
        right = self.fact("b", 100, "FY24")
        left.subject, left.predicate = "Operating revenue", "reports operating revenue"
        right.subject, right.predicate = "Net revenue", "reports net revenue"
        self.assertEqual(compare_facts(left, right).kind, RelationshipKind.INSUFFICIENT_EVIDENCE)

    def test_partial_metric_overlap_does_not_conflate_entities(self):
        left = self.fact("a", 6.5, "FY25", "percent")
        right = self.fact("b", 6.5, "FY25", "percent")
        left.subject, left.predicate = "India real GDP growth", "reports real GDP growth"
        right.subject, right.predicate = "Global GDP growth", "reports global GDP growth"
        self.assertEqual(compare_facts(left, right).kind, RelationshipKind.INSUFFICIENT_EVIDENCE)

    def test_shared_entity_and_metric_terms_allow_paraphrased_corroboration(self):
        left = self.fact("a", 6.5, "FY25", "percent")
        right = self.fact("b", 6.5, "FY25", "percent")
        left.subject, left.predicate = "India real GDP growth", "reports real GDP growth"
        right.subject, right.predicate = "India GDP growth", "reports GDP growth"
        self.assertEqual(compare_facts(left, right).kind, RelationshipKind.CORROBORATION)

    def test_reporting_time_boilerplate_is_not_a_metric_identity(self):
        left = self.fact("a", 100, "FY24")
        right = self.fact("b", 100, "FY24")
        left.subject = left.predicate = "trended largely flat during the first half of the year"
        right.subject = right.predicate = "during the year ended March"
        self.assertEqual(candidate_pairs([left, right]), [])

    def test_source_precision_allows_a_rounded_value_to_corroborate(self):
        left = self.fact("a", 1266, "FY24")
        right = self.fact("b", 1266.41, "FY24")
        left.value_text = "Rs. 1,266 million"
        right.value_text = "1,266.41 million"
        self.assertEqual(compare_facts(left, right).kind, RelationshipKind.CORROBORATION)

    def test_missing_period_does_not_imply_reconciliation(self):
        left = self.fact("a", 6.4, "")
        right = self.fact("b", 6.5, "")
        self.assertEqual(compare_facts(left, right).kind, RelationshipKind.INSUFFICIENT_EVIDENCE)

    def test_candidates_exclude_unresolved_pairs(self):
        unresolved = self.fact("a", 6.4, "")
        unrelated = self.fact("b", 6.5, "")
        self.assertEqual(candidate_pairs([unresolved, unrelated]), [])

    def test_percent_alias_matches_percent_unit(self):
        left = self.fact("a", 4.6, "FY24", "percent")
        right = self.fact("b", 4.6, "FY24", "%")
        self.assertEqual(compare_facts(left, right).kind, RelationshipKind.CORROBORATION)

    def test_fiscal_year_aliases_are_same_period(self):
        left = self.fact("a", 6.5, "FY24", "percent")
        right = self.fact("b", 6.5, "FY2024", "percent")
        self.assertEqual(compare_facts(left, right).kind, RelationshipKind.CORROBORATION)

    def test_fiscal_range_aliases_match_end_year(self):
        left = self.fact("a", 6.5, "2024-25", "percent")
        right = self.fact("b", 6.5, "FY25", "percent")
        self.assertEqual(compare_facts(left, right).kind, RelationshipKind.CORROBORATION)

    def test_incompatible_units_are_insufficient(self):
        left = self.fact("a", 6.5, "FY25", "percent")
        right = self.fact("b", 81415.38, "FY25", "million")
        self.assertEqual(compare_facts(left, right).kind, RelationshipKind.INSUFFICIENT_EVIDENCE)

    def test_vocabulary_only_overlap_is_insufficient(self):
        left = Fact(id="a", document_id="doc-a", evidence_id="ev-a", subject="Revenue from operations", predicate="reports revenue", original_text="Revenue discussion", value_text=None, value_number=None, unit=None, period="FY24")
        right = Fact(id="b", document_id="doc-b", evidence_id="ev-b", subject="Revenue from operations", predicate="reports revenue", original_text="Revenue discussion", value_text=None, value_number=None, unit=None, period="FY24")
        self.assertEqual(compare_facts(left, right).kind, RelationshipKind.INSUFFICIENT_EVIDENCE)

    def test_extracts_grounded_semantic_fact_without_a_number(self):
        evidence = Evidence(
            id="ev",
            document_id="doc",
            page_index=0,
            text="Delhivery operates an integrated logistics network across India.",
        )
        facts = extract_facts(evidence)
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].value_number, None)
        self.assertEqual(facts[0].original_text, evidence.text)
        self.assertEqual(facts[0].attributes["fact_type"], "semantic")

    def test_detects_printed_page_label_from_footer(self):
        self.assertEqual(detect_printed_page_label("Heading\nBody copy\nPage 27"), "27")
        self.assertIsNone(detect_printed_page_label("Heading\nBody copy\nFY2024"))

    def test_evidence_round_trip_preserves_extracted_table(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "crosscheck.db")
            try:
                store.save_document(Document(id="doc", filename="source.pdf", sha256="hash", page_count=1))
                evidence = Evidence(
                    id="ev",
                    document_id="doc",
                    page_index=0,
                    text="Revenue table",
                    tables=[
                        ExtractedTable(
                            bbox=(10, 20, 30, 40),
                            rows=[["Metric", "FY24"], ["Revenue", "100"]],
                        )
                    ],
                )
                store.save_evidence(evidence)
                self.assertEqual(store.evidence("ev"), evidence)
            finally:
                store.close()

    def test_foreign_keys_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "crosscheck.db")
            try:
                self.assertEqual(store.connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                with self.assertRaises(sqlite3.IntegrityError):
                    store.save_evidence(Evidence(id="ev", document_id="missing", page_index=0, text="Source text"))
            finally:
                store.close()

    def test_processing_a_new_document_preserves_existing_relationship(self):
        def fake_extract_document(_path: Path, data: bytes):
            suffix = data.decode("ascii")
            document = Document(
                id=f"doc-{suffix}",
                filename=f"{suffix}.pdf",
                sha256=sha256_bytes(data),
                page_count=1,
            )
            evidence = Evidence(
                id=f"ev-{suffix}",
                document_id=document.id,
                page_index=0,
                text=f"Net revenue was reported for {suffix}.",
            )
            return document, [evidence], []

        def fake_extract_facts(evidence: Evidence) -> list[Fact]:
            suffix = evidence.document_id.removeprefix("doc-")
            return [
                Fact(
                    id=f"fact-{suffix}",
                    document_id=evidence.document_id,
                    evidence_id=evidence.id,
                    subject="Net revenue",
                    predicate="reports net revenue",
                    original_text=evidence.text,
                    value_text="100" if suffix != "c" else "110",
                    value_number=100 if suffix != "c" else 110,
                    unit="million",
                    period="FY24" if suffix != "c" else "FY23",
                    scope="consolidated",
                    attributes={"metric_key": "net revenue", "estimate_status": "actual"},
                )
            ]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_paths = []
            for suffix in ("a", "b", "c"):
                source = root / f"{suffix}.pdf"
                source.write_bytes(suffix.encode("ascii"))
                source_paths.append(source)

            store = Store(root / "crosscheck.db")
            try:
                with patch("crosscheck.pipeline.extract_document", side_effect=fake_extract_document), patch(
                    "crosscheck.pipeline.extract_facts", side_effect=fake_extract_facts
                ):
                    process_pdf(source_paths[0], store, storage_root=root / "documents")
                    process_pdf(source_paths[1], store, storage_root=root / "documents")
                    first_relationship = next(
                        item
                        for item in store.relationships()
                        if {item.left_fact_id, item.right_fact_id} == {"fact-a", "fact-b"}
                    )
                    process_pdf(source_paths[2], store, storage_root=root / "documents")
                    preserved_relationship = next(
                        item
                        for item in store.relationships()
                        if {item.left_fact_id, item.right_fact_id} == {"fact-a", "fact-b"}
                    )
                self.assertEqual(preserved_relationship.id, first_relationship.id)
            finally:
                store.close()

    def test_evaluation_label_package_exists_with_required_counts(self):
        root = Path(__file__).resolve().parents[1]
        labels_dir = root / "evaluation" / "labels"
        required = [
            "delhivery.development.v1.json",
            "delhivery.held_out.v1.json",
            "india_macroeconomy.development.v1.json",
            "india_macroeconomy.held_out.v1.json",
        ]
        self.assertTrue((root / "evaluation" / "schema.json").exists())
        for name in required:
            path = labels_dir / name
            self.assertTrue(path.exists(), msg=f"missing {name}")
            payload = __import__("json").loads(path.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(payload["facts"]), 20, msg=name)
            self.assertGreaterEqual(len(payload["relationships"]), 8, msg=name)
            fact_ids = {fact["id"] for fact in payload["facts"]}
            for rel in payload["relationships"]:
                self.assertIn(rel["left_fact_id"], fact_ids)
                self.assertIn(rel["right_fact_id"], fact_ids)


if __name__ == "__main__":
    unittest.main()
