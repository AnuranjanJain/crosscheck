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


if __name__ == "__main__":
    unittest.main()
