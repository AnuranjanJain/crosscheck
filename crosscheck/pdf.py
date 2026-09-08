from __future__ import annotations

import hashlib
from collections.abc import Callable
from io import BytesIO
import re
from pathlib import Path
from uuid import uuid4

import pdfplumber

from .models import Document, Evidence, ExtractedTable, ProcessingIssue

PAGE_LABEL = re.compile(r"^(?:page\s*)?(\d{1,4}|[ivxlcdm]{1,8})$", re.I)
REPORT_FOOTER = re.compile(
    r"\b(?:annual report|economic survey|prospectus)\b.*?\b(\d{1,4}|[ivxlcdm]{1,8})$",
    re.I,
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def detect_printed_page_label(text: str) -> str | None:
    """Best-effort footer detection; PDF indexes remain the authoritative page location."""
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    for line in reversed(lines[-10:]):
        direct = PAGE_LABEL.fullmatch(line)
        if direct:
            return direct.group(1)
        footer = REPORT_FOOTER.search(line)
        if footer:
            return footer.group(1)
    return None


def extract_document(path: str | Path, data: bytes, on_progress: Callable[[str], None] | None = None) -> tuple[Document, list[Evidence], list[ProcessingIssue]]:
    document_id = uuid4().hex
    evidence: list[Evidence] = []
    issues: list[ProcessingIssue] = []
    warnings: list[str] = []
    try:
        with pdfplumber.open(path) as pdf:
            page_count = len(pdf.pages)
            for page_index, page in enumerate(pdf.pages):
                if on_progress:
                    on_progress(f"Reading PDF page {page_index + 1}/{page_count}")
                text = (page.extract_text(x_tolerance=2, y_tolerance=3) or "").strip()
                if not text:
                    warnings.append(f"Page {page_index + 1} has no extractable text; OCR is not enabled.")
                    issues.append(ProcessingIssue(id=uuid4().hex, document_id=document_id, page_index=page_index, code="empty_page", message="No text extracted from page", recoverable=True))
                    continue
                heading = next((line.strip() for line in text.splitlines() if 3 < len(line.strip()) < 120 and not re.search(r"\d", line)), None)
                tables: list[ExtractedTable] = []
                try:
                    for table in page.find_tables()[:10]:
                        rows = table.extract()
                        if rows:
                            tables.append(ExtractedTable(bbox=tuple(table.bbox), rows=rows))
                except Exception as exc:  # noqa: BLE001 - retain page text when table recovery fails
                    issues.append(
                        ProcessingIssue(
                            id=uuid4().hex,
                            document_id=document_id,
                            page_index=page_index,
                            code="table_extraction_error",
                            message=f"Could not recover a table on this page: {exc}",
                            recoverable=True,
                        )
                    )
                evidence.append(
                    Evidence(
                        id=uuid4().hex,
                        document_id=document_id,
                        page_index=page_index,
                        printed_page=detect_printed_page_label(text),
                        text=text,
                        heading=heading,
                        tables=tables,
                    )
                )
    except Exception as exc:
        issues.append(ProcessingIssue(id=uuid4().hex, document_id=document_id, code="pdf_error", message=f"Could not read PDF: {exc}", recoverable=False))
        page_count = 0
    document = Document(id=document_id, filename=Path(path).name, sha256=sha256_bytes(data), page_count=page_count, status="ready" if not any(not issue.recoverable for issue in issues) else "failed", warnings=warnings)
    return document, evidence, issues


def render_page(path: str | Path, page_index: int, scale: float = 1.5) -> bytes:
    """Render one source page to PNG for evidence inspection."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        page = pdf[page_index]
        try:
            image = page.render(scale=scale).to_pil()
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue()
        finally:
            page.close()
    finally:
        pdf.close()
