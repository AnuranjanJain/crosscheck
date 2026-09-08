from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from itertools import combinations
from uuid import uuid4

from .models import Fact, Relationship, RelationshipKind

IGNORED_WORDS = {"from", "with", "the", "and", "for", "our", "was", "were"}
UNIT_ALIASES = {
    "%": "percent",
    "pct": "percent",
    "per cent": "percent",
    "percentage": "percent",
    "mn": "million",
    "millions": "million",
    "bn": "billion",
    "billions": "billion",
    "cr": "crore",
    "crores": "crore",
}
UNIT_FAMILIES = {
    "percent": "ratio",
    "million": "currency_scale",
    "billion": "currency_scale",
    "crore": "currency_scale",
    "lakh": "currency_scale",
    "days": "duration",
    "customers": "count",
    "shipments": "count",
}
FISCAL_YEAR = re.compile(r"^FY\s*(\d{2}|\d{4})$", re.I)
FISCAL_RANGE = re.compile(r"^(?:FY\s*)?(\d{4})\s*[-/]\s*(\d{2}|\d{4})$", re.I)
YEAR_ONLY = re.compile(r"^(\d{4})$")


def _tokens(text: str) -> list[str]:
    return [word for word in re.findall(r"[a-z]{3,}", text.lower()) if word not in IGNORED_WORDS]


def _terms(text: str, limit: int = 12) -> list[str]:
    return list(dict.fromkeys(_tokens(text)))[:limit]


def _normalize_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    cleaned = " ".join(unit.strip().lower().split())
    if not cleaned:
        return None
    return UNIT_ALIASES.get(cleaned, cleaned)


def _unit_family(unit: str | None) -> str | None:
    normalized = _normalize_unit(unit)
    if normalized is None:
        return None
    if normalized in UNIT_FAMILIES:
        return UNIT_FAMILIES[normalized]
    if "percent" in normalized or normalized.endswith("%"):
        return "ratio"
    if any(token in normalized for token in ("million", "billion", "crore", "lakh", "rupee", "inr")):
        return "currency_scale"
    if "day" in normalized:
        return "duration"
    return normalized


def _expand_year(token: str) -> int | None:
    if len(token) == 2 and token.isdigit():
        return 2000 + int(token)
    if len(token) == 4 and token.isdigit():
        return int(token)
    return None


def _normalize_period(period: str | None) -> str | None:
    if period is None:
        return None
    cleaned = period.strip().upper().replace(" ", "")
    if not cleaned:
        return None
    match = FISCAL_YEAR.match(cleaned)
    if match:
        year = _expand_year(match.group(1))
        return f"FY{year}" if year else cleaned
    match = FISCAL_RANGE.match(cleaned)
    if match:
        end = _expand_year(match.group(2))
        if end is not None and len(match.group(2)) == 2:
            start = int(match.group(1))
            end = start // 100 * 100 + end if end < 100 else end
            if end < start:
                end += 100
        return f"FY{end}" if end else cleaned
    match = YEAR_ONLY.match(cleaned)
    if match:
        return match.group(1)
    return cleaned


def _fact_priority(fact: Fact) -> tuple[int, int, int]:
    has_period = 0 if fact.period else 1
    has_unit = 0 if fact.unit else 1
    has_scope = 0 if fact.scope else 1
    return (has_period, has_unit, has_scope)


def _relationship_rank(relationship: Relationship) -> tuple[int, float]:
    priority = {
        RelationshipKind.CORROBORATION: 0,
        RelationshipKind.LIKELY_CONTRADICTION: 1,
        RelationshipKind.CONTEXTUAL_RECONCILIATION: 2,
        RelationshipKind.INSUFFICIENT_EVIDENCE: 3,
    }
    return (priority[relationship.kind], -relationship.confidence)


