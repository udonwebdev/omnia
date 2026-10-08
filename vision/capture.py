import time
import io
import logging
from typing import Optional, Tuple
from PIL import Image
import mss

from vision.models import VisionFrame, VisionSource

logger = logging.getLogger("Omnia.Vision.Capture")

class VisionCaptureEngine:
    """Captures and validates screenshots across Desktop, Android ADB, and Browser surfaces."""

    @staticmethod
    def _validate_image_bytes(raw_data: bytes) -> Tuple[bool, int, int, str]:
        """Validates that bytes form a legitimate, non-empty, decodable image."""
        if not raw_data or len(raw_data) < 16:
            return False, 0, 0, "INVALID_FRAME: Byte stream empty or truncated"
        try:
            with Image.open(io.BytesIO(raw_data)) as img:
                w, h = img.size
                if w <= 0 or h <= 0:
                    return False, 0, 0, f"INVALID_FRAME: Corrupted dimensions {w}x{h}"
                return True, w, h, "OK"
        except Exception as e:
            return False, 0, 0, f"INVALID_FRAME: Image decoding failed ({str(e)})"

    async def capture_desktop(self) -> VisionFrame:
        """Captures real host desktop screen."""
        t0 = time.perf_counter()
        raw_bytes = None
        error_detail = None

        try:
            with mss.mss() as sct:
                # Capture primary monitor
                monitors = sct.monitors
                target_mon = monitors[1] if len(monitors) > 1 else monitors[0]
                sct_img = sct.grab(target_mon)
                
                # Convert to PNG bytes
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                out_buf = io.BytesIO()
                img.save(out_buf, format="PNG")
                raw_bytes = out_buf.getvalue()
        except Exception as ex:
            error_detail = str(ex)

        # Fallback to PIL ImageGrab if mss failed
        if not raw_bytes:
            try:
                from PIL import ImageGrab
                shot = ImageGrab.grab()
                out_buf = io.BytesIO()
                shot.save(out_buf, format="PNG")
                raw_bytes = out_buf.getvalue()
            except Exception as ex2:
                if not error_detail:
                    error_detail = str(ex2)

        duration_ms = (time.perf_counter() - t0) * 1000

        if not raw_bytes:
            raise RuntimeError(f"DESKTOP_CAPTURE_FAILED: Unable to grab desktop screen ({error_detail})")

        valid, w, h, msg = self._validate_image_bytes(raw_bytes)
        if not valid:
            raise ValueError(f"DESKTOP_CAPTURE_FAILED: {msg}")

        return VisionFrame(
            source=VisionSource.DESKTOP,
            device_id="desktop_host",
            width=w,
            height=h,
            raw_bytes=raw_bytes,
            format="png",
            capture_duration_ms=duration_ms
        )

    async def capture_android(self, serial: Optional[str] = None) -> VisionFrame:
        """Captures a real Android screen via ADB."""
        t0 = time.perf_counter()
        try:
            from device_controller import DeviceController
            ctl = DeviceController()
            if not ctl.devices:
                ctl.refresh_devices()

            if not ctl.devices:
                raise RuntimeError("DEVICE_NOT_FOUND: No active ADB devices connected to host.")

            target_device = None
            if serial:
                for dev in ctl.devices:
                    if dev.get_serial_no() == serial:
                        target_device = dev
                        break
                if not target_device:
                    raise RuntimeError(f"DEVICE_NOT_FOUND: ADB device '{serial}' not found in active mesh.")
            else:
                target_device = ctl.devices[0]

            dev_serial = target_device.get_serial_no()
            logger.info(f"Requesting ADB screencap from device: {dev_serial}")

            # Grab screenshot bytes via adb client screencap
            raw_screencap = target_device.screencap()
            duration_ms = (time.perf_counter() - t0) * 1000

            valid, w, h, msg = self._validate_image_bytes(raw_screencap)
            if not valid:
                raise ValueError(f"ADB_CAPTURE_FAILED: {msg}")

            return VisionFrame(
                source=VisionSource.ANDROID,
                device_id=dev_serial,
                width=w,
                height=h,
                raw_bytes=raw_screencap,
                format="png",
                capture_duration_ms=duration_ms,
                metadata={"adb_serial": dev_serial}
            )
        except Exception as e:
            if "DEVICE_NOT_FOUND" in str(e):
                raise
            raise RuntimeError(f"ADB_CAPTURE_FAILED: {str(e)}")

    async def capture_browser(self) -> VisionFrame:
        """Captures the visible active Playwright/CDP browser page."""
        t0 = time.perf_counter()
        try:
            from browser_driver import browser_driver
            if not browser_driver.active_page:
                await browser_driver.initialize()

            shot_bytes = await browser_driver.active_page.screenshot(full_page=False)
            duration_ms = (time.perf_counter() - t0) * 1000

            valid, w, h, msg = self._validate_image_bytes(shot_bytes)
            if not valid:
                raise ValueError(f"BROWSER_CAPTURE_FAILED: {msg}")

            return VisionFrame(
                source=VisionSource.BROWSER,
                device_id="browser_session",
                width=w,
                height=h,
                raw_bytes=shot_bytes,
                format="png",
                capture_duration_ms=duration_ms,
                metadata={"url": browser_driver.active_page.url}
            )
        except Exception as e:
            raise RuntimeError(f"BROWSER_CAPTURE_FAILED: {str(e)}")

capture_engine = VisionCaptureEngine()
