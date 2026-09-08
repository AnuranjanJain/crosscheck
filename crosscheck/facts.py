from __future__ import annotations

import re
from decimal import Decimal
from uuid import uuid4

from .identity import metric_key
from .models import Evidence, Fact

NUMBER = re.compile(r"(?<![A-Za-z0-9])(?P<currency>[₹$€£])?\s*(?P<number>\(?-?\d[\d,]*(?:\.\d+)?\)?)\s*(?P<unit>million|mn|billion|bn|crore|cr|lakh|percent|per cent|%|tonnes?|million tonnes?)?", re.I)
UNIT_CONTEXT = re.compile(r"\b(million|mn|billion|bn|crore|cr|lakh|percent|per cent|tonnes?|million tonnes)\b|%", re.I)
YEAR = re.compile(r"(?:FY|fiscal year|year ended|period ended|Q[1-4])\s*\d{2,4}(?:[-/]\d{2,4})?", re.I)
SEMANTIC_VERB = re.compile(
    r"\b(is|are|was|were|has|have|operates|provides|serves|achieved|increased|decreased|expects|plans|launched|announced|appointed|resigned)\b",
    re.I,
)
UNIT_SCALE = {
    "crore": Decimal("10"),
    "cr": Decimal("10"),
    "lakh": Decimal("0.1"),
    "billion": Decimal("1000"),
    "bn": Decimal("1000"),
}


def _number(match: re.Match[str], inherited_unit: str | None = None, inherited_currency: str | None = None) -> tuple[float | None, str | None, str | None]:
    raw = match.group("number").replace(",", "")
    negative = raw.startswith("(") and raw.endswith(")")
    raw = raw.strip("()")
    try:
        value = float(raw) * (-1 if negative else 1)
    except ValueError:
        return None, None, None
    unit = (match.group("unit") or inherited_unit or "").lower().replace("per cent", "percent")
    if unit in {"crore", "cr"}:
        value, unit = value * 10, "million"
    elif unit == "lakh":
        value, unit = value * 0.1, "million"
    elif unit in {"billion", "bn"}:
        value, unit = value * 1000, "million"
    elif unit == "mn":
        unit = "million"
    return value, unit or None, match.group("currency") or inherited_currency


def _source_precision_increment(raw_number: str, source_unit: str | None) -> float:
    normalized = raw_number.strip().strip("()").replace(",", "")
    decimal_places = len(normalized.partition(".")[2]) if "." in normalized else 0
    increment = Decimal(1).scaleb(-decimal_places)
    scale = UNIT_SCALE.get((source_unit or "").lower().strip(), Decimal(1))
    return float(increment * scale)


def _semantic_fact(evidence: Evidence, sentence: str) -> Fact | None:
    match = SEMANTIC_VERB.search(sentence)
    if not match:
        return None
    subject = sentence[: match.start()].strip(" ,:;-") or (evidence.heading or "document claim")
    predicate = sentence[match.start() :].strip()
    if len(subject) < 2 or len(predicate) < 8:
        return None
    return Fact(
        id=uuid4().hex,
        document_id=evidence.document_id,
        evidence_id=evidence.id,
        subject=subject[:160],
        predicate=predicate.lower()[:120],
        original_text=sentence[:1000],
        attributes={
            "extractor": "deterministic",
            "fact_type": "semantic",
            "metric_key": metric_key(subject, predicate),
            "source_page_index": evidence.page_index,
        },
    )


def extract_facts(evidence: Evidence) -> list[Fact]:
    facts: list[Fact] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", evidence.text):
        sentence = " ".join(sentence.split()).strip(" -")
        if len(sentence) < 12:
            continue
        if re.fullmatch(r"(?:page\s*)?\d{1,4}", sentence, re.I):
            continue
        period_spans = [item.span() for item in YEAR.finditer(sentence)]
        matches = [match for match in NUMBER.finditer(sentence)
                   if not any(start <= match.start("number") < end for start, end in period_spans)]
        if not matches:
            semantic_fact = _semantic_fact(evidence, sentence)
            if semantic_fact:
                facts.append(semantic_fact)
            continue
        periods = [item.group(0).replace(" ", "") for item in YEAR.finditer(sentence)]
        subject = sentence[: matches[0].start()].strip(" ,:;-")
        context_unit = UNIT_CONTEXT.search(sentence)
        inherited_unit = next((item.group("unit") for item in matches if item.group("unit")), None) or (context_unit.group(0) if context_unit else None)
        inherited_currency = next((item.group("currency") for item in matches if item.group("currency")), None)
        for index, match in enumerate(matches):
            if not (match.group("currency") or match.group("unit") or len(match.group("number").replace(",", "")) >= 2):
                continue
            value, unit, currency = _number(match, inherited_unit, inherited_currency)
            fact_subject = subject[-100:] if subject else (evidence.heading or "document claim")
            lowered = sentence.lower()
            scope = next((label for label in ("consolidated", "standalone") if label in lowered), None)
            estimate_status = next(
                (
                    label
                    for label, aliases in (
                        ("estimate", ("estimate", "estimated")),
                        ("projection", ("projection", "projected")),
                        ("actual", ("actual",)),
                    )
                    for alias in aliases
                    if alias in lowered
                ),
                None,
            )
            period = periods[index] if len(periods) == len(matches) else (periods[0] if periods else None)
            facts.append(
                Fact(
                    id=uuid4().hex,
                    document_id=evidence.document_id,
                    evidence_id=evidence.id,
                    subject=fact_subject[:160],
                    predicate=fact_subject.lower()[:120],
                    original_text=sentence[:1000],
                    value_text=match.group(0),
                    value_number=value,
                    unit=unit,
                    period=period,
                    scope=scope,
                    attributes={
                        "currency": currency,
                        "fact_type": "numeric",
                        "metric_key": metric_key(fact_subject, fact_subject),
                        "source_page_index": evidence.page_index,
                        "source_precision_increment": _source_precision_increment(
                            match.group("number"), match.group("unit") or inherited_unit
                        ),
                        "estimate_status": estimate_status,
                    },
                )
            )
    return facts
