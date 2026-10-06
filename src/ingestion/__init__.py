"""Ingestion package: normalizers, parsers, and chunkers."""

from src.ingestion.chunking import ChildChunk, ChunkingResult, ParentChildChunker, ParentChunk, SentenceSemanticChunker
from src.ingestion.normalizers import (
    clean_text,
    detect_language_simple,
    estimate_tokens,
    normalize_arabic_letters,
    normalize_for_lexical,
    remove_arabic_diacritics,
    strip_null_bytes,
)
from src.ingestion.parsers import (
    BaseDocumentParser,
    DocxParser,
    MarkdownParser,
    ParsedDocument,
    ParsedPage,
    ParsedSection,
    ParserFactory,
    PDFParser,
    TxtParser,
)

__all__ = [
    # Normalizers
    "clean_text",
    "strip_null_bytes",
    "remove_arabic_diacritics",
    "normalize_arabic_letters",
    "normalize_for_lexical",
    "detect_language_simple",
    "estimate_tokens",
    # Parsers
    "BaseDocumentParser",
    "ParsedDocument",
    "ParsedPage",
    "ParsedSection",
    "PDFParser",
    "DocxParser",
    "MarkdownParser",
    "TxtParser",
    "ParserFactory",
    # Chunkers
    "ParentChunk",
    "ChildChunk",
    "ChunkingResult",
    "ParentChildChunker",
    "SentenceSemanticChunker",
]
