from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from itertools import combinations
from uuid import uuid4

from .identity import fact_metric_key, metric_terms, shares_metric_identity
from .models import Fact, Relationship, RelationshipKind

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
VALUE_NUMBER = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?\)?")


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


def _source_precision_increment(fact: Fact) -> Decimal:
    stored = fact.attributes.get("source_precision_increment") if fact.attributes else None
    if isinstance(stored, (int, float, str)):
        try:
            value = Decimal(str(stored))
            if value > 0:
                return value
        except ArithmeticError:
            pass

    source = fact.value_text or str(fact.value_number or "")
    match = VALUE_NUMBER.search(source)
    if not match:
        return Decimal(0)
    raw = match.group(0).strip("()").replace(",", "")
    decimal_places = len(raw.partition(".")[2]) if "." in raw else 0
    return Decimal(1).scaleb(-decimal_places)


def _values_overlap_at_source_precision(left: Fact, right: Fact) -> bool:
    """Compare rounding intervals derived from each source's stated precision."""
    left_value = Decimal(str(left.value_number))
    right_value = Decimal(str(right.value_number))
    left_increment = _source_precision_increment(left)
    right_increment = _source_precision_increment(right)
    if left_increment == 0 or right_increment == 0:
        return left_value == right_value
    left_lower = left_value - left_increment / 2
    left_upper = left_value + left_increment / 2
    right_lower = right_value - right_increment / 2
    right_upper = right_value + right_increment / 2
    return max(left_lower, right_lower) < min(left_upper, right_upper)


def _fact_priority(fact: Fact) -> tuple[int, int, int, int]:
    has_period = 0 if fact.period else 1
    has_unit = 0 if fact.unit else 1
    has_scope = 0 if fact.scope else 1
    table_context = 0 if fact.attributes.get("extractor") in {"period_table", "attributed_table"} else 1
    return (table_context, has_period, has_unit, has_scope)


def _relationship_rank(relationship: Relationship) -> tuple[int, float]:
    priority = {
        RelationshipKind.CORROBORATION: 0,
        RelationshipKind.LIKELY_CONTRADICTION: 1,
        RelationshipKind.CONTEXTUAL_RECONCILIATION: 2,
        RelationshipKind.INSUFFICIENT_EVIDENCE: 3,
    }
    return (priority[relationship.kind], -relationship.confidence)


def compare_facts(left: Fact, right: Fact) -> Relationship:
    if not shares_metric_identity(left, right):
        return Relationship(
            id=uuid4().hex,
            left_fact_id=left.id,
            right_fact_id=right.id,
            kind=RelationshipKind.INSUFFICIENT_EVIDENCE,
            confidence=0.2,
            explanation="The claims do not identify the same metric, so no numerical conclusion is made.",
        )

    left_unit = _normalize_unit(left.unit)
    right_unit = _normalize_unit(right.unit)
    left_family = _unit_family(left_unit)
    right_family = _unit_family(right_unit)
    left_period = _normalize_period(left.period)
    right_period = _normalize_period(right.period)

    same_period = bool(left_period and right_period and left_period == right_period)
    different_period = bool(left_period and right_period and left_period != right_period)
    left_scope = left.scope.lower() if left.scope else None
    right_scope = right.scope.lower() if right.scope else None
    different_scope = bool(left_scope and right_scope and left_scope != right_scope)
    left_estimate = (left.attributes or {}).get("estimate_status")
    right_estimate = (right.attributes or {}).get("estimate_status")
    different_estimate = bool(left_estimate and right_estimate and left_estimate != right_estimate)
    same_unit = bool(left_unit and right_unit and left_unit == right_unit)
    different_unit = bool(left_unit and right_unit and left_unit != right_unit)
    incompatible_units = bool(left_family and right_family and left_family != right_family)
    left_currency = left.attributes.get("currency")
    right_currency = right.attributes.get("currency")
    if left_currency and right_currency and left_currency != right_currency:
        incompatible_units = True

    if left.value_number is not None and right.value_number is not None:
        difference = abs(Decimal(str(left.value_number)) - Decimal(str(right.value_number)))
        values_agree = _values_overlap_at_source_precision(left, right)
        if incompatible_units:
            kind, confidence, explanation = (
                RelationshipKind.INSUFFICIENT_EVIDENCE,
                0.25,
                "The claims use incompatible units, so they are not compared as the same metric.",
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
                "The claims differ by "
                + ", ".join(reasons)
                + ", so the numerical difference is not classified as a contradiction.",
            )
        elif same_period and same_unit and values_agree:
            precision_note = "The values match exactly."
            if difference:
                precision_note = "The sources' stated precision produces overlapping rounding intervals."
            kind, confidence, explanation = (
                RelationshipKind.CORROBORATION,
                0.98,
                f"The claims identify the same metric, period, and unit. {precision_note}",
            )
        elif same_period and same_unit and difference > 0:
            missing_context = [
                label
                for label, value in (("scope", left_scope and right_scope), ("estimate status", left_estimate and right_estimate))
                if not value
            ]
            caveat = ""
            if missing_context:
                caveat = " Missing " + " and ".join(missing_context) + " remains visible for review."
            kind, confidence, explanation = (
                RelationshipKind.LIKELY_CONTRADICTION,
                0.78 if not missing_context else 0.58,
                "The claims identify the same metric, period, and unit but report non-overlapping values."
                + caveat,
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


def candidate_pairs(
    facts: list[Fact],
    limit: int = 1000,
    max_candidates: int = 80_000,
    include_fact_ids: set[str] | None = None,
) -> list[Relationship]:
    """Return bounded cross-document comparisons, optionally only for new facts."""
    ordered = sorted(range(len(facts)), key=lambda index: _fact_priority(facts[index]))
    relationships: list[Relationship] = []
    attributed: dict[str, list[Fact]] = defaultdict(list)
    for fact in facts:
        group = fact.attributes.get("table_group")
        if group:
            attributed[group].append(fact)
    for group in attributed.values():
        for left, right in combinations(group, 2):
            if include_fact_ids is not None and left.id not in include_fact_ids and right.id not in include_fact_ids:
                continue
            relationship = compare_facts(left, right)
            relationship.explanation += (
                f" Attributed table assertions: {left.attributes['attribution']} versus "
                f"{right.attributes['attribution']}. These are statements reproduced in the source; "
                "the system has not independently audited them."
            )
            relationships.append(relationship)
    buckets: dict[tuple[str, str], list[int]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    examined = 0

    for index in ordered:
        right = facts[index]
        terms = list(dict.fromkeys(metric_terms(f"{right.subject} {right.predicate}")))[:12]
        keys = list(combinations(sorted(terms), 2))
        if fact_metric_key(right):
            keys.insert(0, ("exact", fact_metric_key(right)))
        for token_pair in keys:
            for left_index in buckets[token_pair]:
                left = facts[left_index]
                if left.document_id == right.document_id:
                    continue
                if include_fact_ids is not None and left.id not in include_fact_ids and right.id not in include_fact_ids:
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
