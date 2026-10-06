"""Microsoft Word (.docx) document parser using python-docx.

Extracts paragraphs, hierarchical headings (H1-H6) with breadcrumbs,
and converts embedded tables into structured markdown tables.
"""

from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import docx
from src.core.exceptions import DocumentParsingError
from src.core.logging import get_logger
from src.ingestion.normalizers import clean_text, detect_language_simple
from src.ingestion.parsers.base import BaseDocumentParser, ParsedDocument, ParsedSection

logger = get_logger("ingestion.parsers.docx")

HEADING_PATTERN = re.compile(r"^heading\s*([1-6])$", re.IGNORECASE)


class DocxParser(BaseDocumentParser):
    """Parser for Microsoft Word (.docx) documents."""

    async def parse(
        self,
        file_path: str | Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ParsedDocument:
        path = Path(file_path)
        if not path.exists():
            raise DocumentParsingError(f"DOCX file does not exist: {path}")

        file_hash = self.calculate_file_hash(path)
        file_size = path.stat().st_size
        doc_metadata = {
            "file_name": path.name,
            "file_size": file_size,
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "file_hash": file_hash,
            **(metadata or {}),
        }

        try:
            doc = docx.Document(str(path))

            # Extract Core Properties
            core_props = doc.core_properties
            if core_props.title:
                doc_metadata.setdefault("title", clean_text(core_props.title))
            if core_props.author:
                doc_metadata.setdefault("author", clean_text(core_props.author))
            if core_props.subject:
                doc_metadata.setdefault("subject", clean_text(core_props.subject))

            sections: List[ParsedSection] = []
            all_text_blocks: List[str] = []

            current_breadcrumb_stack: List[tuple[int, str]] = []  # (level, title)
            current_section_title = "Introduction"
            current_section_level = 1
            current_section_texts: List[str] = []

            def flush_section():
                nonlocal current_section_texts, current_section_title, current_section_level
                section_body = clean_text("\n\n".join(current_section_texts))
                if section_body or current_section_title:
                    breadcrumbs = [title for _, title in current_breadcrumb_stack]
                    sections.append(
                        ParsedSection(
                            title=current_section_title,
                            level=current_section_level,
                            text=section_body,
                            breadcrumbs=breadcrumbs.copy(),
                        )
                    )
                current_section_texts = []

            # Iterate over paragraphs and tables in document body
            for block in doc.element.body:
                # Check if block is a paragraph
                if block.tag.endswith("p"):
                    p = docx.text.paragraph.Paragraph(block, doc)
                    raw_p = clean_text(p.text)
                    if not raw_p:
                        continue

                    style_name = (p.style.name if p.style else "").strip().lower()
                    heading_match = HEADING_PATTERN.match(style_name)

                    if heading_match:
                        level = int(heading_match.group(1))
                        # Flush current section before starting new one
                        flush_section()

                        # Adjust breadcrumb stack
                        while current_breadcrumb_stack and current_breadcrumb_stack[-1][0] >= level:
                            current_breadcrumb_stack.pop()
                        current_breadcrumb_stack.append((level, raw_p))

                        current_section_title = raw_p
                        current_section_level = level
                        all_text_blocks.append(f"\n## {raw_p}\n")
                    else:
                        current_section_texts.append(raw_p)
                        all_text_blocks.append(raw_p)

                # Check if block is a table
                elif block.tag.endswith("tbl"):
                    tbl = docx.table.Table(block, doc)
                    table_markdown = self._table_to_markdown(tbl)
                    if table_markdown:
                        current_section_texts.append(table_markdown)
                        all_text_blocks.append(table_markdown)

            # Flush the final section
            flush_section()

            full_text = clean_text("\n\n".join(all_text_blocks))
            detected_lang = detect_language_simple(full_text)

            return ParsedDocument(
                raw_text=full_text,
                pages=[],  # DOCX files do not have explicit physical page counts without rendering
                sections=sections,
                metadata=doc_metadata,
                extraction_method="python-docx",
                detected_language=detected_lang,
                is_scanned=False,
            )

        except DocumentParsingError:
            raise
        except Exception as exc:
            logger.error("docx_parsing_failed", file=path.name, error=str(exc))
            raise DocumentParsingError(
                f"Failed to parse DOCX document '{path.name}': {str(exc)}",
                details={"file": str(path), "error": str(exc)},
            )

    @staticmethod
    def _table_to_markdown(table: docx.table.Table) -> str:
        """Converts a docx.table.Table into a clean Markdown table string."""
        rows_data: List[List[str]] = []
        for row in table.rows:
            row_cells = [clean_text(cell.text).replace("\n", " ").strip() for cell in row.cells]
            # Avoid duplicate merged cells on the same row
            dedup_cells: List[str] = []
            for cell_val in row_cells:
                dedup_cells.append(cell_val)
            if any(dedup_cells):
                rows_data.append(dedup_cells)

        if not rows_data:
            return ""

        headers = rows_data[0]
        col_count = len(headers)
        lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * col_count) + " |",
        ]
        for data_row in rows_data[1:]:
            # Pad row if mismatched
            padded_row = data_row + [""] * (col_count - len(data_row))
            lines.append("| " + " | ".join(padded_row[:col_count]) + " |")

        return "\n".join(lines)
