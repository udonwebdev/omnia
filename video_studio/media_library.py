"""OMNIA Video Studio — Project Media Library, Bins & Asset Query Engine (Module 2).

Manages project-scoped media libraries, hierarchical logical bins (collections),
asset movement, metadata updates, and flexible query/search abstractions.
Keeps logical organization strictly separated from physical storage locations.
"""

import time
import uuid
import logging
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field

from video_studio.media_models import (
    MediaAsset,
    AssetMediaType,
    AssetLifecycleStatus,
    MediaRelationship,
    MediaRelationshipType,
)

logger = logging.getLogger("Omnia.VideoStudio.Library")

@dataclass
class MediaBinNode:
    """Logical bin / folder in the project media library."""
    bin_id: str
    project_id: str
    name: str
    parent_bin_id: Optional[str] = None
    color: str = "#808080"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bin_id": self.bin_id,
            "project_id": self.project_id,
            "name": self.name,
            "parent_bin_id": self.parent_bin_id,
            "color": self.color,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

@dataclass
class MediaSearchQuery:
    """Multi-parameter query criteria for asset searching and filtering."""
    query_text: Optional[str] = None
    media_types: Optional[List[AssetMediaType]] = None
    statuses: Optional[List[AssetLifecycleStatus]] = None
    bin_id: Optional[str] = None
    include_sub_bins: bool = True
    tags: Optional[List[str]] = None
    codec: Optional[str] = None
    container: Optional[str] = None
    min_duration: Optional[float] = None
    max_duration: Optional[float] = None
    min_width: Optional[int] = None
    min_height: Optional[int] = None
    sort_by: str = "created_at"  # name, created_at, size_bytes, duration_seconds
    sort_descending: bool = True
    limit: int = 100
    offset: int = 0