def compare_facts(left: Fact, right: Fact) -> Relationship:
    left_unit = _normalize_unit(left.unit)
    right_unit = _normalize_unit(right.unit)
    left_family = _unit_family(left_unit)
    right_family = _unit_family(right_unit)
    left_period = _normalize_period(left.period)
    right_period = _normalize_period(right.period)

    same_period = bool(left_period and right_period and left_period == right_period)
    different_period = bool(left_period and right_period and left_period != right_period)
    reporting_scopes = {"standalone", "consolidated"}
    left_scope = left.scope.lower() if left.scope else None
    right_scope = right.scope.lower() if right.scope else None
    different_scope = bool(
        left_scope in reporting_scopes
        and right_scope in reporting_scopes
        and left_scope != right_scope
    )
    left_estimate = (left.attributes or {}).get("estimate_status")
    right_estimate = (right.attributes or {}).get("estimate_status")
    different_estimate = bool(left_estimate and right_estimate and left_estimate != right_estimate)
    same_unit = bool(left_unit and right_unit and left_unit == right_unit)
    different_unit = bool(left_unit and right_unit and left_unit != right_unit)
    incompatible_units = bool(left_family and right_family and left_family != right_family)

    if left.value_number is not None and right.value_number is not None:
        difference = abs(Decimal(str(left.value_number)) - Decimal(str(right.value_number)))
        if incompatible_units:
            kind, confidence, explanation = (
                RelationshipKind.INSUFFICIENT_EVIDENCE,
                0.25,
                "The claims use incompatible units, so they are not compared as the same metric.",
            )
        elif same_period and same_unit and difference == 0 and not different_scope:
            kind, confidence, explanation = (
                RelationshipKind.CORROBORATION,
                0.98,
                "The claims report the same normalized value for the same period and unit.",
            )
        elif different_scope or different_period or different_unit or different_estimate:
            reasons: list[str] = []
            if different_scope:
                reasons.append(f"scope ({left.scope} vs {right.scope})")
            if different_period:
                reasons.append(f"period ({left.period} vs {right.period})")
            if different_unit:
                reasons.append(f"unit ({left_unit} vs {right_unit})")
            if different_estimate:
                reasons.append(f"estimate status ({left_estimate} vs {right_estimate})")
            kind, confidence, explanation = (
                RelationshipKind.CONTEXTUAL_RECONCILIATION,
                0.91,
                "The claims differ by " + ", ".join(reasons) + ", so the numerical difference is not classified as a contradiction.",
            )
        elif same_period and same_unit and difference > 0:
            kind, confidence, explanation = (
                RelationshipKind.LIKELY_CONTRADICTION,
                0.78,
                "The claims refer to the same apparent period and unit but report different normalized values; review scope and estimate status.",
            )
        else:
            kind, confidence, explanation = (
                RelationshipKind.INSUFFICIENT_EVIDENCE,
                0.35,
                "The values are numerically different, but the extracted context is insufficient to classify the relationship safely.",
            )
    else:
        kind, confidence, explanation = (
            RelationshipKind.INSUFFICIENT_EVIDENCE,
            0.2,
            "The claims do not share enough extracted numeric context for a defensible comparison.",
        )

    return Relationship(
        id=uuid4().hex,
        left_fact_id=left.id,
        right_fact_id=right.id,
        kind=kind,
        confidence=confidence,
        explanation=explanation,
    )


def candidate_pairs(facts: list[Fact], limit: int = 200, max_candidates: int = 80_000) -> list[Relationship]:
    ordered = sorted(range(len(facts)), key=lambda index: _fact_priority(facts[index]))
    relationships: list[Relationship] = []
    buckets: dict[tuple[str, str], list[int]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    examined = 0

    for index in ordered:
        right = facts[index]
        terms = _terms(f"{right.subject} {right.predicate}")
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
                if examined >= max_candidates:
                    relationships.sort(key=_relationship_rank)
                    return relationships[:limit]
            if len(buckets[token_pair]) < 250:
                buckets[token_pair].append(index)

    relationships.sort(key=_relationship_rank)
    return relationships[:limit]
