import time
import asyncio
import logging
from typing import Optional, Dict, Any, List

from vision.models import (
    VisionSource,
    VisionFrame,
    VisionObservation,
    VisionElement,
    GroundingCandidate,
    VisionVerification,
    VerificationStatus,
    VisionRecoveryRequest,
    BoundingBox
)
from vision.capture import capture_engine
from vision.perception import perception_engine
from vision.grounding import grounding_engine
from vision.verification import verification_engine
from vision.comparison import diff_engine
from audit_logger import audit_logger
from policy_engine import policy_engine

logger = logging.getLogger("Omnia.Vision.Engine")

BUS_STATE_URL = "http://127.0.0.1:8000/api/state"

class OmniaVisionEngine:
    """Master Multimodal Vision & Visual Computer Use Subsystem for Omnia."""

    def __init__(self):
        self.last_frame: Optional[VisionFrame] = None
        self.last_observation: Optional[VisionObservation] = None

    async def _notify_hud(self, state: str, message: str):
        """Sends lightweight state update to the HUD bus."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=0.5) as client:
                await client.post(BUS_STATE_URL, json={"state": state, "message": message})
        except Exception:
            pass

    async def capture(self, source: VisionSource = VisionSource.DESKTOP, target_id: Optional[str] = None) -> VisionFrame:
        """Captures a validated screen frame from the specified surface."""
        await self._notify_hud("VISION_CAPTURE", f"Capturing from {source.value}")
        audit_logger.log_event("vision_capture_started", {"source": source.value, "target_id": target_id}, allowed=True, outcome="Started")

        try:
            if source == VisionSource.DESKTOP:
                frame = await capture_engine.capture_desktop()
            elif source == VisionSource.ANDROID:
                frame = await capture_engine.capture_android(serial=target_id)
            elif source == VisionSource.BROWSER:
                frame = await capture_engine.capture_browser()
            else:
                raise ValueError(f"Unknown vision source: {source}")

            self.last_frame = frame
            audit_logger.log_event("vision_capture_completed", {
                "frame_id": frame.frame_id,
                "source": source.value,
                "dimensions": f"{frame.width}x{frame.height}",
                "duration_ms": frame.capture_duration_ms
            }, allowed=True, outcome="Success")
            return frame

        except Exception as e:
            audit_logger.log_event("vision_capture_failed", {"source": source.value, "error": str(e)}, allowed=True, outcome="Failed")
            await self._notify_hud("VISION_FAILED", f"Capture failed: {str(e)[:40]}")
            raise

    async def observe(self, frame: Optional[VisionFrame] = None, source: VisionSource = VisionSource.DESKTOP) -> VisionObservation:
        """Analyzes a frame or captures a new one and extracts visual elements."""
        if frame is None:
            frame = await self.capture(source=source)

        await self._notify_hud("VISION_ANALYZING", f"Analyzing frame {frame.frame_id[:8]}")
        t0 = time.perf_counter()
        
        observation = perception_engine.analyze_frame(frame)
        self.last_observation = observation
        
        analysis_ms = (time.perf_counter() - t0) * 1000
        audit_logger.log_event("vision_analysis_completed", {
            "frame_id": frame.frame_id,
            "element_count": len(observation.elements),
            "analysis_ms": analysis_ms
        }, allowed=True, outcome="Success")

        return observation

    async def locate(self, target_query: str, observation: Optional[VisionObservation] = None) -> Optional[GroundingCandidate]:
        """Locates and ranks the best visual element matching target_query."""
        if observation is None:
            observation = await self.observe()

        await self._notify_hud("VISION_LOCATING", f"Locating '{target_query}'")
        best = grounding_engine.ground_best(target_query, observation)

        if best:
            audit_logger.log_event("element_detected", {
                "query": target_query,
                "label": best.element.label,
                "confidence": best.score,
                "rank": best.rank
            }, allowed=True, outcome="Located")
        else:
            audit_logger.log_event("element_not_found", {"query": target_query}, allowed=True, outcome="Not Found")

        return best

    async def execute_visual_action(
        self,
        action_type: str,
        target_norm_coord: tuple, # (x, y) normalized [0.0, 1.0]
        source: VisionSource = VisionSource.DESKTOP,
        device_id: Optional[str] = None,
        text_input: Optional[str] = None
    ) -> Dict[str, Any]:
        """Applies governance check and dispatches low-level input to the target screen."""
        nx, ny = target_norm_coord
        
        # Policy verification
        audit_params = {
            "action": action_type,
            "target": [nx, ny],
            "source": source.value,
            "text": text_input
        }
        
        # Protect sensitive inputs from policy bypass
        if text_input and any(w in text_input.lower() for w in ["password", "cvv", "card"]):
            audit_logger.log_event("visual_action_blocked", audit_params, allowed=False, outcome="Blocked sensitive input")
            raise PermissionError("POLICY_REJECTION: Typing credentials or sensitive payment details is blocked.")

        await self._notify_hud("VISION_ACTING", f"{action_type.upper()} at ({nx:.2f}, {ny:.2f})")

        t0 = time.perf_counter()
        action_outcome = {}

        if source == VisionSource.DESKTOP:
            import pyautogui
            sw, sh = pyautogui.size()
            px, py = int(round(nx * sw)), int(round(ny * sh))

            if action_type == "click":
                pyautogui.click(px, py)
            elif action_type == "double_click":
                pyautogui.doubleClick(px, py)
            elif action_type == "type" and text_input:
                pyautogui.click(px, py)
                pyautogui.write(text_input, interval=0.05)
            action_outcome = {"pixel": (px, py), "status": "executed"}

        elif source == VisionSource.ANDROID:
            from device_controller import DeviceController
            ctl = DeviceController()
            if not ctl.devices:
                ctl.refresh_devices()
            if not ctl.devices:
                raise RuntimeError("DEVICE_NOT_FOUND: Cannot act on Android without active ADB.")

            target_dev = ctl.devices[0]
            if device_id:
                for dev in ctl.devices:
                    if dev.get_serial_no() == device_id:
                        target_dev = dev
                        break

            # Android display resolution
            # In practice, grab from last frame dimensions or fallback 1080x2400
            fw = self.last_frame.width if self.last_frame else 1080
            fh = self.last_frame.height if self.last_frame else 2400
            px, py = int(round(nx * fw)), int(round(ny * fh))

            if action_type == "click":
                cmd = f"input tap {px} {py}"
            elif action_type == "type" and text_input:
                cmd = f"input tap {px} {py} && input text '{text_input}'"
            else:
                cmd = f"input tap {px} {py}"

            res = target_dev.shell(cmd)
            action_outcome = {"pixel": (px, py), "output": res, "status": "executed"}

        elif source == VisionSource.BROWSER:
            from browser_driver import browser_driver
            if not browser_driver.active_page:
                raise RuntimeError("BROWSER_UNAVAILABLE: No active page to interact with.")
            
            # Use viewport dimensions for Playwright click
            vp = browser_driver.active_page.viewport_size or {"width": 1280, "height": 800}
            px = int(round(nx * vp["width"]))
            py = int(round(ny * vp["height"]))

            if action_type == "click":
                await browser_driver.active_page.mouse.click(px, py)
            elif action_type == "type" and text_input:
                await browser_driver.active_page.mouse.click(px, py)
                await browser_driver.active_page.keyboard.type(text_input)
            action_outcome = {"pixel": (px, py), "status": "executed"}

        elapsed_ms = (time.perf_counter() - t0) * 1000
        audit_logger.log_event("action_executed", {**audit_params, "duration_ms": elapsed_ms}, allowed=True, outcome="Success")
        return action_outcome

    async def observe_act_verify(
        self,
        target_description: str,
        expected_change: str,
        source: VisionSource = VisionSource.DESKTOP,
        action_type: str = "click",
        settle_delay_sec: float = 1.0
    ) -> Dict[str, Any]:
        """Executes the complete Observe -> Locate -> Act -> Observe -> Verify loop."""
        # 1. Capture Pre-Frame & Observe
        pre_frame = await self.capture(source=source)
        observation = await self.observe(frame=pre_frame)

        # 2. Locate Target
        candidate = await self.locate(target_description, observation)
        if not candidate:
            await self._notify_hud("VISION_FAILED", f"Could not find '{target_description}'")
            return {
                "success": False,
                "status": "TARGET_NOT_FOUND",
                "message": f"Could not visually ground target: '{target_description}'"
            }

        target_center = candidate.element.bounding_box.center

        # 3. Act
        await self.execute_visual_action(
            action_type=action_type,
            target_norm_coord=target_center,
            source=source
        )

        # Allow UI transition to settle
        await asyncio.sleep(settle_delay_sec)

        # 4. Capture Post-Frame
        post_frame = await self.capture(source=source)

        # 5. Check for Unexpected UI States
        unexpected_err = verification_engine.detect_unexpected_state(post_frame)
        if unexpected_err:
            audit_logger.log_event("unexpected_state", {"error": unexpected_err}, allowed=True, outcome="Detected")
            await self._notify_hud("VISION_FAILED", "Unexpected UI State Detected")
            recovery = VisionRecoveryRequest(
                failure_type="UNEXPECTED_UI_STATE",
                expected_state=expected_change,
                observed_state=unexpected_err,
                pre_frame=pre_frame,
                post_frame=post_frame
            )
            return {
                "success": False,
                "status": "UNEXPECTED_UI_STATE",
                "reason": unexpected_err,
                "recovery_request": recovery
            }

        # 6. Verify Visual Transition
        verification = verification_engine.verify_visual_transition(
            before=pre_frame,
            after=post_frame,
            target_region=candidate.element.bounding_box
        )

        audit_logger.log_event("verification_completed", {
            "strategy": verification.strategy,
            "status": verification.status.value,
            "reason": verification.reason
        }, allowed=True, outcome=verification.status.value)

        hud_state = "VISION_VERIFIED" if verification.status == VerificationStatus.VERIFIED else "VISION_FAILED"
        await self._notify_hud(hud_state, verification.reason[:50])

        return {
            "success": verification.status == VerificationStatus.VERIFIED,
            "status": verification.status.value,
            "target": candidate.element.label,
            "confidence": candidate.score,
            "reason": verification.reason,
            "diff_summary": verification.diff.description if verification.diff else ""
        }

vision_engine = OmniaVisionEngine()
