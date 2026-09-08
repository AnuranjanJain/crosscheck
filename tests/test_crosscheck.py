import tempfile
import unittest
from pathlib import Path

from crosscheck.compare import candidate_pairs, compare_facts
from crosscheck.db import Store
from crosscheck.facts import extract_facts
from crosscheck.models import Document, Evidence, Fact, RelationshipKind
from crosscheck.pdf import sha256_bytes


class CrosscheckTests(unittest.TestCase):
    def fact(self, identifier: str, value: float, period: str, unit: str = "million") -> Fact:
        return Fact(id=identifier, document_id=f"doc-{identifier}", evidence_id=f"ev-{identifier}", subject="Revenue from contracts with customers", predicate="revenue from contracts with customers", original_text="Revenue was reported", value_text=str(value), value_number=value, unit=unit, period=period)

    def test_same_period_and_value_is_corroboration(self):
        self.assertEqual(compare_facts(self.fact("a", 81415.38, "FY24"), self.fact("b", 81415.38, "FY24")).kind, RelationshipKind.CORROBORATION)

    def test_same_context_different_value_is_likely_contradiction(self):
        self.assertEqual(compare_facts(self.fact("a", 6.4, "FY25", "percent"), self.fact("b", 6.5, "FY25", "percent")).kind, RelationshipKind.LIKELY_CONTRADICTION)

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

    def test_different_reported_scope_is_reconciliation(self):
        left = self.fact("a", 74540.82, "FY24")
        right = self.fact("b", 81415.38, "FY24")
        left.scope, right.scope = "standalone", "consolidated"
        self.assertEqual(compare_facts(left, right).kind, RelationshipKind.CONTEXTUAL_RECONCILIATION)

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
