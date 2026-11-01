"""OMNIA Video Studio — Professional Proxy Media & Relinking Service (Module 18).

Coordinates:
- Standard & custom proxy profiles management (480p, 720p, 1080p, custom).
- Queueing and lifecycle transitions of proxy generation.
- Dynamic source resolution for playback (ORIGINAL vs PROXY).
- Enforcement of export policies (ORIGINALS_ONLY vs PROXIES_ALLOWED).
- Project-level missing media discovery, candidate ranking, and transactional relinking.
- Module 1 Capability registration.
"""

from typing import Dict, Any, List, Optional, Tuple
import os
import time
import uuid
import logging

from video_studio.proxy_models import (
    ProxyLifecycleStatus,
    ProxyProfileType,
    PlaybackSourceMode,
    ExportSourcePolicy,
    ProxyProfileConfig,
    ProxyMediaRecord,
    RelinkCandidate,
    RelinkResult,
)
from video_studio.proxy_engine import ProxyEngine
from video_studio.relinking_engine import RelinkingEngine
from video_studio.media_models import MediaAsset
from video_studio.media_library import media_library_registry, ProjectMediaLibrary
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import (
    VideoStudioCategory,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
)

logger = logging.getLogger("omnia.video_studio.proxy_service")

# Default standard profiles
STANDARD_PROFILES: Dict[str, ProxyProfileConfig] = {
    "profile_480p": ProxyProfileConfig(
        profile_id="profile_480p",
        name="Lightweight Proxy (480p)",
        profile_type=ProxyProfileType.LIGHTWEIGHT_480P,
        target_width=854,
        target_height=480,
        bitrate_kbps=1500,
        video_codec="mp4v",
        container="mp4",
    ),
    "profile_720p": ProxyProfileConfig(
        profile_id="profile_720p",
        name="Standard Proxy (720p)",
        profile_type=ProxyProfileType.STANDARD_720P,
        target_width=1280,
        target_height=720,
        bitrate_kbps=3500,
        video_codec="mp4v",
        container="mp4",
    ),
    "profile_1080p": ProxyProfileConfig(
        profile_id="profile_1080p",
        name="High-Res Proxy (1080p)",
        profile_type=ProxyProfileType.HIGH_1080P,
        target_width=1920,
        target_height=1080,
        bitrate_kbps=6000,
        video_codec="mp4v",
        container="mp4",
    ),
}


