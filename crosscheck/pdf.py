from __future__ import annotations

import hashlib
from io import BytesIO
import re
from pathlib import Path
from uuid import uuid4

import pdfplumber

from .models import Document, Evidence, ProcessingIssue


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_document(path: str | Path, data: bytes) -> tuple[Document, list[Evidence], list[ProcessingIssue]]:
    document_id = uuid4().hex
    evidence: list[Evidence] = []
    issues: list[ProcessingIssue] = []
    warnings: list[str] = []
    try:
        with pdfplumber.open(path) as pdf:
            page_count = len(pdf.pages)
            for page_index, page in enumerate(pdf.pages):
                text = (page.extract_text(x_tolerance=2, y_tolerance=3) or "").strip()
                if not text:
                    warnings.append(f"Page {page_index + 1} has no extractable text; OCR is not enabled.")
                    issues.append(ProcessingIssue(id=uuid4().hex, document_id=document_id, page_index=page_index, code="empty_page", message="No text extracted from page", recoverable=True))
                    continue
                heading = next((line.strip() for line in text.splitlines() if 3 < len(line.strip()) < 120 and not re.search(r"\d", line)), None)
                evidence.append(Evidence(id=uuid4().hex, document_id=document_id, page_index=page_index, text=text, heading=heading))
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
