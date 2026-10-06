"""Hierarchical Parent-Child chunker with contextual header injection.

Produces PARENT sections (~1000 tokens) for LLM context generation and
CHILD chunks (~280 tokens, 50-token overlap) for vector and lexical retrieval.
"""

from typing import Any, Dict, List, Optional, Tuple
from src.core.logging import get_logger
from src.ingestion.chunking.base import ChildChunk, ChunkingResult, ParentChunk
from src.ingestion.chunking.semantic_chunker import SentenceSemanticChunker
from src.ingestion.normalizers import clean_text, estimate_tokens
from src.ingestion.parsers.base import ParsedDocument, ParsedSection

logger = get_logger("ingestion.chunking.hierarchical")


class ParentChildChunker:
    """Implements parent-child chunking with structural boundary awareness and header injection."""

    def __init__(
        self,
        parent_target_tokens: int = 1000,
        child_target_tokens: int = 280,
        child_overlap_tokens: int = 50,
        default_lang: str = "ar",
    ):
        self.parent_target_tokens = parent_target_tokens
        self.child_target_tokens = child_target_tokens
        self.child_overlap_tokens = child_overlap_tokens
        self.default_lang = default_lang
        self.sentence_splitter = SentenceSemanticChunker(lang=default_lang)

    def chunk_parsed_document(
        self,
        doc: ParsedDocument,
        parent_target_tokens: Optional[int] = None,
        child_target_tokens: Optional[int] = None,
        child_overlap_tokens: Optional[int] = None,
    ) -> ChunkingResult:
        """Chunks a ParsedDocument preserving its sections, pages, and metadata."""
        p_target = parent_target_tokens or self.parent_target_tokens
        c_target = child_target_tokens or self.child_target_tokens
        c_overlap = child_overlap_tokens or self.child_overlap_tokens
        lang = doc.detected_language or self.default_lang

        doc_title = doc.metadata.get("title") or doc.metadata.get("file_name") or "Document"

        parents: List[ParentChunk] = []
        children: List[ChildChunk] = []

        parent_idx = 0
        child_idx = 0

        # Scenario 1: Document has explicit sections (Markdown, DOCX)
        if doc.sections:
            for sec in doc.sections:
                if not sec.text.strip():
                    continue

                sec_tokens = estimate_tokens(sec.text, lang=lang)

                # If section fits within parent token budget, keep as single parent
                if sec_tokens <= int(p_target * 1.3):
                    parent = ParentChunk(
                        parent_index=parent_idx,
                        title=sec.title,
                        content=sec.text,
                        token_count=sec_tokens,
                        breadcrumbs=sec.breadcrumbs,
                        page_start=sec.start_page,
                        page_end=sec.end_page,
                        metadata={"section_level": sec.level},
                    )
                    parents.append(parent)

                    # Split this parent into child chunks
                    sec_children = self._create_child_chunks(
                        parent=parent,
                        doc_title=doc_title,
                        start_child_idx=child_idx,
                        target_tokens=c_target,
                        overlap_tokens=c_overlap,
                        lang=lang,
                    )
                    children.extend(sec_children)
                    child_idx += len(sec_children)
                    parent_idx += 1
                else:
                    # Section is large: split into multiple parent chunks
                    sentences = self.sentence_splitter.split_into_sentences(sec.text)
                    parent_text_blocks = self.sentence_splitter.pack_sentences_into_chunks(
                        sentences=sentences,
                        target_tokens=p_target,
                        overlap_tokens=100,  # Slight parent overlap for narrative continuity
                        lang=lang,
                    )

                    for sub_idx, p_text in enumerate(parent_text_blocks, start=1):
                        p_toks = estimate_tokens(p_text, lang=lang)
                        sub_title = f"{sec.title} (Part {sub_idx})" if len(parent_text_blocks) > 1 else sec.title
                        parent = ParentChunk(
                            parent_index=parent_idx,
                            title=sub_title,
                            content=p_text,
                            token_count=p_toks,
                            breadcrumbs=sec.breadcrumbs + ([f"Part {sub_idx}"] if len(parent_text_blocks) > 1 else []),
                            page_start=sec.start_page,
                            page_end=sec.end_page,
                            metadata={"section_level": sec.level, "sub_part": sub_idx},
                        )
                        parents.append(parent)

                        sec_children = self._create_child_chunks(
                            parent=parent,
                            doc_title=doc_title,
                            start_child_idx=child_idx,
                            target_tokens=c_target,
                            overlap_tokens=c_overlap,
                            lang=lang,
                        )
                        children.extend(sec_children)
                        child_idx += len(sec_children)
                        parent_idx += 1

        # Scenario 2: Document has pages (PDF)
        elif doc.pages:
            current_page_texts: List[str] = []
            current_page_numbers: List[int] = []
            current_tokens = 0

            for page in doc.pages:
                if not page.text.strip():
                    continue

                page_toks = estimate_tokens(page.text, lang=lang)

                if current_tokens + page_toks <= p_target or not current_page_texts:
                    current_page_texts.append(page.text)
                    current_page_numbers.append(page.page_number)
                    current_tokens += page_toks
                else:
                    # Flush parent
                    p_content = "\n\n".join(current_page_texts)
                    p_start = current_page_numbers[0]
                    p_end = current_page_numbers[-1]
                    title = f"Pages {p_start}-{p_end}" if p_start != p_end else f"Page {p_start}"

                    parent = ParentChunk(
                        parent_index=parent_idx,
                        title=title,
                        content=p_content,
                        token_count=current_tokens,
                        breadcrumbs=[title],
                        page_start=p_start,
                        page_end=p_end,
                        metadata={"page_start": p_start, "page_end": p_end},
                    )
                    parents.append(parent)

                    page_children = self._create_child_chunks(
                        parent=parent,
                        doc_title=doc_title,
                        start_child_idx=child_idx,
                        target_tokens=c_target,
                        overlap_tokens=c_overlap,
                        lang=lang,
                    )
                    children.extend(page_children)
                    child_idx += len(page_children)
                    parent_idx += 1

                    current_page_texts = [page.text]
                    current_page_numbers = [page.page_number]
                    current_tokens = page_toks

            if current_page_texts:
                p_content = "\n\n".join(current_page_texts)
                p_start = current_page_numbers[0]
                p_end = current_page_numbers[-1]
                title = f"Pages {p_start}-{p_end}" if p_start != p_end else f"Page {p_start}"

                parent = ParentChunk(
                    parent_index=parent_idx,
                    title=title,
                    content=p_content,
                    token_count=current_tokens,
                    breadcrumbs=[title],
                    page_start=p_start,
                    page_end=p_end,
                    metadata={"page_start": p_start, "page_end": p_end},
                )
                parents.append(parent)

                page_children = self._create_child_chunks(
                    parent=parent,
                    doc_title=doc_title,
                    start_child_idx=child_idx,
                    target_tokens=c_target,
                    overlap_tokens=c_overlap,
                    lang=lang,
                )
                children.extend(page_children)
                child_idx += len(page_children)
                parent_idx += 1

        # Scenario 3: Flat raw text fallback
        else:
            flat_result = self.chunk_raw_text(
                raw_text=doc.raw_text,
                doc_title=doc_title,
                parent_target_tokens=p_target,
                child_target_tokens=c_target,
                child_overlap_tokens=c_overlap,
                lang=lang,
            )
            return flat_result

        return ChunkingResult(parents=parents, children=children)

    def chunk_raw_text(
        self,
        raw_text: str,
        doc_title: str = "Document",
        parent_target_tokens: Optional[int] = None,
        child_target_tokens: Optional[int] = None,
        child_overlap_tokens: Optional[int] = None,
        lang: str = "ar",
    ) -> ChunkingResult:
        """Chunks flat text into parent and child chunks without prior parsed sections."""
        cleaned = clean_text(raw_text)
        if not cleaned:
            return ChunkingResult(parents=[], children=[])

        p_target = parent_target_tokens or self.parent_target_tokens
        c_target = child_target_tokens or self.child_target_tokens
        c_overlap = child_overlap_tokens or self.child_overlap_tokens

        sentences = self.sentence_splitter.split_into_sentences(cleaned)
        parent_blocks = self.sentence_splitter.pack_sentences_into_chunks(
            sentences=sentences,
            target_tokens=p_target,
            overlap_tokens=80,
            lang=lang,
        )

        parents: List[ParentChunk] = []
        children: List[ChildChunk] = []
        child_idx = 0

        for p_idx, p_text in enumerate(parent_blocks):
            p_toks = estimate_tokens(p_text, lang=lang)
            title = f"Section {p_idx + 1}"
            parent = ParentChunk(
                parent_index=p_idx,
                title=title,
                content=p_text,
                token_count=p_toks,
                breadcrumbs=[title],
            )
            parents.append(parent)

            p_children = self._create_child_chunks(
                parent=parent,
                doc_title=doc_title,
                start_child_idx=child_idx,
                target_tokens=c_target,
                overlap_tokens=c_overlap,
                lang=lang,
            )
            children.extend(p_children)
            child_idx += len(p_children)

        return ChunkingResult(parents=parents, children=children)

    def chunk_document(
        self,
        raw_text: str,
        doc_title: str,
        doc_author: Optional[str] = None,
        parent_target_tokens: int = 1000,
        child_target_tokens: int = 280,
        child_overlap_tokens: int = 50,
        lang: str = "ar",
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Protocol-compliant method matching `src.domain.protocols.Chunker`."""
        result = self.chunk_raw_text(
            raw_text=raw_text,
            doc_title=doc_title,
            parent_target_tokens=parent_target_tokens,
            child_target_tokens=child_target_tokens,
            child_overlap_tokens=child_overlap_tokens,
            lang=lang,
        )
        parent_dicts = [p.to_dict() for p in result.parents]
        child_dicts = [c.to_dict() for c in result.children]
        return parent_dicts, child_dicts

    def _create_child_chunks(
        self,
        parent: ParentChunk,
        doc_title: str,
        start_child_idx: int,
        target_tokens: int,
        overlap_tokens: int,
        lang: str,
    ) -> List[ChildChunk]:
        """Slices a parent chunk into overlapping child chunks with contextual header injection."""
        sentences = self.sentence_splitter.split_into_sentences(parent.content)
        child_text_blocks = self.sentence_splitter.pack_sentences_into_chunks(
            sentences=sentences,
            target_tokens=target_tokens,
            overlap_tokens=overlap_tokens,
            lang=lang,
        )

        child_chunks: List[ChildChunk] = []

        # Construct contextual header
        header_parts = [f"Document: {doc_title}"]
        if parent.title:
            header_parts.append(f"Section: {parent.title}")
        if parent.page_start:
            if parent.page_end and parent.page_end != parent.page_start:
                header_parts.append(f"Pages: {parent.page_start}-{parent.page_end}")
            else:
                header_parts.append(f"Page: {parent.page_start}")

        header_str = f"[{' | '.join(header_parts)}]"

        for i, body in enumerate(child_text_blocks):
            content_with_header = f"{header_str}\n\n{body}"
            tok_count = estimate_tokens(content_with_header, lang=lang)

            child_chunks.append(
                ChildChunk(
                    child_index=start_child_idx + i,
                    parent_index=parent.parent_index,
                    content=body,
                    content_with_header=content_with_header,
                    header=header_str,
                    token_count=tok_count,
                    breadcrumbs=parent.breadcrumbs,
                    page_number=parent.page_start,
                    metadata={
                        "parent_title": parent.title,
                        **parent.metadata,
                    },
                )
            )

        return child_chunks