class ProxyService:
    """Unified service orchestrating proxy generation, source selection, and media relinking."""

    def __init__(self, proxy_engine: Optional[ProxyEngine] = None, relinking_engine: Optional[RelinkingEngine] = None):
        self.proxy_engine = proxy_engine or ProxyEngine()
        self.relinking_engine = relinking_engine or RelinkingEngine()
        self.profiles: Dict[str, ProxyProfileConfig] = dict(STANDARD_PROFILES)
        self.records: Dict[str, ProxyMediaRecord] = {} # proxy_id -> ProxyMediaRecord
        self.asset_proxies: Dict[str, str] = {} # asset_id -> proxy_id
        self._register_capabilities()

    def _register_capabilities(self) -> None:
        """Register Module 18 capabilities in the global registry."""
        try:
            caps = [
                VideoStudioCapabilityDescriptor(
                    id="video.proxy.generation",
                    name="Proxy Media Generation",
                    description="Aspect-ratio preserved non-destructive downscaled proxy media rendering",
                    category=VideoStudioCategory.MEDIA,
                    implementation_state=ImplementationState.IMPLEMENTED,
                    tags=["proxy", "transcode", "downscale"],
                ),
                VideoStudioCapabilityDescriptor(
                    id="video.proxy.source_selection",
                    name="Playback Source Selection",
                    description="Intelligent playback source switching with export isolation",
                    category=VideoStudioCategory.TIMELINE,
                    implementation_state=ImplementationState.IMPLEMENTED,
                    tags=["playback", "source_mode", "proxy"],
                ),
                VideoStudioCapabilityDescriptor(
                    id="video.media.relinking",
                    name="Missing Media Relinking",
                    description="Multi-signal candidate matching and transactional media relinking",
                    category=VideoStudioCategory.MEDIA,
                    implementation_state=ImplementationState.IMPLEMENTED,
                    tags=["relink", "offline_media", "recovery"],
                ),
            ]
            for cap in caps:
                try:
                    video_studio_capability_registry.register(cap, auth_token="core")
                except Exception as e:
                    logger.debug(f"Capability '{cap.id}' registration note: {e}")
        except Exception as ex:
            logger.debug(f"Capabilities registry not available: {ex}")

    # --------------------------------------------------------------------------
    # Profile Management
    # --------------------------------------------------------------------------

    def get_profile(self, profile_id: str) -> Optional[ProxyProfileConfig]:
        return self.profiles.get(profile_id)

    def list_profiles(self) -> List[Dict[str, Any]]:
        return [p.to_dict() for p in self.profiles.values()]

    def register_profile(self, profile: ProxyProfileConfig) -> None:
        self.profiles[profile.profile_id] = profile

    # --------------------------------------------------------------------------
    # Proxy Generation & Lifecycle
    # --------------------------------------------------------------------------

    def generate_proxy_for_asset(
        self,
        asset: MediaAsset,
        profile_id: str = "profile_720p",
        output_dir: Optional[str] = None,
    ) -> ProxyMediaRecord:
        """Triggers synchronous proxy generation, updates asset state, and stores record."""
        profile = self.get_profile(profile_id)
        if not profile:
            raise ValueError(f"Unknown proxy profile '{profile_id}'.")

        record = self.proxy_engine.generate_proxy(asset, profile, output_dir=output_dir)
        self.records[record.proxy_id] = record
        self.asset_proxies[asset.asset_id] = record.proxy_id

        # Update MediaAsset proxy metadata
        asset.proxy_location = record.file_path
        asset.proxy_info = {
            "proxy_id": record.proxy_id,
            "profile_id": profile.profile_id,
            "status": record.status.value,
            "proxy_width": record.width,
            "proxy_height": record.height,
            "proxy_size_bytes": record.proxy_size_bytes,
            "proxy_fingerprint": record.proxy_fingerprint,
            "generated_at": record.verified_at or record.created_at,
        }

        # Update ProjectMediaLibrary
        pml = media_library_registry.get_or_create(asset.project_id)
        pml.add_asset(asset)

        return record

    def get_proxy_for_asset(self, asset_id: str) -> Optional[ProxyMediaRecord]:
        proxy_id = self.asset_proxies.get(asset_id)
        if proxy_id:
            return self.records.get(proxy_id)
        return None

    def list_proxies_for_project(self, project_id: str) -> List[Dict[str, Any]]:
        return [
            rec.to_dict()
            for rec in self.records.values()
            if rec.project_id == project_id
        ]

    # --------------------------------------------------------------------------
    # Source Resolution (Playback & Export)
    # --------------------------------------------------------------------------

    def resolve_source_for_playback(
        self,
        asset: MediaAsset,
        mode: PlaybackSourceMode = PlaybackSourceMode.AUTOMATIC,
    ) -> Tuple[str, bool]:
        """Resolves the file path to decode for playback.
        Returns: (file_path, is_proxy)
        """
        proxy_rec = self.get_proxy_for_asset(asset.asset_id)
        has_ready_proxy = (
            proxy_rec is not None
            and proxy_rec.status == ProxyLifecycleStatus.READY
            and os.path.exists(proxy_rec.file_path)
        )

        orig_path = asset.file_location
        orig_exists = os.path.exists(orig_path)

        if mode == PlaybackSourceMode.ORIGINAL:
            if not orig_exists:
                raise FileNotFoundError(f"Original media for asset '{asset.asset_id}' is missing at '{orig_path}'.")
            return orig_path, False

        elif mode == PlaybackSourceMode.PROXY:
            if not has_ready_proxy:
                raise FileNotFoundError(f"Ready proxy for asset '{asset.asset_id}' does not exist.")
            return proxy_rec.file_path, True

        elif mode == PlaybackSourceMode.PREFER_PROXY:
            if has_ready_proxy:
                return proxy_rec.file_path, True
            if orig_exists:
                return orig_path, False
            raise FileNotFoundError(f"Neither proxy nor original media available for asset '{asset.asset_id}'.")

        else: # AUTOMATIC
            # Use proxy if high-res (>= 1080p) or large filesize, and proxy is available
            w = asset.width or (asset.video_streams[0].width if asset.video_streams else 0)
            is_high_res = w >= 1920 or asset.size_bytes > 50_000_000
            if is_high_res and has_ready_proxy:
                return proxy_rec.file_path, True
            if orig_exists:
                return orig_path, False
            if has_ready_proxy:
                return proxy_rec.file_path, True
            raise FileNotFoundError(f"Media asset '{asset.asset_id}' has neither original nor proxy available.")

    def resolve_source_for_export(
        self,
        asset: MediaAsset,
        policy: ExportSourcePolicy = ExportSourcePolicy.ORIGINALS_ONLY,
    ) -> Tuple[str, bool]:
        """Resolves the file path for final export rendering.
        Under ORIGINALS_ONLY, strictly fails if the original is missing.
        Returns: (file_path, is_proxy)
        """
        orig_path = asset.file_location
        orig_exists = os.path.exists(orig_path)

        if policy == ExportSourcePolicy.ORIGINALS_ONLY:
            if not orig_exists:
                raise RuntimeError(
                    f"Export failed: original media asset '{asset.asset_id}' is missing at '{orig_path}'. "
                    f"Export policy is strict ORIGINALS_ONLY; proxies cannot be silently substituted."
                )
            return orig_path, False

        elif policy == ExportSourcePolicy.PROXIES_ALLOWED:
            if orig_exists:
                return orig_path, False
            proxy_rec = self.get_proxy_for_asset(asset.asset_id)
            if proxy_rec and proxy_rec.status == ProxyLifecycleStatus.READY and os.path.exists(proxy_rec.file_path):
                logger.warning(f"Using proxy for export of asset '{asset.asset_id}' under PROXIES_ALLOWED policy.")
                return proxy_rec.file_path, True
            raise RuntimeError(f"Export failed: neither original nor proxy available for '{asset.asset_id}'.")

        else: # AUTOMATIC
            if orig_exists:
                return orig_path, False
            raise RuntimeError(
                f"Export policy AUTOMATIC defaulted to original requirement: asset '{asset.asset_id}' original missing."
            )

    # --------------------------------------------------------------------------
    # Missing Media & Relinking
    # --------------------------------------------------------------------------

    def audit_project_media(self, project_id: str) -> Dict[str, Any]:
        """Inspects all assets in a project to identify missing, relinked, and proxy states."""
        pml = media_library_registry.get_or_create(project_id)
        assets = pml.list_assets()

        total = len(assets)
        online = 0
        missing = []
        has_proxy = 0

        for asset in assets:
            if os.path.exists(asset.file_location):
                online += 1
            else:
                missing.append(asset.to_dict())

            if asset.asset_id in self.asset_proxies:
                has_proxy += 1

        return {
            "project_id": project_id,
            "total_assets": total,
            "online_assets": online,
            "missing_assets_count": len(missing),
            "missing_assets": missing,
            "proxies_count": has_proxy,
        }

    def scan_for_relink_candidates(
        self,
        asset: MediaAsset,
        search_roots: List[str],
        max_results: int = 5,
    ) -> List[RelinkCandidate]:
        return self.relinking_engine.find_candidates_for_asset(
            asset=asset,
            search_roots=search_roots,
            max_results=max_results,
        )

    def relink_asset(
        self,
        asset: MediaAsset,
        new_file_path: str,
    ) -> RelinkResult:
        result = self.relinking_engine.relink_asset(asset, new_file_path)
        if result.is_success:
            # Recheck proxy status if one exists
            proxy_rec = self.get_proxy_for_asset(asset.asset_id)
            if proxy_rec:
                # If original changed, proxy might be stale
                if proxy_rec.original_fingerprint and asset.content_hash_sha256 != proxy_rec.original_fingerprint:
                    proxy_rec.status = ProxyLifecycleStatus.STALE
                    logger.info(f"Marked proxy '{proxy_rec.proxy_id}' as STALE after asset relink.")
        return result


# Global singleton instance
proxy_service = ProxyService()
