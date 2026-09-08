from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RelationshipKind(StrEnum):
    CORROBORATION = "corroboration"
    LIKELY_CONTRADICTION = "likely_contradiction"
    CONTEXTUAL_RECONCILIATION = "contextual_reconciliation"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    filename: str
    sha256: str
    page_count: int = Field(ge=0)
    status: str = "queued"
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    document_id: str
    page_index: int = Field(ge=0)
    printed_page: str | None = None
    text: str
    heading: str | None = None
    bbox: tuple[float, float, float, float] | None = None


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    document_id: str
    evidence_id: str
    subject: str
    predicate: str
    original_text: str
    value_text: str | None = None
    value_number: float | None = None
    unit: str | None = None
    period: str | None = None
    scope: str | None = None
    status: str = "grounded"
    attributes: dict[str, Any] = Field(default_factory=dict)


class Relationship(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    left_fact_id: str
    right_fact_id: str
    kind: RelationshipKind
    confidence: float = Field(ge=0, le=1)
    explanation: str
    created_at: datetime = Field(default_factory=utc_now)


class ProcessingIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    document_id: str
    page_index: int | None = None
    code: str
    message: str
    recoverable: bool = True
    created_at: datetime = Field(default_factory=utc_now)
