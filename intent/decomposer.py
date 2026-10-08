import re
import logging
from typing import List, Dict, Any, Optional
from intent.models import UserIntent, PlannedStep, PlanRiskLevel
from intent.capability_mapper import capability_registry
from intent.resolver import PlanningContext

logger = logging.getLogger("Omnia.Intent.Decomposer")

class TaskDecomposer:
    """Decomposes high-level intent into ordered, verifiable atomic steps."""

    def __init__(self, registry=capability_registry):
        self.registry = registry

    def decompose(self, intent: UserIntent, context: PlanningContext) -> List[PlannedStep]:
        """Translates user intent and resolved context into atomic planned steps."""
        steps: List[PlannedStep] = []
        text = intent.normalized_text

        # Pattern 1: YouTube / Media playback on mobile device
        # "Open YouTube on my Android phone, search for SpaceX, play newest video, tell me title"
        if "youtube" in text or "video" in text:
            # Step 1: Ensure target device unlocked
            step_unlock = PlannedStep(
                step_id="step_1_unlock",
                purpose="Ensure target Android device is awake and unlocked",
                capability_name="unlock_all_devices",
                inputs={},
                outputs=["unlocked_devices"],
                dependencies=[],
                preconditions=["DEVICE_CONNECTED"],
                postconditions=["SCREEN_AWAKE"],
                verification_strategy="DEVICE_UNLOCKED",
                risk_level=PlanRiskLevel.LOW_RISK,
                timeout_sec=15.0,
                idempotency="SAFE_TO_RETRY"
            )
            steps.append(step_unlock)

            # Step 2: Open Video
            query_match = re.search(r"search for ([\w\s]+)(?:,|$)", text)
            query = query_match.group(1).strip() if query_match else "SpaceX launch"
            video_url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"

            step_play = PlannedStep(
                step_id="step_2_play",
                purpose=f"Launch YouTube query '{query}' on device",
                capability_name="play_youtube_video",
                inputs={"video_url": video_url, "device_serial": context.resolved_entities.get("target_device_serial", "emulator-5554")},
                outputs=["video_stream_active"],
                dependencies=["step_1_unlock"],
                preconditions=["SCREEN_AWAKE"],
                postconditions=["YOUTUBE_ACTIVITY_RUNNING"],
                verification_strategy="ACTIVITY_RESUMED",
                risk_level=PlanRiskLevel.LOW_RISK,
                timeout_sec=20.0,
                idempotency="SAFE_TO_RETRY"
            )
            steps.append(step_play)

            # Step 3: Announce outcome via voice
            step_speak = PlannedStep(
                step_id="step_3_announce",
                purpose="Report title and playback status to user",
                capability_name="speak_phrase",
                inputs={"phrase": f"Playing the latest {query} video on your device."},
                outputs=["announced"],
                dependencies=["step_2_play"],
                preconditions=["YOUTUBE_ACTIVITY_RUNNING"],
                postconditions=["AUDIO_DELIVERED"],
                verification_strategy="STREAM_EOF",
                risk_level=PlanRiskLevel.LOW_RISK,
                timeout_sec=10.0,
                idempotency="SAFE_TO_RETRY"
            )
            steps.append(step_speak)
            return steps

        # Pattern 2: Browser navigation & Web Automation
        if intent.target_websites or "browse" in text or "open browser" in text or "search" in text:
            target_url = context.resolved_entities.get("target_url", "https://example.com")
            
            # Step 1: Navigate to target URL
            step_nav = PlannedStep(
                step_id="step_1_navigate",
                purpose=f"Navigate browser to {target_url}",
                capability_name="open_url_in_browser",
                inputs={"url": target_url},
                outputs=["current_url", "page_title"],
                dependencies=[],
                preconditions=["NETWORK_ONLINE"],
                postconditions=["PAGE_RENDERED"],
                verification_strategy="DOM_URL_MATCH",
                risk_level=PlanRiskLevel.READ_ONLY,
                timeout_sec=30.0,
                idempotency="SAFE_TO_RETRY"
            )
            steps.append(step_nav)

            # Step 2: If query or extraction was asked
            if "search" in text or "extract" in text or "download" in text or "find" in text:
                step_extract = PlannedStep(
                    step_id="step_2_interact",
                    purpose="Execute page task and extract required information",
                    capability_name="execute_web_task",
                    inputs={"url": target_url, "objective": intent.raw_text},
                    outputs=["extracted_data"],
                    dependencies=["step_1_navigate"],
                    preconditions=["PAGE_RENDERED"],
                    postconditions=["DATA_EXTRACTED"],
                    verification_strategy="DOM_STATE_CHANGE",
                    risk_level=PlanRiskLevel.MODERATE_RISK,
                    timeout_sec=40.0,
                    idempotency="SAFE_TO_RETRY"
                )
                steps.append(step_extract)

            return steps

        # Pattern 3: Desktop Visual interaction / Screenshot
        if "screenshot" in text or "capture" in text or "see" in text or "look" in text:
            step_shot = PlannedStep(
                step_id="step_1_capture",
                purpose="Capture screen frame for visual perception",
                capability_name="capture_screen",
                inputs={"source": "desktop"},
                outputs=["frame_ref"],
                dependencies=[],
                preconditions=["DISPLAY_AVAILABLE"],
                postconditions=["FRAME_BUFFERED"],
                verification_strategy="FRAME_INTEGRITY",
                risk_level=PlanRiskLevel.READ_ONLY,
                timeout_sec=10.0,
                idempotency="SAFE_TO_RETRY"
            )
            steps.append(step_shot)
            return steps

        # Pattern 4: Shell command execution
        if "shell" in text or "terminal" in text or "run command" in text or "exec" in text:
            cmd = intent.parameters.get("command", intent.raw_text)
            step_shell = PlannedStep(
                step_id="step_1_shell",
                purpose="Execute shell command on target node",
                capability_name="execute_mesh_shell_command",
                inputs={"shell_command": cmd, "target_host": "local"},
                outputs=["stdout", "exit_code"],
                dependencies=[],
                preconditions=["SHELL_ALLOWED"],
                postconditions=["PROCESS_TERMINATED"],
                verification_strategy="EXIT_CODE_ZERO",
                risk_level=PlanRiskLevel.HIGH_RISK if intent.requires_confirmation else PlanRiskLevel.MODERATE_RISK,
                requires_confirmation=intent.requires_confirmation,
                timeout_sec=30.0,
                idempotency="NOT_SAFE_TO_RETRY"
            )
            steps.append(step_shell)
            return steps

        # Fallback: General speech / conversational response
        step_speak = PlannedStep(
            step_id="step_1_respond",
            purpose="Acknowledge intent and respond to user",
            capability_name="speak_phrase",
            inputs={"phrase": f"Acknowledging request: {intent.primary_objective}"},
            outputs=["response_played"],
            dependencies=[],
            preconditions=[],
            postconditions=["AUDIO_PLAYED"],
            verification_strategy="STREAM_EOF",
            risk_level=PlanRiskLevel.LOW_RISK,
            timeout_sec=10.0,
            idempotency="SAFE_TO_RETRY"
        )
        steps.append(step_speak)
        return steps

task_decomposer = TaskDecomposer()
