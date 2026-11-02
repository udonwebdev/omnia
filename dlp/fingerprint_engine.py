"""
dlp/fingerprint_engine.py
Content Fingerprinting & Document Tracking Engine for OMNIA Module 52:
Autonomous Data Loss Prevention, Sensitive Information Monitoring & Exfiltration Defense Intelligence.
"""

import hashlib
import uuid
import time
from typing import List, Dict, Any, Tuple, Optional, Set

from dlp.models import (
    ProtectedFingerprint, FingerprintAlgorithm, DataCategory
)
from dlp.persistence import DLPRepository


class ContentFingerprintingEngine:
    """
    Computes exact cryptographic file/content hashes (SHA-256) and rolling block shingles
    for document similarity and partial leak detection without leaking raw content.
    """

    DEFAULT_SHINGLE_SIZE = 32
    DEFAULT_SHINGLE_STEP = 16

    def __init__(self, repo: DLPRepository):
        self.repo = repo

    @staticmethod
    def compute_exact_hash(content: str | bytes) -> str:
        """Computes exact SHA-256 hex digest of normalized content."""
        if isinstance(content, str):
            data = content.strip().encode("utf-8")
        else:
            data = content
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def generate_shingle_hashes(
        content: str | bytes,
        shingle_size: int = DEFAULT_SHINGLE_SIZE,
        step: int = DEFAULT_SHINGLE_STEP
    ) -> List[str]:
        """
        Splits content into overlapping shingles of `shingle_size` bytes
        and computes SHA-256 hashes for each shingle.
        """
        if isinstance(content, str):
            raw_bytes = content.strip().encode("utf-8")
        else:
            raw_bytes = content

        if len(raw_bytes) <= shingle_size:
            return [hashlib.sha256(raw_bytes).hexdigest()]

        hashes: List[str] = []
        for i in range(0, len(raw_bytes) - shingle_size + 1, step):
            shingle = raw_bytes[i : i + shingle_size]
            hashes.append(hashlib.sha256(shingle).hexdigest())

        return list(set(hashes))

    @staticmethod
    def compute_jaccard_similarity(shingles_a: List[str], shingles_b: List[str]) -> float:
        """Computes Jaccard similarity coefficient between two sets of shingle hashes."""
        set_a: Set[str] = set(shingles_a)
        set_b: Set[str] = set(shingles_b)
        if not set_a or not set_b:
            return 0.0
        intersection = set_a.intersection(set_b)
        union = set_a.union(set_b)
        return len(intersection) / len(union)

    def register_protected_content(
        self,
        name: str,
        content: str | bytes,
        data_category: str = DataCategory.INTELLECTUAL_PROPERTY.value,
        algorithm: str = FingerprintAlgorithm.SHA256_EXACT.value,
        threshold: float = 0.8,
        metadata: Optional[Dict[str, Any]] = None,
        fingerprint_id: Optional[str] = None
    ) -> ProtectedFingerprint:
        """
        Registers a protected dataset or document fingerprint into the DLP repository.
        """
        fid = fingerprint_id or f"fp_{uuid.uuid4().hex[:12]}"
        exact_hash = self.compute_exact_hash(content)

        meta = metadata.copy() if metadata else {}
        meta["exact_sha256"] = exact_hash
        meta["content_length_bytes"] = len(content.encode("utf-8") if isinstance(content, str) else content)

        if algorithm == FingerprintAlgorithm.ROLLING_SHINGLE.value:
            shingles = self.generate_shingle_hashes(content)
            meta["shingle_count"] = len(shingles)
            meta["shingles"] = shingles
            fingerprint_hash = exact_hash
        else:
            fingerprint_hash = exact_hash

        fp = ProtectedFingerprint(
            fingerprint_id=fid,
            name=name,
            data_category=data_category,
            fingerprint_hash=fingerprint_hash,
            algorithm=algorithm,
            threshold=threshold,
            is_active=True,
            created_at=time.time(),
            metadata=meta,
        )

        return self.repo.save_fingerprint(fp)

    def match_content(
        self,
        content: str | bytes,
        threshold_override: Optional[float] = None
    ) -> List[Tuple[ProtectedFingerprint, float]]:
        """
        Matches arbitrary payload content against all active registered protected fingerprints.
        Returns tuples of (ProtectedFingerprint, similarity_score) for matches meeting threshold.
        """
        active_fps = self.repo.list_fingerprints(active_only=True)
        if not active_fps:
            return []

        exact_hash = self.compute_exact_hash(content)
        query_shingles: Optional[List[str]] = None

        matches: List[Tuple[ProtectedFingerprint, float]] = []

        for fp in active_fps:
            threshold = threshold_override if threshold_override is not None else fp.threshold

            # 1. Exact match test
            if fp.algorithm == FingerprintAlgorithm.SHA256_EXACT.value:
                if exact_hash == fp.fingerprint_hash:
                    matches.append((fp, 1.0))
            elif fp.algorithm == FingerprintAlgorithm.ROLLING_SHINGLE.value:
                # Check exact first
                if exact_hash == fp.fingerprint_hash:
                    matches.append((fp, 1.0))
                    continue

                # Rolling shingle Jaccard overlap
                stored_shingles = fp.metadata.get("shingles", [])
                if stored_shingles:
                    if query_shingles is None:
                        query_shingles = self.generate_shingle_hashes(content)
                    sim = self.compute_jaccard_similarity(query_shingles, stored_shingles)
                    if sim >= threshold:
                        matches.append((fp, sim))

        # Sort matches by similarity score descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches
