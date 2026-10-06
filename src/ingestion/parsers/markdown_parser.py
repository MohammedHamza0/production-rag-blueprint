"""Markdown (.md, .markdown) parser using markdown-it-py and structural scanning.

Preserves heading hierarchy (H1-H6), constructs breadcrumbs, extracts frontmatter,
and maintains code fences and lists intact.
"""

from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import markdown_it
from src.core.exceptions import DocumentParsingError
from src.core.logging import get_logger
from src.ingestion.normalizers import clean_text, detect_language_simple
from src.ingestion.parsers.base import BaseDocumentParser, ParsedDocument, ParsedSection

logger = get_logger("ingestion.parsers.markdown")

FRONTMATTER_REGEX = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
HEADING_REGEX = re.compile(r"^(#{1,6})\s+(.+)$")


class MarkdownParser(BaseDocumentParser):
    """Parser for Markdown documents with structural heading hierarchy."""

    def __init__(self):
        self.md_it = markdown_it.MarkdownIt()

    async def parse(
        self,
        file_path: str | Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ParsedDocument:
        path = Path(file_path)
        if not path.exists():
            raise DocumentParsingError(f"Markdown file does not exist: {path}")

        file_hash = self.calculate_file_hash(path)
        file_size = path.stat().st_size
        doc_metadata = {
            "file_name": path.name,
            "file_size": file_size,
            "mime_type": "text/markdown",
            "file_hash": file_hash,
            **(metadata or {}),
        }

        try:
            raw_content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as read_err:
            raise DocumentParsingError(
                f"Failed to read markdown file '{path.name}': {str(read_err)}",
                details={"file": str(path), "error": str(read_err)},
            )

        # 1. Extract YAML frontmatter if present
        frontmatter_data = self._extract_frontmatter(raw_content)
        if frontmatter_data:
            doc_metadata.update(frontmatter_data)
            # Remove frontmatter from content for parsing
            content_without_fm = FRONTMATTER_REGEX.sub("", raw_content, count=1)
        else:
            content_without_fm = raw_content

        cleaned_full_text = clean_text(content_without_fm)
        detected_lang = detect_language_simple(cleaned_full_text)

        # 2. Parse structural sections using heading hierarchy
        sections = self._extract_sections_from_markdown(cleaned_full_text)

        # Infer title from H1 or frontmatter if not present
        if "title" not in doc_metadata:
            for s in sections:
                if s.level == 1:
                    doc_metadata["title"] = s.title
                    break
            if "title" not in doc_metadata:
                doc_metadata["title"] = path.stem.replace("_", " ").title()

        return ParsedDocument(
            raw_text=cleaned_full_text,
            pages=[],
            sections=sections,
            metadata=doc_metadata,
            extraction_method="markdown-it",
            detected_language=detected_lang,
            is_scanned=False,
        )

    @staticmethod
    def _extract_frontmatter(content: str) -> Dict[str, Any]:
        """Simple YAML frontmatter key-value extractor without external yaml dependency."""
        match = FRONTMATTER_REGEX.match(content)
        if not match:
            return {}

        fm_text = match.group(1)
        metadata: Dict[str, Any] = {}
        for line in fm_text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, val = line.split(":", 1)
                clean_k = key.strip()
                clean_v = val.strip().strip("'\"")
                if clean_k:
                    metadata[clean_k] = clean_v
        return metadata

    @staticmethod
    def _extract_sections_from_markdown(text: str) -> List[ParsedSection]:
        """Splits markdown into sections by headings while tracking breadcrumbs."""
        lines = text.splitlines()
        sections: List[ParsedSection] = []

        breadcrumb_stack: List[Tuple[int, str]] = []  # (level, title)
        current_title = "Document Overview"
        current_level = 1
        current_lines: List[str] = []
        in_code_block = False

        def flush():
            nonlocal current_lines, current_title, current_level
            body = clean_text("\n".join(current_lines))
            # Don't flush empty initial overview if document starts directly with a heading
            if body or (current_title != "Document Overview" and current_lines):
                crumbs = [t for _, t in breadcrumb_stack]
                sections.append(
                    ParsedSection(
                        title=current_title,
                        level=current_level,
                        text=body,
                        breadcrumbs=crumbs.copy(),
                    )
                )
            current_lines = []

        for line in lines:
            # Check for code fence toggling to avoid mistaking comments/code for headings
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                current_lines.append(line)
                continue

            if in_code_block:
                current_lines.append(line)
                continue

            heading_match = HEADING_REGEX.match(line)
            if heading_match:
                flush()
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()

                # Adjust breadcrumbs hierarchy
                while breadcrumb_stack and breadcrumb_stack[-1][0] >= level:
                    breadcrumb_stack.pop()
                breadcrumb_stack.append((level, title))

                current_title = title
                current_level = level
            else:
                current_lines.append(line)

        flush()
        return sections
