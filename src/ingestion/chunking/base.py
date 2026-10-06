"""Chunking data structures and base contracts for hierarchical Parent-Child indexing."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ParentChunk:
    """Parent contextual chunk (~800-1200 tokens).

    Serves as the high-fidelity context passed to the LLM during generation
    when one of its child chunks is retrieved.
    """

    parent_index: int
    title: str
    content: str
    token_count: int
    breadcrumbs: List[str] = field(default_factory=list)
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parent_index": self.parent_index,
            "title": self.title,
            "content": self.content,
            "token_count": self.token_count,
            "breadcrumbs": self.breadcrumbs,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "metadata": self.metadata,
        }


@dataclass
class ChildChunk:
    """Child retrieval chunk (~250-300 tokens, 50-token overlap).

    Embedded and indexed in pgvector (HNSW) and tsvector (GIN).
    Includes injected contextual header for semantic anchoring.
    """

    child_index: int
    parent_index: int
    content: str  # Clean body text
    content_with_header: str  # Contextual header + body text for embedding/search
    header: str
    token_count: int
    breadcrumbs: List[str] = field(default_factory=list)
    page_number: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "child_index": self.child_index,
            "parent_index": self.parent_index,
            "content": self.content,
            "content_with_header": self.content_with_header,
            "header": self.header,
            "token_count": self.token_count,
            "breadcrumbs": self.breadcrumbs,
            "page_number": self.page_number,
            "metadata": self.metadata,
        }


@dataclass
class ChunkingResult:
    """Complete collection of parent and child chunks resulting from document chunking."""

    parents: List[ParentChunk]
    children: List[ChildChunk]
    total_parents: int = 0
    total_children: int = 0
    avg_child_tokens: float = 0.0

    def __post_init__(self):
        self.total_parents = len(self.parents)
        self.total_children = len(self.children)
        if self.children:
            self.avg_child_tokens = sum(c.token_count for c in self.children) / len(self.children)
        else:
            self.avg_child_tokens = 0.0
