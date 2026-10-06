"""Document parser factory and router.

Maps file extensions and MIME types to appropriate concrete parsers.
"""

from pathlib import Path
from typing import Any, Dict, Optional
from src.core.exceptions import DocumentParsingError
from src.ingestion.parsers.base import BaseDocumentParser, ParsedDocument
from src.ingestion.parsers.docx_parser import DocxParser
from src.ingestion.parsers.markdown_parser import MarkdownParser
from src.ingestion.parsers.pdf_parser import PDFParser
from src.ingestion.parsers.txt_parser import TxtParser


class ParserFactory:
    """Factory and registry for format-specific document parsers."""

    _EXTENSION_MAP = {
        ".pdf": PDFParser,
        ".docx": DocxParser,
        ".md": MarkdownParser,
        ".markdown": MarkdownParser,
        ".txt": TxtParser,
    }

    _MIME_MAP = {
        "application/pdf": PDFParser,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DocxParser,
        "text/markdown": MarkdownParser,
        "text/plain": TxtParser,
    }

    def __init__(self):
        self._instances: Dict[type, BaseDocumentParser] = {}

    def get_parser_for_path(self, file_path: str | Path) -> BaseDocumentParser:
        """Resolves parser instance based on file suffix/extension."""
        path = Path(file_path)
        ext = path.suffix.lower()

        parser_cls = self._EXTENSION_MAP.get(ext)
        if not parser_cls:
            supported = ", ".join(self._EXTENSION_MAP.keys())
            raise DocumentParsingError(
                f"Unsupported file format '{ext}' for file: {path.name}. Supported formats: {supported}",
                details={"file": str(path), "extension": ext},
            )

        if parser_cls not in self._instances:
            self._instances[parser_cls] = parser_cls()
        return self._instances[parser_cls]

    def get_parser_for_mime(self, mime_type: str) -> BaseDocumentParser:
        """Resolves parser instance based on MIME type."""
        clean_mime = mime_type.split(";")[0].strip().lower()
        parser_cls = self._MIME_MAP.get(clean_mime)
        if not parser_cls:
            supported = ", ".join(self._MIME_MAP.keys())
            raise DocumentParsingError(
                f"Unsupported MIME type '{clean_mime}'. Supported MIME types: {supported}",
                details={"mime_type": clean_mime},
            )

        if parser_cls not in self._instances:
            self._instances[parser_cls] = parser_cls()
        return self._instances[parser_cls]

    async def parse_file(
        self,
        file_path: str | Path,
        metadata: Optional[Dict[str, Any]] = None,
        mime_type: Optional[str] = None,
    ) -> ParsedDocument:
        """Parses a document file by routing to the appropriate parser."""
        if mime_type and mime_type.split(";")[0].strip().lower() in self._MIME_MAP:
            parser = self.get_parser_for_mime(mime_type)
        else:
            parser = self.get_parser_for_path(file_path)

        return await parser.parse(file_path, metadata=metadata)
