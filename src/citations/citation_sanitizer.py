"""Citation Sanitizer, Phantom Stripper, Sequential Aligner, and Grounding Auditor."""

from dataclasses import dataclass
import re
from typing import Dict, List, Optional, Set, Tuple
from src.core.logging import get_logger
from src.domain.entities import GroundingAudit, RetrievedSource, StructuredCitation

logger = get_logger("citations.citation_sanitizer")

# Eastern Arabic numerals mapping to standard ASCII digits
EASTERN_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# Bracketed citation pattern e.g. [1], [1, 2], [ 1 , 3 ]
CITATION_PATTERN = re.compile(r"\[([\d\s,]+)\]")


@dataclass
class SanitizationResult:
    """Outcome of citation sanitization and source reconciliation."""

    sanitized_text: str
    reconciled_sources: List[RetrievedSource]
    structured_citations: List[StructuredCitation]
    grounding_audit: GroundingAudit
    stripped_phantoms_count: int = 0
    was_modified: bool = False


class CitationSanitizer:
    """Sanitizes generated LLM citations, strips phantom references, and aligns sequential numbers."""

    def sanitize_and_align(
        self,
        raw_text: str,
        sources: List[RetrievedSource],
    ) -> SanitizationResult:
        """Sanitizes text, eliminates phantom citations, and remaps indices sequentially."""
        if not raw_text:
            return SanitizationResult(
                sanitized_text="",
                reconciled_sources=[],
                structured_citations=[],
                grounding_audit=GroundingAudit(status="EMPTY", groundedness_score=0.0),
                stripped_phantoms_count=0,
                was_modified=False,
            )

        # 1. Normalize Eastern Arabic digits to standard ASCII numerals inside text
        normalized_text = raw_text.translate(EASTERN_ARABIC_DIGITS)

        # Build mapping of available source indices
        available_sources_map: Dict[int, RetrievedSource] = {
            s.source_index: s for s in sources
        }
        max_source_idx = max(available_sources_map.keys()) if available_sources_map else 0

        # 2. First Pass: Identify all referenced source indices and detect phantoms
        referenced_indices: List[int] = []
        phantom_indices: Set[int] = set()

        for match in CITATION_PATTERN.finditer(normalized_text):
            inner = match.group(1)
            parts = [p.strip() for p in inner.split(",") if p.strip().isdigit()]
            for p in parts:
                idx = int(p)
                if idx in available_sources_map:
                    if idx not in referenced_indices:
                        referenced_indices.append(idx)
                else:
                    phantom_indices.add(idx)

        # 3. Create Sequential Remapping (e.g. if sources [2, 5] were cited, map: 2->1, 5->2)
        remapping: Dict[int, int] = {
            old_idx: new_idx for new_idx, old_idx in enumerate(referenced_indices, start=1)
        }

        stripped_phantoms_count = len(phantom_indices)

        # 4. Replace citations in text using remapping and strip phantoms
        def replace_citation(match: re.Match) -> str:
            inner = match.group(1)
            parts = [p.strip() for p in inner.split(",") if p.strip().isdigit()]
            valid_new_indices: List[int] = []

            for p in parts:
                idx = int(p)
                if idx in remapping:
                    valid_new_indices.append(remapping[idx])

            if not valid_new_indices:
                return ""  # Strip entirely if all were phantoms

            # Deduplicate and sort
            unique_new = sorted(set(valid_new_indices))
            return "[" + ", ".join(str(n) for n in unique_new) + "]"

        sanitized_text = CITATION_PATTERN.sub(replace_citation, normalized_text)
        # Clean potential double spaces from removed phantoms
        sanitized_text = re.sub(r"\s{2,}", " ", sanitized_text).strip()

        # 5. Build Reconciled Sources list matching the new sequential indices
        reconciled_sources: List[RetrievedSource] = []
        for old_idx in referenced_indices:
            orig_source = available_sources_map[old_idx]
            new_idx = remapping[old_idx]

            # Re-index source
            reconciled = RetrievedSource(
                source_index=new_idx,
                document_id=orig_source.document_id,
                document_title=orig_source.document_title,
                document_author=orig_source.document_author,
                work_id=orig_source.work_id,
                work_title=orig_source.work_title,
                edition_id=orig_source.edition_id,
                edition_title=orig_source.edition_title,
                edition_language=orig_source.edition_language,
                chunk_language=orig_source.chunk_language,
                content=orig_source.content,
                page_number=orig_source.page_number,
                chapter_title=orig_source.chapter_title,
                chunk_id=orig_source.chunk_id,
                chunk_index=orig_source.chunk_index,
                chunk_type=orig_source.chunk_type,
                parent_chunk_id=orig_source.parent_chunk_id,
                depth=orig_source.depth,
                volume_number=orig_source.volume_number,
                breadcrumb=orig_source.breadcrumb,
                vector_similarity=orig_source.vector_similarity,
                text_score=orig_source.text_score,
                combined_score=orig_source.combined_score,
                original_source_index=old_idx,
                parent_content=orig_source.parent_content,
                is_expanded=orig_source.is_expanded,
            )
            reconciled_sources.append(reconciled)

        # 6. Extract Structured Citations and compute lightweight claim entailment
        structured_citations: List[StructuredCitation] = []
        citation_counter = 1

        # Break sanitized text into sentences to associate each citation with its claim
        sentences = [s.strip() for s in re.split(r"[.!?؟؛\n]+", sanitized_text) if s.strip()]

        for sent in sentences:
            cite_matches = CITATION_PATTERN.findall(sent)
            if not cite_matches:
                continue

            for match_str in cite_matches:
                parts = [p.strip() for p in match_str.split(",") if p.strip().isdigit()]
                for p in parts:
                    new_idx = int(p)
                    # Find corresponding reconciled source
                    src = next((s for s in reconciled_sources if s.source_index == new_idx), None)
                    if not src:
                        continue

                    # Lightweight lexical overlap entailment check
                    entailment = self._compute_lexical_entailment(sent, src.content)

                    structured_citations.append(
                        StructuredCitation(
                            citation_index=citation_counter,
                            raw_match=f"[{new_idx}]",
                            source_index=new_idx,
                            document_id=str(src.document_id),
                            document_title=src.document_title,
                            page_number=src.page_number,
                            chapter_title=src.chapter_title,
                            breadcrumb=src.breadcrumb,
                            claim_text=sent,
                            entailment_score=entailment,
                            is_supported=entailment >= 0.20,
                        )
                    )
                    citation_counter += 1

        # 7. Compile Grounding Audit
        total_cites = len(structured_citations)
        supported_cites = sum(1 for c in structured_citations if c.is_supported)
        groundedness_score = (
            (supported_cites / total_cites * 100.0) if total_cites > 0 else (100.0 if not sources else 50.0)
        )

        status = "VERIFIED" if groundedness_score >= 70.0 else ("WEAK_SUPPORT" if total_cites > 0 else "UNGROUNDED")

        audit = GroundingAudit(
            status=status,
            total_citations=total_cites,
            valid_citations=supported_cites,
            invalid_count=stripped_phantoms_count,
            groundedness_score=round(groundedness_score, 1),
            claim_entailment_score=round(
                (sum(c.entailment_score for c in structured_citations) / total_cites * 100.0) if total_cites > 0 else 0.0,
                1,
            ),
            claims_count=len(sentences),
            supported_claims_count=supported_cites,
            structured_citations=structured_citations,
            reconciled_sources=reconciled_sources,
        )

        was_modified = (sanitized_text != raw_text)

        logger.debug(
            "citations_sanitized",
            total_citations=total_cites,
            phantoms_stripped=stripped_phantoms_count,
            reconciled_sources=len(reconciled_sources),
            groundedness=groundedness_score,
        )

        return SanitizationResult(
            sanitized_text=sanitized_text,
            reconciled_sources=reconciled_sources,
            structured_citations=structured_citations,
            grounding_audit=audit,
            stripped_phantoms_count=stripped_phantoms_count,
            was_modified=was_modified,
        )

    @staticmethod
    def _compute_lexical_entailment(claim: str, source_text: str) -> float:
        """Computes lexical token overlap ratio between claim and cited source."""
        # Simple word token set overlap
        claim_words = {w.lower() for w in re.findall(r"\w+", claim) if len(w) > 2}
        source_words = {w.lower() for w in re.findall(r"\w+", source_text) if len(w) > 2}

        if not claim_words or not source_words:
            return 0.0

        overlap = claim_words.intersection(source_words)
        return round(len(overlap) / len(claim_words), 2)
