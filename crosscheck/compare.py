from __future__ import annotations

import re
from collections import defaultdict
from itertools import combinations
from decimal import Decimal
from uuid import uuid4

from .models import Fact, Relationship, RelationshipKind


def _key(text: str) -> set[str]:
    ignored = {"from", "with", "the", "and", "for", "our", "was", "were"}
    return {word for word in re.findall(r"[a-z]{3,}", text.lower()) if word not in ignored}


def _terms(text: str, limit: int = 12) -> list[str]:
    ignored = {"from", "with", "the", "and", "for", "our", "was", "were"}
    ordered = dict.fromkeys(word for word in re.findall(r"[a-z]{3,}", text.lower()) if word not in ignored)
    return list(ordered)[:limit]


def compare_facts(left: Fact, right: Fact) -> Relationship:
    overlap = _key(left.subject + " " + left.predicate) & _key(right.subject + " " + right.predicate)
    same_period = bool(left.period and right.period and left.period.lower() == right.period.lower())
    same_unit = left.unit == right.unit
    different_scope = bool(left.scope and right.scope and left.scope != right.scope)
    different_period = bool(left.period and right.period and left.period.lower() != right.period.lower())
    different_unit = bool(left.unit and right.unit and left.unit != right.unit)
    if left.value_number is not None and right.value_number is not None:
        difference = abs(Decimal(str(left.value_number)) - Decimal(str(right.value_number)))
        if same_period and same_unit and difference == 0:
            kind, confidence, explanation = RelationshipKind.CORROBORATION, 0.98, "The claims report the same normalized value for the same period and unit."
        elif different_scope or different_period or different_unit:
            kind, confidence, explanation = RelationshipKind.CONTEXTUAL_RECONCILIATION, 0.91, "The claims use different reported scopes or estimate status, so their numerical difference is not classified as a contradiction."
        elif same_period and same_unit and difference > 0:
            kind, confidence, explanation = RelationshipKind.LIKELY_CONTRADICTION, 0.78, "The claims refer to the same apparent period and unit but report different normalized values; review scope and estimate status."
        elif difference == 0 and same_period and same_unit:
            kind, confidence, explanation = RelationshipKind.CORROBORATION, 0.92, "The claims match numerically for the same extracted period and unit."
        else:
            kind, confidence, explanation = RelationshipKind.INSUFFICIENT_EVIDENCE, 0.35, "The values are numerically different, but the extracted context is insufficient to classify the relationship safely."
    elif overlap:
        kind, confidence, explanation = RelationshipKind.CORROBORATION, 0.62, "The claims share subject vocabulary; semantic corroboration needs human review against both excerpts."
    else:
        kind, confidence, explanation = RelationshipKind.INSUFFICIENT_EVIDENCE, 0.2, "The claims do not share enough extracted context for a defensible comparison."
    return Relationship(id=uuid4().hex, left_fact_id=left.id, right_fact_id=right.id, kind=kind, confidence=confidence, explanation=explanation)


def candidate_pairs(facts: list[Fact], limit: int = 200, max_candidates: int = 25_000) -> list[Relationship]:
    relationships: list[Relationship] = []
    buckets: dict[tuple[str, str], list[int]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    examined = 0
    for index, right in enumerate(facts):
        terms = _terms(right.subject + " " + right.predicate)
        for token_pair in combinations(sorted(terms), 2):
            for left_index in buckets[token_pair]:
                left = facts[left_index]
                if left.document_id == right.document_id:
                    continue
                pair_id = tuple(sorted((left.id, right.id)))
                if pair_id in seen:
                    continue
                seen.add(pair_id)
                relationship = compare_facts(left, right)
                examined += 1
                if relationship.kind != RelationshipKind.INSUFFICIENT_EVIDENCE:
                    relationships.append(relationship)
                if len(relationships) >= limit or examined >= max_candidates:
                    return relationships
            if len(buckets[token_pair]) < 250:
                buckets[token_pair].append(index)
    return relationships
