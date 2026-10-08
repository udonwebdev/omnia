# Omnia Module 13: Multimodal Vision & Visual Computer Use

## 1. Overview
Module 13 provides the perception and visual grounding layer for the Omnia autonomous orchestration architecture. It equips Omnia with the ability to capture real screens, perceive visible semantic UI regions via local OCR, ground natural language user commands onto candidate regions, execute controlled visual actions through the policy governor, and visually verify that the expected UI state transition occurred.

The core operational cycle follows the **Observe-Act-Verify** loop:
```
CAPTURE → PERCEIVE → GROUND / LOCATE → POLICY CHECK → ACT → CAPTURE → COMPARE → VERIFY
```

---

## 2. Architecture & File Structure
```
vision/
    __init__.py          # Public package API exports
    models.py            # Strongly typed domain models (VisionFrame, VisionElement, etc.)
    capture.py           # Multi-surface screen capture (Desktop, Android ADB, Browser)
    ocr.py               # Pluggable local OCR abstraction using RapidOCR (ONNX)
    perception.py        # Semantic classification of UI elements (BUTTON, INPUT, LINK, etc.)
    grounding.py         # Visual grounding engine with ranking heuristics
    comparison.py        # Screen difference engine (pixel and structural grid comparison)
    verification.py      # Verification strategies (text appearance, transition, error popups)
    vision_engine.py     # Central orchestrator integrating governance, audit logs, and HUD events
```

---

## 3. Supported Vision Surfaces
1. **Desktop**: Captured via `mss` / `PIL.ImageGrab`. Note: In headless, service, or disconnected RDP sessions, Windows OS denies display buffer access (`BitBlt` / `grabscreen_win32`), in which case the engine returns a structured `DESKTOP_CAPTURE_FAILED` error.
2. **Android (ADB)**: Captured via `ppadb` screencap buffer. If no active ADB devices exist or ADB server is stopped, raises `DEVICE_NOT_FOUND` or `ADB_CAPTURE_FAILED`.
3. **Browser**: Captured directly via Playwright/CDP (`active_page.screenshot`). Provides direct visual feedback on web SPAs where accessibility or DOM trees are insufficient.

---

## 4. Coordinate System
Omnia Vision standardizes on a **normalized coordinate system** `[0.0, 1.0]`:
- `x`: Horizontal offset normalized against frame width ($0.0$ is left, $1.0$ is right).
- `y`: Vertical offset normalized against frame height ($0.0$ is top, $1.0$ is bottom).
- `width`, `height`: Normalized box dimensions.
- Conversion functions: `BoundingBox.to_pixels(w, h)` and `BoundingBox.from_pixels(px, py, pw, ph, w, h)`.

---

## 5. Security & Policy Governance
Visual interactions (`click`, `tap`, `type`, `scroll`) are intercepted before execution:
- Calls to `click_visual_element` are wrapped with `@guard_action`.
- Text injection containing credential keywords (`password`, `cvv`, `card`) is blocked immediately with a `PermissionError`.
- All operations are appended to the cryptographically linked audit chain (`omnia_audit.jsonl`).

---

## 6. Verification Statuses
- **VERIFIED**: Screen transition or text appearance/disappearance confirmed by structural image diff or OCR match.
- **FAILED**: Expected change did not occur or expected text was missing.
- **UNCERTAIN**: Difference was ambiguous or below the confidence threshold. Never coerced into VERIFIED.
- **UNEXPECTED_UI_STATE**: Detected error banners, crash dialogs, or fatal exceptions in the post-action frame.

---

## 7. Automated Testing
Run the comprehensive verification suite:
```bash
python test_vision_module13.py
```
Run the system-wide diagnostic check:
```bash
python system_check.py
```
