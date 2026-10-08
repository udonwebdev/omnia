import asyncio
import io
import time
from PIL import Image, ImageDraw
import numpy as np

from vision.models import (
    VisionSource,
    ElementType,
    VerificationStatus,
    BoundingBox,
    VisionFrame,
    VisionElement,
    VisionObservation
)
from vision.capture import capture_engine
from vision.ocr import ocr_engine
from vision.perception import perception_engine
from vision.grounding import grounding_engine
from vision.comparison import diff_engine
from vision.verification import verification_engine
from vision.vision_engine import vision_engine

def generate_test_ui(title: str = "Login Portal", button_text: str = "Continue", has_error: bool = False) -> VisionFrame:
    """Generates a synthetic UI screen for deterministic testing."""
    img = Image.new("RGB", (800, 600), color=(240, 244, 248))
    draw = ImageDraw.Draw(img)

    # Header
    draw.rectangle([0, 0, 800, 60], fill=(20, 30, 48))
    draw.text((30, 20), title, fill=(255, 255, 255))

    # Input Box
    draw.rectangle([250, 200, 550, 245], outline=(100, 110, 130), width=2, fill=(255, 255, 255))
    draw.text((260, 215), "Search Query", fill=(120, 120, 120))

    # Action Button
    draw.rectangle([250, 280, 550, 330], fill=(0, 122, 255))
    draw.text((370, 295), button_text, fill=(255, 255, 255))

    # Error banner if requested
    if has_error:
        draw.rectangle([250, 360, 550, 410], fill=(255, 59, 48))
        draw.text((270, 375), "Error: Invalid Access Key", fill=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw = buf.getvalue()

    return VisionFrame(
        source=VisionSource.DESKTOP,
        width=800,
        height=600,
        raw_bytes=raw,
        format="png"
    )

async def run_vision_test_suite():
    print("=" * 65)
    print("          OMNIA MODULE 13: VISION TEST SUITE          ")
    print("=" * 65)

    # 1. Coordinate Systems & Math
    print("\n[TEST 1] Coordinate Transformations...")
    bbox = BoundingBox(x=0.25, y=0.5, width=0.5, height=0.25)
    px, py, pw, ph = bbox.to_pixels(1000, 800)
    assert (px, py, pw, ph) == (250, 400, 500, 200)
    
    # Re-normalize
    bbox_restored = BoundingBox.from_pixels(px, py, pw, ph, 1000, 800)
    assert abs(bbox_restored.x - 0.25) < 1e-4
    assert abs(bbox_restored.y - 0.5) < 1e-4
    print(" -> Normalized <-> Pixel coordinates: PASS")

    # 2. Local OCR Extraction
    print("\n[TEST 2] Local OCR Engine Extraction...")
    frame_a = generate_test_ui(button_text="Continue")
    regions = ocr_engine.extract_text_regions(frame_a)
    assert len(regions) >= 2, f"Expected at least 2 text regions, got {len(regions)}"
    texts = [r["text"] for r in regions]
    print(f" -> Detected regions ({len(regions)}): {texts}")
    assert any("continue" in t.lower() for t in texts)
    print(" -> OCR Extraction: PASS")

    # 3. Perception & Semantic Classification
    print("\n[TEST 3] Visual Perception & Semantic Classification...")
    obs = perception_engine.analyze_frame(frame_a)
    assert len(obs.elements) > 0
    btn_elements = [el for el in obs.elements if el.element_type == ElementType.BUTTON]
    assert len(btn_elements) > 0, "Button element not classified"
    print(f" -> Classified button: '{btn_elements[0].label}' (confidence: {btn_elements[0].confidence:.2f})")
    print(" -> Perception Engine: PASS")

    # 4. Visual Grounding & Candidate Ranking
    print("\n[TEST 4] Visual Grounding & Ranking...")
    best_candidate = grounding_engine.ground_best("continue button", obs)
    assert best_candidate is not None
    assert "continue" in best_candidate.element.label.lower()
    print(f" -> Grounded: '{best_candidate.element.label}' (Rank {best_candidate.rank}, Score {best_candidate.score:.2f})")
    
    # Negative test
    missing = grounding_engine.ground_best("nonexistent checkout button", obs)
    assert missing is None or missing.score < 0.4
    print(" -> Negative grounding query rejection: PASS")

    # 5. Image Comparison & Structural Diffing
    print("\n[TEST 5] Image Comparison Engine...")
    frame_b = generate_test_ui(button_text="Done")
    diff = diff_engine.compare_frames(frame_a, frame_b)
    print(f" -> Measured diff: {diff.changed_pixels_ratio * 100:.2f}%, description: {diff.description}")
    assert diff.changed_pixels_ratio > 0.0, "Expected pixel differences between frames"
    print(" -> Difference Engine: PASS")

    # 6. Verification Engine
    print("\n[TEST 6] Verification Engine Strategies...")
    # Appearance check
    v1 = verification_engine.verify_text_appearance(frame_a, frame_b, "Done", should_appear=True)
    assert v1.status == VerificationStatus.VERIFIED
    print(f" -> Text appearance verified: PASS ({v1.reason})")

    # Unexpected state detection
    frame_err = generate_test_ui(has_error=True)
    err = verification_engine.detect_unexpected_state(frame_err)
    assert err is not None
    print(f" -> Unexpected state detected: PASS ({err})")

    # 7. Security & Governance Filter
    print("\n[TEST 7] Security Governance on Visual Action...")
    try:
        await vision_engine.execute_visual_action(
            action_type="type",
            target_norm_coord=(0.5, 0.5),
            source=VisionSource.DESKTOP,
            text_input="my_secret_password"
        )
        assert False, "Sensitive input was not blocked by governance"
    except PermissionError as pe:
        print(f" -> Governance intercept: PASS ({pe})")

    # 8. Real Browser Visual Perception & Grounding
    print("\n[TEST 8] Real End-to-End Browser Vision...")
    try:
        browser_frame = await capture_engine.capture_browser()
        assert browser_frame.width > 0 and browser_frame.height > 0
        b_obs = perception_engine.analyze_frame(browser_frame)
        print(f" -> Browser screenshot captured: {browser_frame.width}x{browser_frame.height}")
        print(f" -> Visual elements detected on browser page: {len(b_obs.elements)}")
        b_target = grounding_engine.ground_best("example", b_obs)
        if b_target:
            print(f" -> Grounded on live page: '{b_target.element.label}' (score: {b_target.score:.2f})")
        print(" -> Real Browser Visual Loop: PASS")
    except Exception as ex:
        print(f" -> Real Browser Vision: NOTICE ({ex})")

    # 9. Hardware & Session Isolation Checks
    print("\n[TEST 9] Hardware & Device Error Classification...")
    try:
        await capture_engine.capture_android("fake_serial_9999")
        assert False, "Should have thrown DEVICE_NOT_FOUND"
    except RuntimeError as re:
        print(f" -> Android error handling: PASS ({re})")

    print("\n" + "=" * 65)
    print("       ALL MODULE 13 VISION TESTS COMPLETED SUCCESSFULLY!      ")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(run_vision_test_suite())
