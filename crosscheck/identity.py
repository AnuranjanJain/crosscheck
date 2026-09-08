from __future__ import annotations

import re

from .models import Fact

IGNORED_TERMS = {
    "about",
    "across",
    "against",
    "and",
    "are",
    "as",
    "at",
    "by",
    "claim",
    "document",
    "during",
    "ended",
    "fact",
    "for",
    "first",
    "from",
    "has",
    "have",
    "in",
    "is",
    "of",
    "our",
    "report",
    "reported",
    "reports",
    "show",
    "shows",
    "state",
    "stated",
    "states",
    "the",
    "this",
    "to",
    "value",
    "was",
    "were",
    "with",
    "year",
}
NON_ENTITY_INITIALS = {
    "adjusted",
    "average",
    "consumer",
    "external",
    "fiscal",
    "gross",
    "headline",
    "income",
    "net",
    "operating",
    "profit",
    "revenue",
    "service",
    "total",
}


def metric_terms(text: str) -> list[str]:
    """Return comparison terms while excluding reporting-language boilerplate."""
    return [
        word
        for word in re.findall(r"[a-z]{3,}", text.lower())
        if word not in IGNORED_TERMS
    ]


def metric_key(subject: str, predicate: str) -> str:
    """Create a stable, inspectable metric identity from extracted language."""
    terms = list(dict.fromkeys(metric_terms(f"{subject} {predicate}")))
    return " ".join(terms[:12])


def fact_metric_key(fact: Fact) -> str:
    stored_key = fact.attributes.get("metric_key") if fact.attributes else None
    if isinstance(stored_key, str) and stored_key.strip():
        return stored_key.strip().lower()
    return metric_key(fact.subject, fact.predicate)


def _entity_hint(fact: Fact) -> str | None:
    """Use a leading proper name as a conservative entity guard when available."""
    match = re.match(r"\s*([A-Z][a-z]{2,})\b", fact.subject)
    if not match:
        return None
    candidate = match.group(1).lower()
    return None if candidate in NON_ENTITY_INITIALS else candidate


def shares_metric_identity(left: Fact, right: Fact) -> bool:
    """Require a deliberate metric match before comparing two numeric values."""
    left_key = fact_metric_key(left)
    right_key = fact_metric_key(right)
    if left_key and left_key == right_key:
        return True

    left_terms = set(metric_terms(f"{left.subject} {left.predicate}"))
    right_terms = set(metric_terms(f"{right.subject} {right.predicate}"))
    if len(left_terms & right_terms) < 2:
        return False

    left_entity = _entity_hint(left)
    right_entity = _entity_hint(right)
    return not (left_entity and right_entity and left_entity != right_entity)
