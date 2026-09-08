from __future__ import annotations

import re
from uuid import uuid4

from .models import Evidence, Fact

NUMBER = re.compile(r"(?<![A-Za-z0-9])(?P<currency>[₹$€£])?\s*(?P<number>\(?-?\d[\d,]*(?:\.\d+)?\)?)\s*(?P<unit>million|mn|billion|bn|crore|cr|lakh|percent|per cent|%|tonnes?|million tonnes?)?", re.I)
UNIT_CONTEXT = re.compile(r"\b(million|mn|billion|bn|crore|cr|lakh|percent|per cent|tonnes?|million tonnes)\b|%", re.I)
YEAR = re.compile(r"(?:FY|fiscal year|year ended|period ended|Q[1-4])\s*\d{2,4}(?:[-/]\d{2,4})?", re.I)


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


def extract_facts(evidence: Evidence) -> list[Fact]:
    facts: list[Fact] = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", evidence.text):
        sentence = " ".join(sentence.split()).strip(" -")
        if len(sentence) < 12:
            continue
        matches = list(NUMBER.finditer(sentence))
        periods = [item.group(0).replace(" ", "") for item in YEAR.finditer(sentence)]
        subject = sentence[: matches[0].start()].strip(" ,:;-") if matches else ""
        context_unit = UNIT_CONTEXT.search(sentence)
        inherited_unit = next((item.group("unit") for item in matches if item.group("unit")), None) or (context_unit.group(0) if context_unit else None)
        inherited_currency = next((item.group("currency") for item in matches if item.group("currency")), None)
        for index, match in enumerate(matches):
            if not (match.group("currency") or match.group("unit") or len(match.group("number").replace(",", "")) >= 2):
                continue
            value, unit, currency = _number(match, inherited_unit, inherited_currency)
            fact_subject = subject[-100:] if subject else (evidence.heading or "document claim")
            scope = next((label for label in ("consolidated", "standalone", "estimate", "estimated", "projection", "actual") if label in sentence.lower()), None)
            period = periods[index] if len(periods) == len(matches) else (periods[0] if periods else None)
            facts.append(Fact(id=uuid4().hex, document_id=evidence.document_id, evidence_id=evidence.id, subject=fact_subject[:160], predicate=fact_subject.lower()[:120], original_text=sentence[:1000], value_text=match.group(0), value_number=value, unit=unit, period=period, scope=scope, attributes={"currency": currency, "source_page_index": evidence.page_index}))
    return facts
