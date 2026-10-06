"""Base interfaces and data structures for document parsing."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional
from src.ingestion.normalizers import clean_text, detect_language_simple


@dataclass
class ParsedPage:
    """Represents an extracted physical page from a document (PDF, pagination)."""

    page_number: int  # 1-indexed
    text: str
    char_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.char_count:
            self.char_count = len(self.text)


@dataclass
class ParsedSection:
    """Represents a logical section within a document hierarchy."""

    title: str
    level: int  # 1 = H1, 2 = H2, etc.
    text: str
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    breadcrumbs: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """Canonical representation of a parsed document regardless of source format."""

    raw_text: str
    pages: List[ParsedPage] = field(default_factory=list)
    sections: List[ParsedSection] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    extraction_method: str = "native"
    detected_language: str = "en"
    is_scanned: bool = False
    has_warnings: bool = False
    warning_messages: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.detected_language and self.raw_text:
            self.detected_language = detect_language_simple(self.raw_text)

    @property
    def total_pages(self) -> int:
        return len(self.pages) or 1

    def to_dict(self) -> Dict[str, Any]:
        """Serializes parsed document representation to dictionary."""
        return {
            "metadata": self.metadata,
            "extraction_method": self.extraction_method,
            "detected_language": self.detected_language,
            "is_scanned": self.is_scanned,
            "total_pages": len(self.pages),
            "total_sections": len(self.sections),
            "total_characters": len(self.raw_text),
            "has_warnings": self.has_warnings,
            "warning_messages": self.warning_messages,
        }


class BaseDocumentParser(ABC):
    """Abstract base class for format-specific document parsers."""

    @abstractmethod
    async def parse(
        self,
        file_path: str | Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ParsedDocument:
        """Parses a document file and returns a structured ParsedDocument."""
        pass

    @staticmethod
    def calculate_file_hash(file_path: str | Path) -> str:
        """Calculates a streaming SHA-256 checksum of the target file."""
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        return sha.hexdigest()