class ProjectMediaLibrary:
    """In-memory & persistent media library for an active Video Studio project."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self._assets: Dict[str, MediaAsset] = {}
        self._bins: Dict[str, MediaBinNode] = {}
        self._relationships: Dict[str, MediaRelationship] = {}
        self._hash_to_asset_ids: Dict[str, Set[str]] = {}

        # Initialize standard default bins
        self._create_default_bins()

    def _create_default_bins(self) -> None:
        """Sets up default organizational bins for video editing workflows."""
        defaults = [
            ("bin_footage", "Footage", "#3b82f6"),
            ("bin_audio", "Audio", "#10b981"),
            ("bin_graphics", "Graphics", "#8b5cf6"),
            ("bin_sequences", "Sequences", "#f59e0b"),
            ("bin_captions", "Captions", "#ec4899"),
        ]
        for bid, name, col in defaults:
            self._bins[bid] = MediaBinNode(
                bin_id=bid,
                project_id=self.project_id,
                name=name,
                parent_bin_id=None,
                color=col,
            )

    # -------------------------------------------------------------------------
    # Asset Management
    # -------------------------------------------------------------------------

    def add_asset(self, asset: MediaAsset) -> None:
        """Registers a media asset into this project library."""
        asset.project_id = self.project_id
        self._assets[asset.asset_id] = asset

        if asset.content_hash_sha256:
            if asset.content_hash_sha256 not in self._hash_to_asset_ids:
                self._hash_to_asset_ids[asset.content_hash_sha256] = set()
            self._hash_to_asset_ids[asset.content_hash_sha256].add(asset.asset_id)

    def get_asset(self, asset_id: str) -> Optional[MediaAsset]:
        return self._assets.get(asset_id)

    def remove_asset(self, asset_id: str) -> bool:
        """Removes asset reference from project without deleting physical source media."""
        if asset_id in self._assets:
            asset = self._assets.pop(asset_id)
            if asset.content_hash_sha256 and asset.content_hash_sha256 in self._hash_to_asset_ids:
                self._hash_to_asset_ids[asset.content_hash_sha256].discard(asset_id)
            return True
        return False

    def list_assets(self) -> List[MediaAsset]:
        return list(self._assets.values())

    def find_duplicate_asset(self, content_hash: str) -> Optional[MediaAsset]:
        """Checks if an identical file has already been ingested into this project."""
        if not content_hash or content_hash not in self._hash_to_asset_ids:
            return None
        existing_ids = self._hash_to_asset_ids[content_hash]
        for aid in existing_ids:
            if aid in self._assets:
                return self._assets[aid]
        return None

    # -------------------------------------------------------------------------
    # Bin / Collection Operations
    # -------------------------------------------------------------------------

    def create_bin(self, name: str, parent_bin_id: Optional[str] = None, color: str = "#808080") -> MediaBinNode:
        """Creates a new logical bin."""
        if parent_bin_id and parent_bin_id not in self._bins:
            raise ValueError(f"Parent bin {parent_bin_id} does not exist.")

        bin_id = f"bin_{uuid.uuid4().hex[:8]}"
        node = MediaBinNode(
            bin_id=bin_id,
            project_id=self.project_id,
            name=name.strip() or "New Bin",
            parent_bin_id=parent_bin_id,
            color=color,
        )
        self._bins[bin_id] = node
        return node

    def rename_bin(self, bin_id: str, new_name: str) -> bool:
        if bin_id not in self._bins:
            return False
        self._bins[bin_id].name = new_name.strip() or "Untitled Bin"
        self._bins[bin_id].updated_at = time.time()
        return True

    def delete_bin(self, bin_id: str, recursive: bool = False) -> bool:
        """Deletes a bin. Assets inside are moved to root (None)."""
        if bin_id not in self._bins:
            return False

        # Gather descendant bins
        children = [bid for bid, b in self._bins.items() if b.parent_bin_id == bin_id]
        if children and not recursive:
            raise ValueError(f"Cannot delete bin {bin_id}: contains child bins and recursive=False.")

        if recursive:
            for child_id in children:
                self.delete_bin(child_id, recursive=True)

        # Reassign all assets in this bin to root
        for asset in self._assets.values():
            if asset.bin_id == bin_id:
                asset.bin_id = None
                asset.updated_at = time.time()

        del self._bins[bin_id]
        return True

    def move_asset_to_bin(self, asset_id: str, target_bin_id: Optional[str]) -> bool:
        """Moves an asset into a logical bin (or root if None)."""
        if asset_id not in self._assets:
            return False
        if target_bin_id is not None and target_bin_id not in self._bins:
            raise ValueError(f"Target bin {target_bin_id} does not exist.")

        self._assets[asset_id].bin_id = target_bin_id
        self._assets[asset_id].updated_at = time.time()
        return True

    def get_bin(self, bin_id: str) -> Optional[MediaBinNode]:
        return self._bins.get(bin_id)

    def list_bins(self) -> List[MediaBinNode]:
        return list(self._bins.values())

    def get_bin_hierarchy(self) -> List[Dict[str, Any]]:
        """Returns recursive bin tree structure for UI explorer."""
        roots = [b for b in self._bins.values() if b.parent_bin_id is None]

        def _build_node(b: MediaBinNode) -> Dict[str, Any]:
            children = [
                _build_node(child)
                for child in self._bins.values()
                if child.parent_bin_id == b.bin_id
            ]
            asset_count = sum(1 for a in self._assets.values() if a.bin_id == b.bin_id)
            return {
                "bin_id": b.bin_id,
                "name": b.name,
                "color": b.color,
                "asset_count": asset_count,
                "children": children,
            }

        return [_build_node(r) for r in roots]

    # -------------------------------------------------------------------------
    # Tags & Search
    # -------------------------------------------------------------------------

    def add_tag(self, asset_id: str, tag: str) -> bool:
        asset = self.get_asset(asset_id)
        if not asset:
            return False
        clean_tag = tag.strip().lower()
        if clean_tag and clean_tag not in asset.tags:
            asset.tags.append(clean_tag)
            asset.updated_at = time.time()
        return True

    def remove_tag(self, asset_id: str, tag: str) -> bool:
        asset = self.get_asset(asset_id)
        if not asset:
            return False
        clean_tag = tag.strip().lower()
        if clean_tag in asset.tags:
            asset.tags.remove(clean_tag)
            asset.updated_at = time.time()
        return True

    def search_assets(self, query: MediaSearchQuery) -> List[MediaAsset]:
        """Executes a multi-criteria search against the project media library."""
        results = []

        # Find all descendant bin IDs if query specifies a bin
        allowed_bins = None
        if query.bin_id is not None:
            allowed_bins = {query.bin_id}
            if query.include_sub_bins:
                stack = [query.bin_id]
                while stack:
                    curr = stack.pop()
                    for bid, b in self._bins.items():
                        if b.parent_bin_id == curr and bid not in allowed_bins:
                            allowed_bins.add(bid)
                            stack.append(bid)

        for asset in self._assets.values():
            # Bin filter
            if allowed_bins is not None and asset.bin_id not in allowed_bins:
                continue

            # Text query (searches name, original name, metadata tags)
            if query.query_text:
                q = query.query_text.lower()
                matches_text = (
                    q in asset.name.lower()
                    or q in asset.original_name.lower()
                    or any(q in t for t in asset.tags)
                )
                if not matches_text:
                    continue

            # Media type filter
            if query.media_types and asset.media_type not in query.media_types:
                continue

            # Status filter
            if query.statuses and asset.status not in query.statuses:
                continue

            # Tags filter
            if query.tags:
                wanted = {t.lower() for t in query.tags}
                if not wanted.issubset({t.lower() for t in asset.tags}):
                    continue

            # Codec filter
            if query.codec:
                c = query.codec.lower()
                matches_codec = (
                    (asset.video_codec and c in asset.video_codec.lower())
                    or (asset.audio_codec and c in asset.audio_codec.lower())
                )
                if not matches_codec:
                    continue

            # Container filter
            if query.container and query.container.lower() != asset.container.lower():
                continue

            # Duration filter
            if query.min_duration is not None and asset.duration_seconds < query.min_duration:
                continue
            if query.max_duration is not None and asset.duration_seconds > query.max_duration:
                continue

            # Resolution filter
            if query.min_width is not None and (asset.width or 0) < query.min_width:
                continue
            if query.min_height is not None and (asset.height or 0) < query.min_height:
                continue

            results.append(asset)

        # Sorting
        sort_key = lambda a: getattr(a, query.sort_by, a.created_at)
        results.sort(key=sort_key, reverse=query.sort_descending)

        # Pagination
        start = query.offset
        end = query.offset + query.limit
        return results[start:end]

    # -------------------------------------------------------------------------
    # Media Relationships
    # -------------------------------------------------------------------------

    def link_relationship(
        self,
        source_asset_id: str,
        target_asset_id: str,
        rel_type: MediaRelationshipType,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MediaRelationship:
        """Links two assets together explicitly (e.g. original to proxy or original to derivative)."""
        rel_id = f"rel_{uuid.uuid4().hex[:10]}"
        rel = MediaRelationship(
            relationship_id=rel_id,
            source_asset_id=source_asset_id,
            target_asset_id=target_asset_id,
            relationship_type=rel_type,
            metadata=metadata or {},
        )
        self._relationships[rel_id] = rel
        return rel

    def get_related_assets(self, asset_id: str) -> List[MediaRelationship]:
        return [
            r for r in self._relationships.values()
            if r.source_asset_id == asset_id or r.target_asset_id == asset_id
        ]

class MediaLibraryRegistry:
    """Manages active project media libraries across multiple open projects."""

    def __init__(self):
        self._libraries: Dict[str, ProjectMediaLibrary] = {}

    def get_or_create(self, project_id: str) -> ProjectMediaLibrary:
        if project_id not in self._libraries:
            self._libraries[project_id] = ProjectMediaLibrary(project_id)
        return self._libraries[project_id]

    def remove(self, project_id: str) -> None:
        if project_id in self._libraries:
            del self._libraries[project_id]

# Global singleton
media_library_registry = MediaLibraryRegistry()


# Service alias for transitions/effects
media_library_service = media_library_registry
