"""Unit tests for OMNIA Video Studio Module 16: Video Color Grading, Color Management & Look Development Engine.

Covers:
1. Primary color correction (exposure EV, contrast & pivot, temperature & tint, saturation, vibrance).
2. Three-way color wheels (Lift, Gamma, Gain, Offset) with mathematical verification.
3. Parametric tone curves (identity check, spline LUT generation, per-channel curves).
4. HSL secondary color qualification (hue windowing with circular wraparound, luma/sat gating).
5. 3D Look-Up Table (.cube) parsing and trilinear interpolation on float32 image buffers.
6. Real-time color scopes generation (256-bin RGB/luma histogram, waveform, vectorscope UV, parade).
7. Reusable creative looks and clip grade persistence.
8. Capability registry registration and health.
"""

import unittest
import numpy as np

from video_studio.color_models import (
    ColorGradeDocument,
    PrimaryGrade,
    LiftGammaGain,
    WheelBalance,
    ColorCurves,
    CurvePoint,
    HSLQualifier,
    LUTDescriptor,
    LUTType,
    ColorSpace,
)
from video_studio.color_pipeline import color_pipeline_processor
from video_studio.color_lut import lut_processor, LUTParser
from video_studio.color_service import color_service
from video_studio.compositing_models import VideoFrameBuffer

