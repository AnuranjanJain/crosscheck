"""Conservative extraction for date-indexed, explicitly attributed tables."""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from .models import Evidence, Fact
from .identity import metric_key

PERIOD_HEADER = re.compile(r"(?:Q[1-4]\s+)?FY\d{2,4}|March\s+31,?\s+20\d{2}|20\d{2}[-/]\d{2,4}", re.I)
CELL_NUMBER = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?\)?")


def period_table_facts(evidence: Evidence) -> list[Fact]:
    facts: list[Fact] = []
    seen = set()
    for table_index, table in enumerate(evidence.tables):
        header_index = next((i for i, row in enumerate(table.rows[:4])
                             if sum(bool(PERIOD_HEADER.fullmatch((cell or "").strip())) for cell in row) >= 2), None)
        if header_index is None:
            continue
        headers = table.rows[header_index]
        periods = [(index, (cell or "").strip()) for index, cell in enumerate(headers)
                   if PERIOD_HEADER.fullmatch((cell or "").strip())]
        unit_match = re.search(r"[₹$€£]\s*(?:in\s+)?(million|crore|cr|billion)\b", evidence.text, re.I)
        if not unit_match:
            continue
        unit_text = unit_match[1].lower()
        scale = Decimal(10) if unit_text in {"crore", "cr"} else Decimal(1000) if unit_text == "billion" else Decimal(1)
        rows = table.rows[header_index + 1:]
        if not rows:
            # Some PDFs expose only the ruled header; accept strictly aligned text rows.
            rows = []
            for line in evidence.text.splitlines():
                match = re.fullmatch(r"([A-Za-z][A-Za-z /()'-]+?)\s+((?:\(?-?\d[\d,]*(?:\.\d+)?\)?\s*)+)", line)
                if match:
                    cells = CELL_NUMBER.findall(match[2])
                    if len(cells) == len(headers) - 1:
                        rows.append([match[1]] + cells)
        for row in rows:
            subject = " ".join((row[0] or "").split())
            if not subject:
                continue
            for column, period in periods:
                if column >= len(row):
                    continue
                raw = (row[column] or "").strip()
                if not CELL_NUMBER.fullmatch(raw) or raw not in evidence.text:
                    continue
                if period.lower().startswith("march"):
                    period = "FY" + period[-4:]
                value = Decimal(raw.strip("()").replace(",", "")) * (-1 if raw.startswith("(") else 1) * scale
                key = (subject, period, raw)
                if key in seen:
                    continue
                seen.add(key)
                decimals = len(raw.strip("()").partition(".")[2])
                facts.append(Fact(id=uuid4().hex, document_id=evidence.document_id, evidence_id=evidence.id,
                                  subject=subject, predicate=subject.lower(), original_text=raw, value_text=raw,
                                  value_number=float(value), unit="million", period=period,
                                  attributes={"extractor": "period_table", "metric_key": metric_key(subject, subject),
                                              "table_index": table_index, "column_header": headers[column],
                                              "currency": unit_match[0][0],
                                              "source_precision_increment": float(Decimal(1).scaleb(-decimals) * scale)}))
    return facts


def attributed_table_facts(evidence: Evidence) -> list[Fact]:
    facts = []
    for table_index, table in enumerate(evidence.tables):
        if not table.rows:
            continue
        headers = [" ".join((cell or "").split()) for cell in table.rows[0]]
        columns = []
        for index, header in enumerate(headers[1:], 1):
            split = re.split(r"\bper(?=[A-Z\s(])", header, maxsplit=1, flags=re.I)
            if len(split) == 2:
                metric = set(re.findall(r"[a-z]{3,}", split[0].lower()))
                columns.append((index, header, metric))
        if len(columns) < 2:
            continue
        minimum = min(len(metric) for _, _, metric in columns)
        # Only the shortest metric and its entity-qualified variant are comparable.
        base = next(metric for _, _, metric in columns if len(metric) == minimum)
        comparable = [(index, header) for index, header, metric in columns
                      if base <= metric and len(metric - base) <= 1]
        if len(comparable) < 2:
            continue
        for row_index, row in enumerate(table.rows[1:], 1):
            raw_date = (row[0] or "").strip()
            try:
                period = datetime.strptime(raw_date, "%m/%d/%y").date().isoformat()
            except ValueError:
                continue
            for column, header in comparable:
                if column >= len(row):
                    continue
                raw = (row[column] or "").strip()
                match = re.fullmatch(r"([$€£₹])([\d,]+(?:\.\d+)?)", raw)
                if not match or raw not in evidence.text:
                    continue
                group = f"{evidence.id}:{table_index}:{row_index}"
                facts.append(Fact(id=uuid4().hex, document_id=evidence.document_id,
                                  evidence_id=evidence.id, subject=" ".join(sorted(base)),
                                  predicate="reported " + " ".join(sorted(base)), original_text=raw,
                                  value_text=raw, value_number=float(Decimal(match[2].replace(",", ""))),
                                  unit=match[1], period=period, scope="same table row",
                                  attributes={"extractor": "attributed_table", "attribution": header,
                                              "table_group": group, "table_index": table_index,
                                              "row_index": row_index, "column_index": column,
                                              "metric_key": group, "source_precision_increment": 1,
                                              "estimate_status": "reported assertion"}))
    return facts
