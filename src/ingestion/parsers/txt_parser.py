"""Plain text (.txt) document parser with multi-encoding fallback and paragraph structuring."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from src.core.exceptions import DocumentParsingError
from src.core.logging import get_logger
from src.ingestion.normalizers import clean_text, detect_language_simple
from src.ingestion.parsers.base import BaseDocumentParser, ParsedDocument, ParsedSection

logger = get_logger("ingestion.parsers.txt")

COMMON_ENCODINGS = ["utf-8", "utf-8-sig", "windows-1256", "cp1252", "latin-1"]


class TxtParser(BaseDocumentParser):
    """Parser for plain text files with encoding resilience."""

    async def parse(
        self,
        file_path: str | Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ParsedDocument:
        path = Path(file_path)
        if not path.exists():
            raise DocumentParsingError(f"Text file does not exist: {path}")

        file_hash = self.calculate_file_hash(path)
        file_size = path.stat().st_size
        doc_metadata = {
            "file_name": path.name,
            "file_size": file_size,
            "mime_type": "text/plain",
            "file_hash": file_hash,
            **(metadata or {}),
        }

        raw_bytes = path.read_bytes()
        text_content: Optional[str] = None
        used_encoding = "utf-8"

        for enc in COMMON_ENCODINGS:
            try:
                text_content = raw_bytes.decode(enc)
                used_encoding = enc
                break
            except (UnicodeDecodeError, LookupError):
                continue

        if text_content is None:
            text_content = raw_bytes.decode("utf-8", errors="replace")
            used_encoding = "utf-8-lossy"

        doc_metadata["encoding"] = used_encoding
        cleaned_text = clean_text(text_content)
        detected_lang = detect_language_simple(cleaned_text)

        # Build natural paragraph-based sections
        paragraphs = [p.strip() for p in cleaned_text.split("\n\n") if p.strip()]
        sections: List[ParsedSection] = []

        if paragraphs:
            # Group into meaningful sections (~3 paragraphs per section or by size)
            current_section_paragraphs: List[str] = []
            section_idx = 1

            for p in paragraphs:
                current_section_paragraphs.append(p)
                if len(current_section_paragraphs) >= 4:
                    sec_body = "\n\n".join(current_section_paragraphs)
                    sections.append(
                        ParsedSection(
                            title=f"Section {section_idx}",
                            level=1,
                            text=sec_body,
                            breadcrumbs=[f"Section {section_idx}"],
                        )
                    )
                    section_idx += 1
                    current_section_paragraphs = []

            if current_section_paragraphs:
                sec_body = "\n\n".join(current_section_paragraphs)
                sections.append(
                    ParsedSection(
                        title=f"Section {section_idx}",
                        level=1,
                        text=sec_body,
                        breadcrumbs=[f"Section {section_idx}"],
                    )
                )
        else:
            sections.append(
                ParsedSection(
                    title="Content",
                    level=1,
                    text="",
                    breadcrumbs=["Content"],
                )
            )

        if "title" not in doc_metadata:
            doc_metadata["title"] = path.stem.replace("_", " ").title()

        return ParsedDocument(
            raw_text=cleaned_text,
            pages=[],
            sections=sections,
            metadata=doc_metadata,
            extraction_method="plain-text",
            detected_language=detected_lang,
            is_scanned=False,
        )