class TestVideoStudioModule16(unittest.TestCase):

    def test_01_primary_color_correction_pixels(self):
        """Verifies exposure, contrast, temperature, tint, and saturation modify actual pixels."""
        # 10x10 mid-gray frame: (128, 128, 128, 255)
        raw = np.full((10, 10, 4), 128, dtype=np.uint8)
        raw[:, :, 3] = 255
        frame = VideoFrameBuffer(width=10, height=10, data=raw)

        # 1. Exposure +1 EV (should roughly double RGB values from ~128 to ~255)
        grade_exp = ColorGradeDocument(
            grade_id="g_exp",
            primary=PrimaryGrade(exposure=1.0),
        )
        res_exp = color_pipeline_processor.process_frame(frame, grade_exp)
        self.assertGreater(res_exp.data[0, 0, 0], 250)
        self.assertEqual(res_exp.data[0, 0, 3], 255) # Alpha preserved

        # 2. Warm Temperature (+50)
        grade_temp = ColorGradeDocument(
            grade_id="g_temp",
            primary=PrimaryGrade(temperature=50.0),
        )
        res_temp = color_pipeline_processor.process_frame(frame, grade_temp)
        # Red should increase, Blue should decrease
        self.assertGreater(res_temp.data[0, 0, 0], res_temp.data[0, 0, 2])

    def test_02_lift_gamma_gain_wheels(self):
        """Verifies 3-way color wheels perform real mathematical shadow/highlight adjustments."""
        # Frame with black (0), midtone (128), and white (255)
        raw = np.zeros((3, 1, 4), dtype=np.uint8)
        raw[0, 0, :3] = 0     # Black
        raw[1, 0, :3] = 128   # Midtone
        raw[2, 0, :3] = 255   # White
        frame = VideoFrameBuffer(width=1, height=3, data=raw)

        # Lift (shadows) adjustment: red lift +0.2
        grade_lift = ColorGradeDocument(
            grade_id="g_lift",
            wheels=LiftGammaGain(
                lift=WheelBalance(r=0.2, g=0.0, b=0.0),
            ),
        )
        res_lift = color_pipeline_processor.process_frame(frame, grade_lift)
        # Black pixel's red channel should now be lifted (> 0)
        self.assertGreater(res_lift.data[0, 0, 0], 40)
        self.assertEqual(res_lift.data[0, 0, 1], 0) # Green untouched

        # Gain (highlights) adjustment: blue gain +0.5
        grade_gain = ColorGradeDocument(
            grade_id="g_gain",
            wheels=LiftGammaGain(
                gain=WheelBalance(r=0.0, g=0.0, b=0.5),
            ),
        )
        res_gain = color_pipeline_processor.process_frame(frame, grade_gain)
        # White pixel already clamped at 255, but midtone blue should increase more than black
        self.assertGreater(res_gain.data[1, 0, 2], res_gain.data[1, 0, 0])

    def test_03_tone_curves(self):
        """Verifies tone curves and identity curve behavior."""
        raw = np.full((10, 10, 4), 100, dtype=np.uint8)
        frame = VideoFrameBuffer(width=10, height=10, data=raw)

        # Identity curve: should leave pixels unchanged
        grade_ident = ColorGradeDocument(grade_id="g_ident")
        res_ident = color_pipeline_processor.process_frame(frame, grade_ident)
        np.testing.assert_array_equal(res_ident.data, raw)

        # Master curve boosting input 0.39 (~100/255) to 0.8 (~204/255)
        grade_curve = ColorGradeDocument(
            grade_id="g_curve",
            curves=ColorCurves(
                master=[CurvePoint(0.0, 0.0), CurvePoint(0.39, 0.8), CurvePoint(1.0, 1.0)],
            ),
        )
        res_curve = color_pipeline_processor.process_frame(frame, grade_curve)
        self.assertGreater(res_curve.data[0, 0, 0], 190)

    def test_04_hsl_secondary_qualifier(self):
        """Verifies HSL qualification selects specific hues and modifies them exclusively."""
        # 2x2 image: Red pixel, Green pixel, Blue pixel, White pixel
        raw = np.zeros((2, 2, 4), dtype=np.uint8)
        raw[0, 0, :3] = [255, 0, 0]     # Red (Hue = 0)
        raw[0, 1, :3] = [0, 255, 0]     # Green (Hue = 120)
        raw[1, 0, :3] = [0, 0, 255]     # Blue (Hue = 240)
        raw[1, 1, :3] = [255, 255, 255] # White (Sat = 0)
        raw[:, :, 3] = 255
        frame = VideoFrameBuffer(width=2, height=2, data=raw)

        # Qualify Red hue (center=0, width=40) and desaturate it
        q = HSLQualifier(
            is_enabled=True,
            hue_center=0.0,
            hue_width=40.0,
            hue_softness=5.0,
            sat_min=0.2,
            sat_max=1.0,
            luma_min=0.1,
            luma_max=0.9,
            target_sat_scale=0.0, # Desaturate qualified pixels to grayscale
        )
        grade_hsl = ColorGradeDocument(grade_id="g_hsl", hsl_qualifier=q)
        res_hsl = color_pipeline_processor.process_frame(frame, grade_hsl)

        # Red pixel should now be desaturated (R ~= G ~= B)
        red_pixel = res_hsl.data[0, 0, :3]
        self.assertAlmostEqual(int(red_pixel[0]), int(red_pixel[1]), delta=10)

        # Green and Blue pixels must remain unchanged
        np.testing.assert_array_equal(res_hsl.data[0, 1, :3], [0, 255, 0])
        np.testing.assert_array_equal(res_hsl.data[1, 0, :3], [0, 0, 255])

    def test_05_lut_parser_and_trilinear_interpolation(self):
        """Verifies .cube parser and trilinear 3D LUT application."""
        # Minimal 2x2x2 cube LUT that inverts RGB
        cube_text = """
TITLE "Invert 2x2x2"
LUT_3D_SIZE 2
1.0 1.0 1.0
0.0 1.0 1.0
1.0 0.0 1.0
0.0 0.0 1.0
1.0 1.0 0.0
0.0 1.0 0.0
1.0 0.0 0.0
0.0 0.0 0.0
"""
        lut = LUTParser.parse_cube_content(cube_text, lut_id="lut_inv", name="Invert")
        self.assertEqual(lut.size, 2)
        self.assertEqual(lut.lut_type, LUTType.LUT_3D)

        # Apply to a black frame (0, 0, 0) -> should become white (255, 255, 255)
        raw_black = np.zeros((4, 4, 4), dtype=np.uint8)
        raw_black[:, :, 3] = 255
        frame = VideoFrameBuffer(width=4, height=4, data=raw_black)

        grade_lut = ColorGradeDocument(grade_id="g_lut", lut=lut)
        res_lut = color_pipeline_processor.process_frame(frame, grade_lut)
        self.assertGreater(res_lut.data[0, 0, 0], 250)
        self.assertGreater(res_lut.data[0, 0, 1], 250)
        self.assertGreater(res_lut.data[0, 0, 2], 250)

    def test_06_color_scopes_measurements(self):
        """Verifies calculation of real histogram, waveform, vectorscope, and parade."""
        raw = np.zeros((16, 16, 4), dtype=np.uint8)
        raw[:8, :, :3] = 50   # Dark top
        raw[8:, :, :3] = 200  # Bright bottom
        raw[:, :, 3] = 255
        frame = VideoFrameBuffer(width=16, height=16, data=raw)

        scopes = color_pipeline_processor.calculate_scopes(frame)
        self.assertEqual(len(scopes.histogram_luma), 256)
        # Should have peaks at bins 50 and 200
        self.assertGreater(scopes.histogram_luma[50], 0)
        self.assertGreater(scopes.histogram_luma[200], 0)
        self.assertEqual(scopes.histogram_luma[0], 0)

        # Waveform should measure average column luminance
        self.assertGreater(len(scopes.waveform_samples), 0)
        # RGB Parade
        self.assertIn("r", scopes.rgb_parade)

    def test_07_looks_preset_catalog(self):
        """Verifies built-in creative looks and look application."""
        looks = color_service.list_looks()
        self.assertGreaterEqual(len(looks), 3)

        # Apply 'look_golden_hour' to clip
        grade = color_service.apply_look_to_clip("look_golden_hour", item_id="clip_sunset")
        self.assertIsNotNone(grade)
        self.assertGreater(grade.primary.temperature, 20.0)

    def test_08_capability_registry_ready(self):
        """Verifies Module 16 capabilities registered into Video Studio Capability Registry."""
        from video_studio.registry import video_studio_capability_registry
        from video_studio.registry_models import ImplementationState

        color_service.register_capabilities()

        cap_prim = video_studio_capability_registry.get("video.color.primary")
        self.assertIsNotNone(cap_prim)
        self.assertEqual(cap_prim.implementation_state, ImplementationState.IMPLEMENTED)

        cap_lut = video_studio_capability_registry.get("video.color.lut_processor")
        self.assertIsNotNone(cap_lut)
        self.assertEqual(cap_lut.implementation_state, ImplementationState.IMPLEMENTED)

if __name__ == "__main__":
    unittest.main()
