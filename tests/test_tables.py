from crosscheck.compare import candidate_pairs
from crosscheck.models import Evidence, ExtractedTable, RelationshipKind
from crosscheck.tables import attributed_table_facts, period_table_facts


def test_table_units_periods_and_rounding():
    left = Evidence(id="a", document_id="a", page_index=0, text="GBP\n£ in Million\nEBITDA 1266.41 100",
                    tables=[ExtractedTable(rows=[["Metric", "March 31, 2024", "March 31, 2023"], ["EBITDA", "1266.41", "100"]])])
    right = Evidence(id="b", document_id="b", page_index=0, text="£ Cr\nEBITDA 127 10",
                     tables=[ExtractedTable(rows=[["Metric", "FY24", "FY23"], ["EBITDA", "127", "10"]])])
    facts = period_table_facts(left) + period_table_facts(right)
    assert len(facts) == 4
    assert any(item.kind == RelationshipKind.CORROBORATION for item in candidate_pairs(facts))
    assert any(item.kind == RelationshipKind.CONTEXTUAL_RECONCILIATION for item in candidate_pairs(facts))


def test_attributed_table_retains_distinct_assertions_and_rejects_unreadable_date():
    evidence = Evidence(id="e", document_id="d", page_index=0, text="9/30/09 $100 $900\n3/3I/08 $200 $700",
                        tables=[ExtractedTable(rows=[["Date", "Balance per bank", "Balance per company"],
                                                     ["9/30/09", "$100", "$900"], ["3/3I/08", "$200", "$700"]])])
    facts = attributed_table_facts(evidence)
    assert len(facts) == 2
    assert facts[0].period == "2009-09-30"
    relationships = candidate_pairs(facts)
    assert relationships[0].kind == RelationshipKind.LIKELY_CONTRADICTION
    assert "not independently audited" in relationships[0].explanation
