"""PDF document parser using pypdf.

Extracts text preserving page boundaries, extracts PDF metadata,
and detects scanned/image-only PDFs.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import pypdf
from src.core.exceptions import DocumentParsingError
from src.core.logging import get_logger
from src.ingestion.normalizers import clean_text, detect_language_simple
from src.ingestion.parsers.base import BaseDocumentParser, ParsedDocument, ParsedPage

logger = get_logger("ingestion.parsers.pdf")


class PDFParser(BaseDocumentParser):
    """Parser for Adobe PDF documents."""

    def __init__(self, min_chars_per_page: int = 50):
        self.min_chars_per_page = min_chars_per_page

    async def parse(
        self,
        file_path: str | Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ParsedDocument:
        path = Path(file_path)
        if not path.exists():
            raise DocumentParsingError(f"PDF file does not exist: {path}")

        file_hash = self.calculate_file_hash(path)
        file_size = path.stat().st_size
        doc_metadata = {
            "file_name": path.name,
            "file_size": file_size,
            "mime_type": "application/pdf",
            "file_hash": file_hash,
            **(metadata or {}),
        }

        pages: List[ParsedPage] = []
        raw_text_parts: List[str] = []
        is_scanned = False
        warning_messages: List[str] = []

        try:
            reader = pypdf.PdfReader(str(path))
            if reader.is_encrypted:
                try:
                    reader.decrypt("")
                except Exception as dec_err:
                    raise DocumentParsingError(
                        f"Cannot decrypt protected PDF: {path.name}",
                        details={"error": str(dec_err)},
                    )

            # Extract embedded metadata if available
            pdf_info = reader.metadata or {}
            if pdf_info.title:
                doc_metadata.setdefault("title", clean_text(str(pdf_info.title)))
            if pdf_info.author:
                doc_metadata.setdefault("author", clean_text(str(pdf_info.author)))
            if pdf_info.subject:
                doc_metadata.setdefault("subject", clean_text(str(pdf_info.subject)))

            total_pages = len(reader.pages)
            doc_metadata["total_pages"] = total_pages

            total_extracted_chars = 0

            for idx, page in enumerate(reader.pages, start=1):
                try:
                    page_text = page.extract_text() or ""
                except Exception as p_err:
                    logger.warning(
                        "pdf_page_extraction_error",
                        page=idx,
                        file=path.name,
                        error=str(p_err),
                    )
                    page_text = ""

                cleaned_page_text = clean_text(page_text)
                char_count = len(cleaned_page_text)
                total_extracted_chars += char_count

                pages.append(
                    ParsedPage(
                        page_number=idx,
                        text=cleaned_page_text,
                        char_count=char_count,
                        metadata={"page_index": idx - 1},
                    )
                )

                if cleaned_page_text:
                    raw_text_parts.append(cleaned_page_text)

            # Scanned / Image-only detection heuristic
            if total_pages > 0:
                avg_chars_per_page = total_extracted_chars / total_pages
                if avg_chars_per_page < self.min_chars_per_page:
                    is_scanned = True
                    msg = (
                        f"PDF appears scanned or image-only: average characters per page is "
                        f"{avg_chars_per_page:.1f} (threshold: {self.min_chars_per_page})"
                    )
                    warning_messages.append(msg)
                    logger.warning("scanned_pdf_detected", file=path.name, avg_chars=avg_chars_per_page)

            combined_raw_text = "\n\n".join(raw_text_parts)
            detected_lang = detect_language_simple(combined_raw_text)

            return ParsedDocument(
                raw_text=combined_raw_text,
                pages=pages,
                sections=[],  # Flat pages for PDF unless outline/bookmarks parsed
                metadata=doc_metadata,
                extraction_method="pypdf",
                detected_language=detected_lang,
                is_scanned=is_scanned,
                has_warnings=bool(warning_messages),
                warning_messages=warning_messages,
            )

        except DocumentParsingError:
            raise
        except Exception as exc:
            logger.error("pdf_parsing_failed", file=path.name, error=str(exc))
            raise DocumentParsingError(
                f"Failed to parse PDF document '{path.name}': {str(exc)}",
                details={"file": str(path), "error": str(exc)},
            )
