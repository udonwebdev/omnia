"""OMNIA Video Studio — Module 1: Capability Registry & Feature Gating System.

The authoritative registry and runtime availability engine for OMNIA Video Studio capabilities.
Provides:
- register() / unregister() / get() / list()
- is_enabled() / is_available() / is_ready()
- Feature gating evaluated at runtime against configuration, platform, hardware, and dependencies
- Circular dependency detection and resolution
- Provider abstraction management
- Structured health evaluations
- Thread-safe, non-destructive, isolated operation
"""

import re
import logging
import time
from typing import Dict, List, Optional, Tuple, Set, Any

from video_studio.registry_models import (
    VideoStudioCategory,
    VideoStudioCapabilityStatus,
    ImplementationState,
    VideoStudioCapabilityDescriptor,
    CapabilityProviderDescriptor,
    CapabilityDependency,
    CapabilityHealthReport,
    HardwareRequirements,
    PlatformRequirements,
    AIRequirements,
    AccelerationAPI,
)
from video_studio.hardware import VideoStudioHardwareDetector

logger = logging.getLogger("Omnia.VideoStudio.Registry")

class VideoStudioCapabilityRegistry:
    """Central authoritative Capability Registry for Video Studio."""

    def __init__(self):
        self._capabilities: Dict[str, VideoStudioCapabilityDescriptor] = {}
        self._auth_tokens: Set[str] = {"core", "omnia_internal", "video_studio_internal"}
        self._hardware_profile = VideoStudioHardwareDetector.get_complete_hardware_profile()
        self._cached_health: Dict[str, CapabilityHealthReport] = {}

    def refresh_hardware_profile(self) -> Dict[str, Any]:
        """Refreshes detected hardware and compute capabilities."""
        self._hardware_profile = VideoStudioHardwareDetector.get_complete_hardware_profile()
        self._cached_health.clear()
        return self._hardware_profile

    # ==========================================================================
    # 1. Registration & Management
    # ==========================================================================

    def register(self, capability: VideoStudioCapabilityDescriptor, auth_token: str = "core") -> Tuple[bool, str]:
        """Registers a Video Studio capability with strict security, identity, and schema validation."""
        # 1. Authorization check
        if auth_token not in self._auth_tokens:
            msg = f"SECURITY_REJECTION: Untrusted authorization token '{auth_token}' cannot register '{capability.id}'."
            logger.warning(msg)
            return False, msg

        # 2. Identity format validation (dot-separated syntax e.g., 'video.timeline.multitrack')
        if not re.match(r"^[a-z0-9_\-]+(\.[a-z0-9_\-]+)+$", capability.id):
            msg = f"SCHEMA_REJECTION: Invalid capability ID format '{capability.id}'. Expected dot notation (e.g. 'video.timeline.multitrack')."
            logger.error(msg)
            return False, msg

        # 3. Duplicate check
        if capability.id in self._capabilities:
            existing = self._capabilities[capability.id]
            if existing.version == capability.version:
                msg = f"CONFLICT_REJECTION: Capability '{capability.id}' version '{capability.version}' is already registered."
                logger.warning(msg)
                return False, msg

        # 4. Circular dependency check
        circular = self._detect_circular_dependency(capability.id, capability.dependencies)
        if circular:
            msg = f"CIRCULAR_DEPENDENCY_REJECTION: Registering '{capability.id}' introduces dependency cycle: {' -> '.join(circular)}"
            logger.error(msg)
            return False, msg

        capability.updated_at = time.time()
        self._capabilities[capability.id] = capability
        self._cached_health.pop(capability.id, None)

        logger.info(f"Registered VideoStudio capability: {capability.id} [{capability.category.value}] (State: {capability.implementation_state.value})")
        return True, "REGISTERED"

    def unregister(self, capability_id: str, auth_token: str = "core") -> Tuple[bool, str]:
        """Unregisters a capability safely."""
        if auth_token not in self._auth_tokens:
            return False, "SECURITY_REJECTION"

        if capability_id not in self._capabilities:
            return False, f"NOT_FOUND: Capability '{capability_id}' is not registered."

        # Check if downstream capabilities depend on this capability
        dependents = [c.id for c in self._capabilities.values() if any(d.dependency_id == capability_id and not d.is_optional for d in c.dependencies)]
        if dependents:
            msg = f"DEPENDENCY_BLOCKED: Cannot unregister '{capability_id}'; required by: {dependents}"
            logger.warning(msg)
            return False, msg

        del self._capabilities[capability_id]
        self._cached_health.pop(capability_id, None)
        return True, "UNREGISTERED"

    def get(self, capability_id: str) -> Optional[VideoStudioCapabilityDescriptor]:
        """Retrieves a registered capability descriptor."""
        return self._capabilities.get(capability_id)

    # ==========================================================================
    # 2. Query & Filter APIs
    # ==========================================================================

    def list(
        self,
        category: Optional[VideoStudioCategory] = None,
        implementation_state: Optional[ImplementationState] = None,
        tag: Optional[str] = None
    ) -> List[VideoStudioCapabilityDescriptor]:
        """Lists capabilities filtered by category, implementation state, or tag."""
        res = list(self._capabilities.values())
        if category is not None:
            res = [c for c in res if c.category == category]
        if implementation_state is not None:
            res = [c for c in res if c.implementation_state == implementation_state]
        if tag is not None:
            res = [c for c in res if tag in c.tags]
        return res

    def list_available(self) -> List[VideoStudioCapabilityDescriptor]:
        """Lists capabilities that are currently implemented, enabled, and satisfy all dependencies and hardware."""
        return [c for c in self._capabilities.values() if self.is_available(c.id)]

    def list_enabled(self) -> List[VideoStudioCapabilityDescriptor]:
        """Lists capabilities that are enabled by configuration and flag."""
        return [c for c in self._capabilities.values() if self.is_enabled(c.id)]

    def list_experimental(self) -> List[VideoStudioCapabilityDescriptor]:
        """Lists experimental capabilities."""
        return [c for c in self._capabilities.values() if c.experimental or c.implementation_state == ImplementationState.EXPERIMENTAL]

    # ==========================================================================
    # 3. Feature Gating & Runtime Availability
    # ==========================================================================

    def is_enabled(self, capability_id: str, check_subsystem_master: bool = False) -> bool:
        """Evaluates whether a capability is enabled according to descriptor and configuration."""
        cap = self.get(capability_id)
        if not cap:
            return False
        if not cap.enabled:
            return False

        try:
            from config import config_control_plane
            if check_subsystem_master:
                subsystem_enabled = config_control_plane.resolve_effective_value("video_studio.enabled")
                if subsystem_enabled is not None and not subsystem_enabled:
                    return False

            # If capability is experimental, check if experimental features are permitted
            if cap.experimental or cap.implementation_state == ImplementationState.EXPERIMENTAL:
                exp_enabled = config_control_plane.resolve_effective_value("video_studio.experimental")
                if exp_enabled is not None and not exp_enabled:
                    return False

            # Check specific configuration keys
            for ck in cap.configuration_keys:
                cval = config_control_plane.resolve_effective_value(ck)
                if cval is not None and not cval:
                    return False
        except Exception:
            pass

        return True

    def is_available(self, capability_id: str) -> bool:
        """Evaluates whether a capability is ready for execution (implemented, platform/hardware satisfied, dependencies available).
        Independent of whether the feature toggle is currently enabled.
        """
        cap = self.get(capability_id)
        if not cap:
            return False

        # Roadmap rule: PLANNED capabilities are NOT implemented yet
        if cap.implementation_state == ImplementationState.PLANNED:
            return False

        health = self.get_health(capability_id)
        return health.status in [VideoStudioCapabilityStatus.AVAILABLE, VideoStudioCapabilityStatus.READY, VideoStudioCapabilityStatus.EXPERIMENTAL]

    def is_ready(self, capability_id: str) -> bool:
        """Evaluates whether a capability is both enabled AND available for active execution."""
        return self.is_enabled(capability_id) and self.is_available(capability_id)

    def get_status(self, capability_id: str) -> VideoStudioCapabilityStatus:
        """Returns the evaluated runtime status of a capability.
        Distinguishes:
        - UNREGISTERED: not registered
        - REGISTERED: planned roadmap capability (not implemented)
        - UNAVAILABLE: implemented, but hardware or dependencies missing
        - DISABLED: available/implemented, but toggled off by configuration
        - AVAILABLE: implemented, enabled, and ready
        - EXPERIMENTAL: operational under experimental mode
        """
        cap = self.get(capability_id)
        if not cap:
            return VideoStudioCapabilityStatus.UNREGISTERED

        if cap.implementation_state == ImplementationState.PLANNED:
            return VideoStudioCapabilityStatus.REGISTERED

        health = self.get_health(capability_id)
        if health.status == VideoStudioCapabilityStatus.UNAVAILABLE:
            return VideoStudioCapabilityStatus.UNAVAILABLE

        if not self.is_enabled(capability_id):
            return VideoStudioCapabilityStatus.DISABLED

        return health.status

    # ==========================================================================
    # 4. Dependency & Hardware Health Evaluation
    # ==========================================================================

    def get_health(self, capability_id: str) -> CapabilityHealthReport:
        """Performs structured diagnostic health check on a capability and its dependencies."""
        if capability_id in self._cached_health:
            return self._cached_health[capability_id]

        cap = self.get(capability_id)
        if not cap:
            return CapabilityHealthReport(
                capability_id=capability_id,
                is_healthy=False,
                status=VideoStudioCapabilityStatus.UNREGISTERED,
                reason="Capability not found in registry."
            )

        failed_deps: List[str] = []
        hw_shortfalls: List[str] = []

        # 1. Platform & Architecture Check
        plat = self._hardware_profile["platform"]
        if not cap.platform_requirements.is_supported(plat["os"], plat["architecture"]):
            rep = CapabilityHealthReport(
                capability_id=capability_id,
                is_healthy=False,
                status=VideoStudioCapabilityStatus.UNAVAILABLE,
                reason=f"Current platform '{plat['os']} ({plat['architecture']})' is not supported."
            )
            self._cached_health[capability_id] = rep
            return rep

        # 2. Hardware Resource Checks
        res = self._hardware_profile["resources"]
        hw = cap.hardware_requirements

        if res["ram_total_mb"] < hw.min_ram_mb:
            hw_shortfalls.append(f"RAM {res['ram_total_mb']}MB < required {hw.min_ram_mb}MB")

        if res["disk_free_mb"] < hw.min_disk_space_mb:
            hw_shortfalls.append(f"Disk {res['disk_free_mb']}MB < required {hw.min_disk_space_mb}MB")

        if hw.requires_gpu and not self._hardware_profile["has_gpu_acceleration"]:
            hw_shortfalls.append("Requires GPU hardware acceleration which is unavailable.")

        # Check required acceleration APIs
        avail_acc = self._hardware_profile["acceleration"]
        for req_acc in hw.required_acceleration:
            if req_acc.value not in avail_acc:
                hw_shortfalls.append(f"Requires acceleration API '{req_acc.value}', not detected on host.")

        # 3. Dependencies Check
        for dep in cap.dependencies:
            dep_cap = self.get(dep.dependency_id)
            if not dep_cap:
                if not dep.is_optional:
                    failed_deps.append(f"Missing required dependency: '{dep.dependency_id}'")
                continue

            # Version check
            if dep.min_version and not self._is_version_compatible(dep_cap.version, min_ver=dep.min_version):
                failed_deps.append(f"Dependency '{dep.dependency_id}' version {dep_cap.version} < required min {dep.min_version}")
            if dep.max_version and not self._is_version_compatible(dep_cap.version, max_ver=dep.max_version):
                failed_deps.append(f"Dependency '{dep.dependency_id}' version {dep_cap.version} > required max {dep.max_version}")

            # If dependency is required but not ready/implemented
            if not dep.is_optional and dep_cap.implementation_state == ImplementationState.PLANNED:
                failed_deps.append(f"Required dependency '{dep.dependency_id}' is not yet implemented.")

        # Formulate health verdict
        if hw_shortfalls or failed_deps:
            status = VideoStudioCapabilityStatus.UNAVAILABLE
            is_healthy = False
            reasons = []
            if hw_shortfalls:
                reasons.append(f"Hardware shortfalls: {'; '.join(hw_shortfalls)}")
            if failed_deps:
                reasons.append(f"Dependency issues: {'; '.join(failed_deps)}")
            reason = " | ".join(reasons)
            recovery = "Install required acceleration drivers or fulfill dependent capabilities."
        elif cap.experimental or cap.implementation_state == ImplementationState.EXPERIMENTAL:
            status = VideoStudioCapabilityStatus.EXPERIMENTAL
            is_healthy = True
            reason = "Operational in experimental mode."
            recovery = None
        elif cap.implementation_state == ImplementationState.PLANNED:
            status = VideoStudioCapabilityStatus.REGISTERED
            is_healthy = True
            reason = "Cataloged roadmap capability (pending module implementation)."
            recovery = None
        else:
            status = VideoStudioCapabilityStatus.AVAILABLE
            is_healthy = True
            reason = "All dependencies and hardware constraints satisfied."
            recovery = None

        rep = CapabilityHealthReport(
            capability_id=capability_id,
            is_healthy=is_healthy,
            status=status,
            reason=reason,
            recovery_suggestion=recovery,
            failed_dependencies=failed_deps,
            hardware_shortfalls=hw_shortfalls
        )
        self._cached_health[capability_id] = rep
        return rep

    # ==========================================================================
    # 5. Providers Management
    # ==========================================================================

    def register_provider(self, capability_id: str, provider: CapabilityProviderDescriptor) -> bool:
        """Registers an implementation provider for a capability."""
        cap = self.get(capability_id)
        if not cap:
            return False
        cap.providers[provider.provider_id] = provider
        if cap.active_provider_id is None or provider.priority < cap.providers[cap.active_provider_id].priority:
            cap.active_provider_id = provider.provider_id
        self._cached_health.pop(capability_id, None)
        return True

    def get_active_provider(self, capability_id: str) -> Optional[CapabilityProviderDescriptor]:
        """Resolves the highest-priority available provider for a capability."""
        cap = self.get(capability_id)
        if not cap or not cap.providers:
            return None
        available = [p for p in cap.providers.values() if p.is_available]
        if not available:
            return None
        available.sort(key=lambda x: x.priority)
        return available[0]

    # ==========================================================================
    # 6. Helper & Graph Algorithms
    # ==========================================================================

    def _detect_circular_dependency(self, start_id: str, direct_deps: List[CapabilityDependency]) -> Optional[List[str]]:
        """Detects if adding this capability introduces a directed cycle in dependencies."""
        visited = set()

        def dfs(current: str, path: List[str]) -> Optional[List[str]]:
            if current == start_id:
                return path + [current]
            if current in visited:
                return None
            visited.add(current)
            c = self.get(current)
            if not c:
                return None
            for d in c.dependencies:
                res = dfs(d.dependency_id, path + [current])
                if res:
                    return res
            return None

        for dep in direct_deps:
            cycle = dfs(dep.dependency_id, [start_id])
            if cycle:
                return cycle
        return None

    @staticmethod
    def _is_version_compatible(version_str: str, min_ver: Optional[str] = None, max_ver: Optional[str] = None) -> bool:
        """Compares semantic versions tuple-wise (e.g. 1.2.0 >= 1.0.0)."""
        def parse_v(v: str) -> Tuple[int, ...]:
            parts = re.findall(r"\d+", v)
            return tuple(int(p) for p in parts) if parts else (0,)

        v_tuple = parse_v(version_str)
        if min_ver and v_tuple < parse_v(min_ver):
            return False
        if max_ver and v_tuple > parse_v(max_ver):
            return False
        return True

# Authoritative global singleton
video_studio_capability_registry = VideoStudioCapabilityRegistry()
