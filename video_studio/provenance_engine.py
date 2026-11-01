"""OMNIA Video Studio — Module 42: Media Asset Provenance & Relinking Engine.

Algorithmic core for:
- Chunked/streaming SHA-256 calculation for media files without UI freezing.
- Intelligent relinking candidate scoring and multi-tier ranking.
- Project dependency graph generation connecting projects, sequences, clips, assets, and revisions.
- Missing and modified media detection comparing disk attributes against asset provenance.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any, Dict, List, Optional, Tuple

from video_studio.media_models import MediaAsset
from video_studio.provenance_models import (
    DependencyEdge,
    DependencyEdgeType,
    DependencyNode,
    DependencyNodeType,
    ProjectDependencyGraph,
    RelinkMatchCandidate,
    RelinkMatchConfidence,
)
from video_studio.timeline_models import VideoSequence


def compute_file_sha256_chunked(file_path: str, chunk_size: int = 1024 * 1024) -> Optional[str]:
    """Computes SHA-256 fingerprint in streaming chunks to prevent memory spikes or UI thread blocking."""
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        return None
    h = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


class ProvenanceEngine:
    """Core domain logic for dependency graphing, integrity validation, and intelligent relinking scoring."""

    @staticmethod
    def build_dependency_graph(
        project_id: str,
        sequences: List[VideoSequence],
        assets: Dict[str, MediaAsset],
        revisions: Optional[List[Any]] = None,
    ) -> ProjectDependencyGraph:
        """Constructs a unified DAG connecting project, sequences, clips, assets, and snapshots."""
        graph = ProjectDependencyGraph(project_id=project_id)

        # 1. Project Root Node
        proj_node = DependencyNode(
            node_id=f"proj_{project_id}",
            node_type=DependencyNodeType.PROJECT,
            label=f"Project: {project_id}",
        )
        graph.add_node(proj_node)

        # 2. Asset Nodes
        for aid, asset in assets.items():
            is_missing = not (os.path.exists(asset.file_location) and os.path.isfile(asset.file_location))
            node = DependencyNode(
                node_id=f"asset_{aid}",
                node_type=DependencyNodeType.MEDIA_ASSET,
                label=asset.name or asset.original_name,
                is_missing=is_missing,
                details={
                    "asset_id": aid,
                    "file_location": asset.file_location,
                    "size_bytes": asset.size_bytes,
                    "sha256": asset.content_hash_sha256,
                },
            )
            graph.add_node(node)

        # 3. Sequences, Tracks, and Clips
        for seq in sequences:
            seq_node_id = f"seq_{seq.sequence_id}"
            seq_node = DependencyNode(
                node_id=seq_node_id,
                node_type=DependencyNodeType.SEQUENCE,
                label=seq.name,
                details={"sequence_id": seq.sequence_id, "revision": seq.revision},
            )
            graph.add_node(seq_node)
            graph.add_edge(
                DependencyEdge(
                    source_id=proj_node.node_id,
                    target_id=seq_node_id,
                    edge_type=DependencyEdgeType.CONTAINS,
                )
            )

            for track in seq.tracks:
                for item in track.items:
                    clip_node_id = f"clip_{item.item_id}"
                    clip_node = DependencyNode(
                        node_id=clip_node_id,
                        node_type=DependencyNodeType.CLIP,
                        label=item.name,
                        details={
                            "item_id": item.item_id,
                            "track_id": track.track_id,
                            "source_reference_id": item.source_reference_id,
                        },
                    )
                    graph.add_node(clip_node)
                    graph.add_edge(
                        DependencyEdge(
                            source_id=seq_node_id,
                            target_id=clip_node_id,
                            edge_type=DependencyEdgeType.CONTAINS,
                        )
                    )

                    # Connect Clip to Media Asset
                    ref_id = item.source_reference_id
                    target_asset_node_id = f"asset_{ref_id}"
                    if target_asset_node_id in graph.nodes:
                        graph.add_edge(
                            DependencyEdge(
                                source_id=clip_node_id,
                                target_id=target_asset_node_id,
                                edge_type=DependencyEdgeType.REFERENCES,
                                is_required=True,
                            )
                        )
                    else:
                        # Missing uncataloged asset dependency
                        missing_node = DependencyNode(
                            node_id=target_asset_node_id,
                            node_type=DependencyNodeType.MEDIA_ASSET,
                            label=f"Missing Asset: {ref_id}",
                            is_missing=True,
                        )
                        graph.add_node(missing_node)
                        graph.add_edge(
                            DependencyEdge(
                                source_id=clip_node_id,
                                target_id=target_asset_node_id,
                                edge_type=DependencyEdgeType.REFERENCES,
                                is_required=True,
                            )
                        )

        # 4. Revisions linking to assets
        if revisions:
            for rev in revisions:
                rev_node_id = f"rev_{rev.revision_id}"
                rev_node = DependencyNode(
                    node_id=rev_node_id,
                    node_type=DependencyNodeType.REVISION_SNAPSHOT,
                    label=rev.name,
                    details={"revision_id": rev.revision_id, "revision_number": rev.revision_number},
                )
                graph.add_node(rev_node)
                for aid in rev.referenced_asset_ids:
                    target_id = f"asset_{aid}"
                    if target_id in graph.nodes:
                        graph.add_edge(
                            DependencyEdge(
                                source_id=rev_node_id,
                                target_id=target_id,
                                edge_type=DependencyEdgeType.SNAPSHOT_PINS,
                                is_required=False,
                            )
                        )

        return graph

    @staticmethod
    def score_relink_candidate(
        asset: MediaAsset,
        candidate_file_path: str,
    ) -> RelinkMatchCandidate:
        """Evaluates a potential relink replacement file using multi-tier evidence."""
        if not os.path.exists(candidate_file_path) or not os.path.isfile(candidate_file_path):
            return RelinkMatchCandidate(
                file_path=candidate_file_path,
                filename=os.path.basename(candidate_file_path),
                confidence=RelinkMatchConfidence.UNVERIFIED,
                score=0.0,
                match_reasons=["File not found on disk."],
            )

        cand_filename = os.path.basename(candidate_file_path)
        cand_size = os.path.getsize(candidate_file_path)
        cand_hash = compute_file_sha256_chunked(candidate_file_path)

        reasons: List[str] = []
        score = 0.0

        # Tier 1: Cryptographic content fingerprint match (100% confidence)
        if asset.content_hash_sha256 and cand_hash and asset.content_hash_sha256 == cand_hash:
            reasons.append("Cryptographic SHA-256 fingerprint verified exactly.")
            return RelinkMatchCandidate(
                file_path=candidate_file_path,
                filename=cand_filename,
                size_bytes=cand_size,
                content_fingerprint_sha256=cand_hash,
                confidence=RelinkMatchConfidence.VERIFIED_EXACT,
                score=1.0,
                match_reasons=reasons,
                is_verified=True,
            )

        # Tier 2: Exact Filename match
        orig_name = asset.original_name or asset.name
        name_matched = False
        if orig_name and cand_filename.lower() == orig_name.lower():
            score += 0.4
            name_matched = True
            reasons.append("Filename matches original asset name.")

        # Tier 3: File size match
        size_matched = False
        if asset.size_bytes > 0 and cand_size == asset.size_bytes:
            score += 0.4
            size_matched = True
            reasons.append(f"File size matches exactly ({cand_size} bytes).")

        # Tier 4: Extension match
        _, asset_ext = os.path.splitext(orig_name)
        _, cand_ext = os.path.splitext(cand_filename)
        if asset_ext and cand_ext and asset_ext.lower() == cand_ext.lower():
            score += 0.1
            reasons.append(f"File extension matches '{cand_ext}'.")

        # Determine confidence grade
        confidence = RelinkMatchConfidence.UNVERIFIED
        if name_matched and size_matched:
            confidence = RelinkMatchConfidence.HIGH_PROBABILITY
        elif name_matched:
            confidence = RelinkMatchConfidence.PARTIAL_MATCH

        return RelinkMatchCandidate(
            file_path=candidate_file_path,
            filename=cand_filename,
            size_bytes=cand_size,
            content_fingerprint_sha256=cand_hash,
            confidence=confidence,
            score=min(round(score, 3), 0.99),
            match_reasons=reasons,
            is_verified=False,
        )
