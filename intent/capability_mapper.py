import logging
from typing import Dict, List, Optional
from intent.models import CapabilityMetadata, PlanRiskLevel

logger = logging.getLogger("Omnia.Intent.CapabilityMapper")

class CapabilityRegistry:
    """Discovers and exposes execution capabilities mapped from omnia_tools."""

    def __init__(self):
        self._capabilities: Dict[str, CapabilityMetadata] = {}
        self._register_default_capabilities()

    def _register_default_capabilities(self):
        # 1. Browser capabilities
        self.register(CapabilityMetadata(
            name="open_url_in_browser",
            description="Navigates the autonomous browser to an explicit URL",
            supported_environments=["browser", "desktop"],
            required_resources=["browser:session"],
            risk_level=PlanRiskLevel.READ_ONLY,
            idempotent=True,
            reversibility=True,
            verification_mechanism="DOM_URL_MATCH",
            timeout_sec=30.0,
            input_keys=["url"],
            output_keys=["final_url", "page_title"]
        ))
        self.register(CapabilityMetadata(
            name="execute_web_task",
            description="Performs an automated multistep browser interaction",
            supported_environments=["browser"],
            required_resources=["browser:session"],
            risk_level=PlanRiskLevel.MODERATE_RISK,
            idempotent=False,
            reversibility=False,
            verification_mechanism="DOM_STATE_CHANGE",
            timeout_sec=45.0,
            input_keys=["url", "objective"],
            output_keys=["task_result"]
        ))

        # 2. Vision & Screen capabilities
        self.register(CapabilityMetadata(
            name="capture_screen",
            description="Captures current desktop or active Android screen",
            supported_environments=["desktop", "android"],
            required_resources=["display:screen"],
            risk_level=PlanRiskLevel.READ_ONLY,
            idempotent=True,
            reversibility=True,
            verification_mechanism="FRAME_INTEGRITY",
            timeout_sec=10.0,
            input_keys=["source"],
            output_keys=["frame_width", "frame_height", "frame_ref"]
        ))
        self.register(CapabilityMetadata(
            name="find_visual_element",
            description="Locates button or label on screen via multimodal OCR/grounding",
            supported_environments=["desktop", "android", "browser"],
            required_resources=["display:screen"],
            risk_level=PlanRiskLevel.READ_ONLY,
            idempotent=True,
            reversibility=True,
            verification_mechanism="ELEMENT_CONFIDENCE",
            timeout_sec=15.0,
            input_keys=["target_description"],
            output_keys=["matched_label", "confidence", "coordinates"]
        ))
        self.register(CapabilityMetadata(
            name="click_visual_element",
            description="Locates target visually and executes physical/virtual click",
            supported_environments=["desktop", "android", "browser"],
            required_resources=["desktop:mouse", "display:screen"],
            risk_level=PlanRiskLevel.MODERATE_RISK,
            idempotent=False,
            reversibility=False,
            verification_mechanism="VISUAL_DIFF_VERIFIED",
            timeout_sec=20.0,
            input_keys=["target_description", "expected_transition"],
            output_keys=["click_success", "verified"]
        ))
        self.register(CapabilityMetadata(
            name="verify_visual_state",
            description="Inspects screen to confirm expected text or state transition",
            supported_environments=["desktop", "android", "browser"],
            required_resources=["display:screen"],
            risk_level=PlanRiskLevel.READ_ONLY,
            idempotent=True,
            reversibility=True,
            verification_mechanism="VISUAL_DIFF_VERIFIED",
            timeout_sec=15.0,
            input_keys=["expected_text", "should_appear"],
            output_keys=["verified_status", "confidence"]
        ))

        # 3. Audio & Speech
        self.register(CapabilityMetadata(
            name="speak_phrase",
            description="Plays spoken audio response over workstation or telephony",
            supported_environments=["audio", "desktop"],
            required_resources=["audio:playback_stream"],
            risk_level=PlanRiskLevel.LOW_RISK,
            idempotent=True,
            reversibility=True,
            verification_mechanism="STREAM_EOF",
            timeout_sec=15.0,
            input_keys=["phrase"],
            output_keys=["playback_duration"]
        ))

        # 4. Device & Mesh capabilities
        self.register(CapabilityMetadata(
            name="unlock_all_devices",
            description="Dispatches wake and keyevent 82 unlock to connected ADB devices",
            supported_environments=["android"],
            required_resources=["adb:device_mesh"],
            risk_level=PlanRiskLevel.LOW_RISK,
            idempotent=True,
            reversibility=False,
            verification_mechanism="SCREEN_ON_VERIFIED",
            timeout_sec=15.0,
            input_keys=[],
            output_keys=["unlocked_devices"]
        ))
        self.register(CapabilityMetadata(
            name="play_youtube_video",
            description="Launches specific YouTube video on ADB Android target",
            supported_environments=["android"],
            required_resources=["adb:device"],
            risk_level=PlanRiskLevel.LOW_RISK,
            idempotent=True,
            reversibility=False,
            verification_mechanism="ACTIVITY_RESUMED",
            timeout_sec=20.0,
            input_keys=["video_url", "device_serial"],
            output_keys=["intent_dispatched"]
        ))
        self.register(CapabilityMetadata(
            name="execute_mesh_shell_command",
            description="Executes a CLI command across local host or remote mesh node",
            supported_environments=["shell", "mesh"],
            required_resources=["shell:process"],
            risk_level=PlanRiskLevel.HIGH_RISK,
            idempotent=False,
            reversibility=False,
            verification_mechanism="EXIT_CODE_ZERO",
            timeout_sec=30.0,
            input_keys=["shell_command", "target_host"],
            output_keys=["stdout", "exit_code"]
        ))

        # 5. Semantic Memory
        self.register(CapabilityMetadata(
            name="search_recent_web_context",
            description="Queries ChromaDB vector store for past browsing snippets",
            supported_environments=["memory"],
            required_resources=[],
            risk_level=PlanRiskLevel.READ_ONLY,
            idempotent=True,
            reversibility=True,
            verification_mechanism="HITS_RETURNED",
            timeout_sec=10.0,
            input_keys=["query"],
            output_keys=["context_matches"]
        ))

    def register(self, capability: CapabilityMetadata):
        self._capabilities[capability.name] = capability

    def get_capability(self, name: str) -> Optional[CapabilityMetadata]:
        return self._capabilities.get(name)

    def find_capability_for_action(self, action_verb: str, target: str) -> Optional[CapabilityMetadata]:
        """Matches intent action and target to best registered capability."""
        v = action_verb.lower()
        t = target.lower()

        if "browse" in v or "navigate" in v or "open url" in v or "http" in t or "website" in t or "web" in t:
            if "task" in v or "click" in v or "search and" in v:
                return self.get_capability("execute_web_task")
            return self.get_capability("open_url_in_browser")

        if "say" in v or "speak" in v or "tell" in v or "voice" in t:
            return self.get_capability("speak_phrase")

        if "click" in v or "press" in v or "tap" in v:
            return self.get_capability("click_visual_element")

        if "screenshot" in v or "capture" in v or "see" in v:
            return self.get_capability("capture_screen")

        if "find" in v or "locate" in v or "search screen" in v:
            return self.get_capability("find_visual_element")

        if "verify" in v or "check" in v or "confirm" in v:
            return self.get_capability("verify_visual_state")

        if "shell" in v or "run command" in v or "terminal" in v or "exec" in v:
            return self.get_capability("execute_mesh_shell_command")

        if "youtube" in t or "video" in t:
            return self.get_capability("play_youtube_video")

        if "unlock" in v and "device" in t:
            return self.get_capability("unlock_all_devices")

        if "remember" in v or "search history" in v:
            return self.get_capability("search_recent_web_context")

        return None

    def list_all(self) -> List[CapabilityMetadata]:
        return list(self._capabilities.values())

    def list_capabilities(self) -> List[CapabilityMetadata]:
        return self.list_all()

capability_registry = CapabilityRegistry()
capability_mapper = capability_registry
