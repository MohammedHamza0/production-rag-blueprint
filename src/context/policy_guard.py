"""PolicyGuard: Sub-millisecond deterministic input validation, prompt injection & jailbreak detection."""

from dataclasses import dataclass
import re
from typing import Optional
from src.core.logging import get_logger
from src.ingestion.normalizers import clean_text

logger = get_logger("context.policy_guard")


@dataclass
class GuardCheckResult:
    """Outcome of the PolicyGuard evaluation."""

    is_allowed: bool
    violation_type: Optional[str] = None  # PROMPT_INJECTION, JAILBREAK, SYSTEM_PROMPT_LEAK, OVERSIZED_INPUT
    sanitized_query: str = ""
    rejection_reason: Optional[str] = None


# Patterns detecting prompt injection and jailbreak overrides
INJECTION_PATTERNS = [
    # Direct instruction overrides (English)
    r"\b(ignore|disregard|forget|override)\s+(all\s+)?(previous|prior|system)\s+(instructions|prompts|directions|rules)\b",
    r"\byou\s+are\s+now\s+(in\s+developer\s+mode|dan|unfiltered|jailbroken)\b",
    r"\b(bypass|disable)\s+(safety|content\s+filters|security\s+guardrails)\b",
    r"\bact\s+as\s+(an?\s+unrestricted|dan|evil|hacker)\b",
    # System prompt extraction / leakage
    r"\b(show|reveal|display|output|print|repeat)\s+(your\s+)?(system\s+prompt|developer\s+instructions|initial\s+prompt|secret\s+key)\b",
    r"\bwhat\s+(is|are)\s+your\s+(exact\s+)?(system\s+prompt|hidden\s+instructions)\b",
    # Arabic instruction overrides
    r"(تجاهل|انس|احذف|تجاوز|الغ)\s+(كل\s+)?(التعليمات|التوجيهات|القواعد|الأوامر)\s+(السابقة|المسبقة|الأولية|الأساسية)",
    r"أنت\s+الآن\s+(في\s+وضع\s+المطور|بدون\s+قيود|حر\s+تماماً)",
    r"(تجاوز|عطل|أوقف)\s+(حواجز|فلاتر|سياسات)\s+(الأمان|الحماية|النظام)",
    # Arabic system prompt extraction
    r"(اعرض|أظهر|اطبع|اكتب|اكشف|ما\s+هو)\s+(برومبت\s+النظام|تعليمات\s+النظام|التعليمات\s+السرية|مفتاح\s+النظام)",
    # SQL Injection heuristics
    r"\b(select\s+.+\s+from\s+|insert\s+into\s+|update\s+.+\s+set\s+|delete\s+from\s+|drop\s+table\b|union\s+select\b)",
    r"(--|;|\/\*|\*\/)\s*(select|drop|insert|update|delete|create)\b",
    # XSS & HTML Script injection
    r"<\s*script[^>]*>.*?<\s*/\s*script\s*>",
    r"javascript\s*:\s*",
]

INJECTION_REGEX = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE | re.DOTALL)


class PolicyGuard:
    """Deterministic security guardrail protecting against prompt injections and malicious inputs."""

    def __init__(self, max_query_chars: int = 4000):
        self.max_query_chars = max_query_chars

    def check_query(self, raw_query: str) -> GuardCheckResult:
        """Inspects query under 1ms for size bounds, control characters, and injection patterns."""
        if not raw_query or not raw_query.strip():
            return GuardCheckResult(
                is_allowed=False,
                violation_type="EMPTY_QUERY",
                sanitized_query="",
                rejection_reason="Query is empty.",
            )

        # 1. Size ceiling check
        if len(raw_query) > self.max_query_chars:
            logger.warning(
                "policy_guard_violation_oversized",
                length=len(raw_query),
                max_allowed=self.max_query_chars,
            )
            return GuardCheckResult(
                is_allowed=False,
                violation_type="OVERSIZED_INPUT",
                sanitized_query="",
                rejection_reason=f"Query length ({len(raw_query)} chars) exceeds maximum limit ({self.max_query_chars} chars).",
            )

        # 2. Sanitize null bytes and invalid characters
        sanitized = clean_text(raw_query)

        # 3. Check for injection or jailbreak attempts
        match = INJECTION_REGEX.search(sanitized)
        if match:
            matched_phrase = match.group(0).lower()
            logger.warning(
                "policy_guard_violation_injection_blocked",
                pattern=matched_phrase,
            )
            if any(k in matched_phrase for k in ["select", "drop table", "insert into", "delete from", "union"]):
                v_type = "SQL_INJECTION"
            elif "script" in matched_phrase or "javascript" in matched_phrase:
                v_type = "XSS_VECTOR"
            elif any(k in matched_phrase for k in ["developer mode", "jailbreak", "unrestricted", "dan"]):
                v_type = "JAILBREAK_ATTEMPT"
            else:
                v_type = "PROMPT_INJECTION"

            return GuardCheckResult(
                is_allowed=False,
                violation_type=v_type,
                sanitized_query="",
                rejection_reason="Your query contains prohibited instructions or attempts to bypass system policies.",
            )

        return GuardCheckResult(
            is_allowed=True,
            sanitized_query=sanitized,
        )

