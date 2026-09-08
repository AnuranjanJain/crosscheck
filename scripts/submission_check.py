"""Resolve acceptance cases against actual stored facts, without altering them."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crosscheck.compare import _normalize_period  # noqa: E402
from crosscheck.db import Store  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="crosscheck.db")
    parser.add_argument("--output", default="evaluation/results.json")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "evaluation/cases.json").read_text(encoding="utf-8"))
    store = Store(args.database)
    try:
        documents = {doc.id: doc for doc in store.documents()}
        facts = store.facts()
        evidence = {fact.evidence_id: store.evidence(fact.evidence_id) for fact in facts}
        relationships = store.relationships()

        def resolve(side):
            target = manifest["documents"][side["document"]]
            return [fact for fact in facts if documents[fact.document_id].sha256 == target["sha256"]
                    and evidence[fact.evidence_id].page_index == side["pdf_page_index"]
                    and fact.value_number == float(side["value"])
                    and _normalize_period(fact.period) == _normalize_period(side["period"])]

        cases = []
        for case in manifest["cases"]:
            result = {"id": case["id"], "expected_label": case["expected_label"], "demonstrated": False}
            if "source" in case:
                source = case["source"]
                target = manifest["documents"][source["document"]]
                doc = next((doc for doc in documents.values() if doc.sha256 == target["sha256"]), None)
                result["demonstrated"] = bool(doc and any(issue.page_index == source["pdf_page_index"] and issue.code == "empty_page" for issue in store.issues(doc.id)))
            else:
                left, right = resolve(case["left"]), resolve(case["right"])
                ids = {(a.id, b.id) for a in left for b in right}
                match = next((rel for rel in relationships if ((rel.left_fact_id, rel.right_fact_id) in ids or (rel.right_fact_id, rel.left_fact_id) in ids) and rel.kind.value == case["expected_label"]), None)
                if match:
                    result.update(demonstrated=True, relationship=match.model_dump(mode="json"),
                                  facts=[fact.model_dump(mode="json") for fact in facts if fact.id in {match.left_fact_id, match.right_fact_id}],
                                  evidence=[evidence[fact.evidence_id].model_dump(mode="json") for fact in facts if fact.id in {match.left_fact_id, match.right_fact_id}])
            cases.append(result)
        result = {"note": "Actual pipeline outputs. Acceptance matches are not corpus accuracy. Unmatched cases remain visible.",
                  "documents": [doc.model_dump(mode="json") for doc in documents.values()],
                  "processing_configuration": {doc.sha256: store.processing_config(doc.id) for doc in documents.values()},
                  "facts": len(facts), "relationship_counts": dict(Counter(rel.kind.value for rel in relationships)),
                  "cases": cases}
        samples = {}
        for label_path in sorted((ROOT / "evaluation/labels").glob("*.json")):
            labels = json.loads(label_path.read_text(encoding="utf-8"))
            matches = {}
            for expected in labels["facts"]:
                matches[expected["id"]] = [fact for fact in facts
                    if documents[fact.document_id].filename == expected["document_filename"]
                    and evidence[fact.evidence_id].page_index == expected["pdf_page_index"]
                    and fact.value_number == expected.get("value_number")
                    and _normalize_period(fact.period) == _normalize_period(expected.get("period"))
                    and fact.unit == expected.get("unit")]
            classified = correct = abstained = 0
            for expected in labels["relationships"]:
                pairs = {(a.id, b.id) for a in matches[expected["left_fact_id"]] for b in matches[expected["right_fact_id"]]}
                predictions = {rel.kind.value for rel in relationships
                               if (rel.left_fact_id, rel.right_fact_id) in pairs or (rel.right_fact_id, rel.left_fact_id) in pairs}
                if len(predictions) == 1:
                    classified += 1
                    correct += expected["expected_label"] in predictions
                else:
                    abstained += 1
            samples[label_path.name] = {"labeled_facts": len(matches), "value_period_unit_matches": sum(bool(value) for value in matches.values()),
                                       "relationship_targets": len(labels["relationships"]), "classified": classified,
                                       "correct_classifications": correct, "unresolved_or_ambiguous": abstained}
        result["regression_samples"] = samples
        result["measurement_limits"] = "Value/period/unit coverage is not semantic precision. Samples overlap and were exposed during development. Missing discovery is counted separately from a classified error."
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({case["id"]: case["demonstrated"] for case in cases}, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
