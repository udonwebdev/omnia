"""
Omnia Module 30: Knowledge Graph Entity Resolution Engine
Implements deterministic and fuzzy identity matching, candidate evaluation,
similarity scoring, and non-destructive resolution.
"""

import re
import uuid
import time
from typing import List, Dict, Any, Tuple, Optional

from knowledge.models import (
    GraphEntity,
    EntityIdentity,
    ResolutionCandidate,
    ResolutionStatus,
    IdentifierType,
)
from knowledge.persistence import KnowledgePersistence


class EntityResolver:
    """
    Evaluates entity similarity and identifies duplicate/co-referent entities.
    Employs exact token matching, identifier overlap, and attribute consistency.
    Never destructively removes entities.
    """

    def __init__(self, persistence: KnowledgePersistence):
        self.persistence = persistence

    def compute_similarity(self, e1: GraphEntity, e2: GraphEntity) -> Tuple[float, List[str]]:
        """
        Calculates similarity between two entities based on:
        - Exact canonical name or alias match
        - Token overlap in names/aliases
        - Attribute value matches
        - Identity identifier overlaps
        Returns (score between 0.0 and 1.0, list of match reasons).
        """
        if e1.entity_id == e2.entity_id:
            return 1.0, ["identical_entity_id"]

        reasons = []
        score = 0.0

        # Type check - different types rarely resolve unless both are CUSTOM
        if e1.entity_type != e2.entity_type:
            return 0.0, ["different_entity_types"]

        # 1. Exact canonical name match
        name1 = e1.canonical_name.strip().lower()
        name2 = e2.canonical_name.strip().lower()

        if name1 == name2:
            score += 0.6
            reasons.append("exact_canonical_name_match")
        else:
            # Token overlap Jaccard
            tokens1 = set(re.findall(r"\w+", name1))
            tokens2 = set(re.findall(r"\w+", name2))
            if tokens1 and tokens2:
                jaccard = len(tokens1 & tokens2) / len(tokens1 | tokens2)
                if jaccard >= 0.5:
                    score += 0.3 * jaccard
                    reasons.append(f"name_token_overlap({jaccard:.2f})")

        # 2. Alias overlap
        aliases1 = {a.strip().lower() for a in e1.aliases}
        aliases2 = {a.strip().lower() for a in e2.aliases}

        # Check if canonical name appears in other's aliases
        if name1 in aliases2 or name2 in aliases1:
            score += 0.4
            reasons.append("alias_to_canonical_match")

        shared_aliases = aliases1 & aliases2
        if shared_aliases:
            score += 0.35
            reasons.append(f"shared_aliases({len(shared_aliases)})")

        # 3. Attribute overlap (e.g. email, domain, ip, version)
        common_keys = set(e1.attributes.keys()) & set(e2.attributes.keys())
        shared_attrs = 0
        for k in common_keys:
            v1 = str(e1.attributes[k]).strip().lower()
            v2 = str(e2.attributes[k]).strip().lower()
            if v1 and v1 == v2:
                shared_attrs += 1
                reasons.append(f"matching_attribute({k})")

        if shared_attrs > 0:
            score += min(0.3, shared_attrs * 0.15)

        # 4. Identity overlap from persistence
        ids1 = {i.identifier_value.strip().lower() for i in self.persistence.get_identities_for_entity(e1.entity_id)}
        ids2 = {i.identifier_value.strip().lower() for i in self.persistence.get_identities_for_entity(e2.entity_id)}
        shared_ids = ids1 & ids2
        if shared_ids:
            score += 0.5
            reasons.append(f"shared_identities({len(shared_ids)})")

        total_score = min(1.0, max(0.0, score))
        return total_score, reasons

    def evaluate_candidates(self, target_entity: GraphEntity, min_threshold: float = 0.5) -> List[ResolutionCandidate]:
        """
        Scans existing entities of the same type and creates resolution candidate records.
        """
        all_same_type = self.persistence.find_entities_by_type(target_entity.entity_type, limit=200)
        candidates = []

        for other in all_same_type:
            if other.entity_id == target_entity.entity_id:
                continue
            if other.status.value == "MERGED" or target_entity.status.value == "MERGED":
                continue

            score, reasons = self.compute_similarity(target_entity, other)
            if score >= min_threshold:
                cand = ResolutionCandidate(
                    candidate_id=f"cand-{uuid.uuid4().hex[:12]}",
                    source_entity_id=target_entity.entity_id,
                    target_entity_id=other.entity_id,
                    similarity_score=round(score, 3),
                    match_reasons=reasons,
                    status=ResolutionStatus.PENDING,
                    evaluated_at=time.time(),
                )
                self.persistence.record_resolution_candidate(cand)
                candidates.append(cand)

        return candidates

    def auto_resolve(self, auto_merge_threshold: float = 0.85) -> List[Dict[str, Any]]:
        """
        Scans pending resolution candidates. For those with score >= auto_merge_threshold,
        performs non-destructive entity merging.
        Returns list of resolution actions taken.
        """
        pending = self.persistence.get_pending_candidates(min_similarity=auto_merge_threshold)
        actions = []

        for cand in pending:
            source = self.persistence.get_entity(cand.source_entity_id)
            target = self.persistence.get_entity(cand.target_entity_id)
            if not source or not target:
                continue
            if source.status.value == "MERGED" or target.status.value == "MERGED":
                continue

            # Merge target into source (source remains primary)
            reason = f"Auto-resolved candidate {cand.candidate_id} score={cand.similarity_score} ({', '.join(cand.match_reasons)})"
            success = self.persistence.merge_entities(source.entity_id, target.entity_id, reason=reason)
            if success:
                actions.append({
                    "primary_id": source.entity_id,
                    "merged_id": target.entity_id,
                    "similarity_score": cand.similarity_score,
                    "reasons": cand.match_reasons,
                })

        return actions
