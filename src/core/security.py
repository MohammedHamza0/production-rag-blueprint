"""Security primitives: Deceptive KeyVault, API key hashing, nonces, and input validation."""

import hashlib
import os
import secrets
import uuid
from typing import Dict, Optional, Tuple


class KeyVault:
    """Enterprise Key Vault with deceptive non-linear partition reassembly.
    
    Prevents credential leakage via static environment scanners by splitting
    the working secret into non-linear partitions:
        - Part 1: TadabburApiKey (or MidadeApiKey / API_KEY_PART1)
        - Part 2: ApiSecret (or API_KEY_PART2)
        - Part 3: ApiSalt (or API_KEY_PART3)
    Notice the deceptive order in .env:
        TadabburApiKey (slice 1)
        ApiSalt (slice 3)
        ApiSecret (slice 2)
    """

    @classmethod
    def resolve_gemini_api_key(cls, env: Optional[Dict[str, str]] = None) -> str:
        """Dynamically reassembles Gemini API credentials in-memory."""
        source = env if env is not None else os.environ

        # Try primary deceptive keys
        p1 = (source.get("TadabburApiKey") or source.get("MidadeApiKey") or source.get("API_KEY_PART1") or "").strip()
        p2 = (source.get("ApiSecret") or source.get("API_KEY_PART2") or "").strip()
        p3 = (source.get("ApiSalt") or source.get("API_KEY_PART3") or "").strip()

        if p1 and p2 and p3:
            return f"{p1}{p2}{p3}"

        # If only part 1 is provided without salt/secret
        if p1 and not p2 and not p3:
            return p1

        # Fallback to direct environment key for local development
        direct = (source.get("GEMINI_API_KEY") or "").strip()
        if direct:
            return direct

        return ""

    @classmethod
    def has_gemini_key(cls, env: Optional[Dict[str, str]] = None) -> bool:
        """Returns True if a valid key can be assembled."""
        return len(cls.resolve_gemini_api_key(env)) > 0

    @classmethod
    def split_key(cls, raw_key: str) -> Tuple[str, str, str]:
        """Splits an API key string into 3 non-linear parts for deceptive environment deployment."""
        if not raw_key or len(raw_key.strip()) < 3:
            raise ValueError("Valid API key string with at least 3 characters is required to split.")

        clean = raw_key.strip()
        n = len(clean)
        chunk_len = n // 3
        remainder = n % 3

        len1 = chunk_len + (1 if remainder > 0 else 0)
        len2 = chunk_len + (1 if remainder > 1 else 0)

        p1 = clean[:len1]
        p2 = clean[len1 : len1 + len2]
        p3 = clean[len1 + len2 :]

        return p1, p2, p3


def hash_api_key(raw_key: str) -> Tuple[str, str]:
    """Computes SHA-256 hash and extracts prefix for database storage.
    
    Returns:
        (key_hash, key_prefix) e.g. ('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'rag_live_abc')
    """
    clean = raw_key.strip()
    key_hash = hashlib.sha256(clean.encode("utf-8")).hexdigest()
    key_prefix = clean[:10] if len(clean) >= 10 else clean
    return key_hash, key_prefix


def generate_boundary_nonce(length: int = 12) -> str:
    """Generates a cryptographic random hex nonce for enclosing untrusted evidence."""
    return secrets.token_hex(length // 2 if length % 2 == 0 else (length // 2) + 1)[:length]


def is_valid_uuid(val: Any) -> bool:
    """Validates whether a value is a valid UUID string."""
    if not val or not isinstance(val, (str, uuid.UUID)):
        return False
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, AttributeError, TypeError):
        return False
