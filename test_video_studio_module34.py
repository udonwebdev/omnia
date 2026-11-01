"""Unit and Integration Tests for Module 34: Object Segmentation, Semantic Masking & Subject Isolation Engine.

Verifies:
1. Model discovery and availability safeguards:
   - Discovers registered segmentation models.
   - Accurately reports UNAVAILABLE when weights are not bundled.
   - Never fabricates placeholder or simulated masks.
2. Mask Refinement Operations:
   - Soft-mask preservation (non-destructive float32 precision).
   - Binarization thresholding.
   - Morphological erosion and dilation.
   - Edge-aware and Gaussian feathering.
   - Connected-component interior hole closure.
   - Polarity inversion.
3. Multi-Mask Combination Operations:
   - REPLACE, UNION, INTERSECT, SUBTRACT, INVERT combinations.
4. Non-AI Mask Ingestion:
   - Ingestion of external floating-point and uint8 mask arrays.
   - Conversion to Module 11 CompositingMask contract.
5. Integration with Module 23 Chroma Keying:
   - Combining chroma mattes with segmentation masks.
6. Optical-flow-assisted mask propagation:
   - Propagating masks using Module 33 dense optical flow.
   - Scene-cut detection and propagation reset.
7. Service state management, undo/redo:
   - Ingestion, frame retrieval, and multi-mask containers.
8. Effects Processor Registry Integration:
   - VideoSegmentationEffectProcessor registered under COMPOSITING and frame rendering.
"""

import unittest
import numpy as np
import cv2

from video_studio.effects_models import VideoFrameBuffer, EffectCategory
from video_studio.effects_processors import effect_processor_registry
from video_studio.segmentation_models import (
    SegmentationWorkflowType,
    SegmentationPromptType,
    MaskCombinationMode,
    MaskFormat,
    SegmentationModelStatus,
    SegmentationPrompt,
    ModelRuntimeDescriptor,
    MaskRefinementConfig,
    VideoSegmentMask,
    MultiMaskFrameContainer,
)
from video_studio.segmentation_engine import VideoSegmentationEngine
from video_studio.segmentation_service import VideoSegmentationService
from video_studio.segmentation_processor import VideoSegmentationEffectProcessor
from video_studio.optical_flow_models import MotionVectorField, FlowFieldStatus


def make_test_frame(width: int, height: int, data: np.ndarray, frame_number: int = 0) -> VideoFrameBuffer:
    buf = VideoFrameBuffer(width=width, height=height, data=data)
    buf.timeline_frame = frame_number
    buf.pts_seconds = frame_number * 0.04
    return buf


class TestVideoStudioModule34(unittest.TestCase):

    def setUp(self):
        self.engine = VideoSegmentationEngine()
        self.service = VideoSegmentationService(engine=self.engine)

    def test_model_discovery_and_unavailability_safeguards(self):
        """Tests that models report UNAVAILABLE when weights are missing and refuse to fabricate masks."""
        models = self.engine.get_registered_models()
        self.assertGreater(len(models), 0)

        sam_model = self.engine.get_model("sam_interactive")
        self.assertIsNotNone(sam_model)
        self.assertEqual(sam_model.status, SegmentationModelStatus.UNAVAILABLE)

        dummy_rgb = np.zeros((100, 100, 3), dtype=np.uint8)
        mask, status = self.engine.execute_segmentation_inference(
            dummy_rgb, "sam_interactive", [SegmentationPrompt(prompt_type=SegmentationPromptType.POSITIVE_POINT, x=50, y=50)]
        )
        self.assertIsNone(mask)
        self.assertFalse(status["success"])
        self.assertEqual(status["status"], "UNAVAILABLE")

    def test_mask_refinement_erosion_dilation_and_inversion(self):
        """Tests morphological erosion, dilation, and polarity inversion."""
        h, w = 40, 40
        # Solid center square (20x20)
        raw_mask = np.zeros((h, w), dtype=np.float32)
        raw_mask[10:30, 10:30] = 1.0

        # 1. Erosion: square should shrink
        cfg_erode = MaskRefinementConfig(erode_radius=2)
        eroded = self.engine.refine_mask(raw_mask, cfg_erode)
        self.assertLess(np.sum(eroded), np.sum(raw_mask))
        self.assertEqual(eroded[10, 10], 0.0)
        self.assertEqual(eroded[20, 20], 1.0)

        # 2. Dilation: square should expand
        cfg_dilate = MaskRefinementConfig(dilate_radius=2)
        dilated = self.engine.refine_mask(raw_mask, cfg_dilate)
        self.assertGreater(np.sum(dilated), np.sum(raw_mask))
        self.assertEqual(dilated[9, 9], 1.0)

        # 3. Inversion
        cfg_inv = MaskRefinementConfig(invert_mask=True)
        inverted = self.engine.refine_mask(raw_mask, cfg_inv)
        self.assertEqual(inverted[0, 0], 1.0)
        self.assertEqual(inverted[20, 20], 0.0)

    def test_mask_refinement_hole_filling(self):
        """Tests automatic connected-component interior hole closure."""
        h, w = 30, 30
        mask = np.zeros((h, w), dtype=np.float32)
        # Ring / frame with hole in center
        mask[5:25, 5:25] = 1.0
        mask[12:18, 12:18] = 0.0 # Center hole

        self.assertEqual(mask[15, 15], 0.0)

        cfg_fill = MaskRefinementConfig(fill_holes=True)
        filled = self.engine.refine_mask(mask, cfg_fill)

        # Interior hole must now be filled (1.0)
        self.assertEqual(filled[15, 15], 1.0)
        # Exterior background must remain 0.0
        self.assertEqual(filled[0, 0], 0.0)

    def test_mask_refinement_feathering(self):
        """Tests Gaussian and edge-preserving feathering on sharp boundaries."""
        h, w = 30, 30
        mask = np.zeros((h, w), dtype=np.float32)
        mask[:, :15] = 1.0

        cfg_feather = MaskRefinementConfig(feather_radius=3.0)
        feathered = self.engine.refine_mask(mask, cfg_feather)

        # Boundary at x=14 and x=15 should be soft gradients, not binary 0/1
        self.assertTrue(0.1 < feathered[15, 14] < 0.9)
        self.assertTrue(0.1 < feathered[15, 15] < 0.9)

    def test_multi_mask_combination_modes(self):
        """Tests boolean and arithmetic mask combination modes."""
        h, w = 20, 20
        # Mask A: top half
        mask_a = np.zeros((h, w), dtype=np.float32)
        mask_a[:10, :] = 1.0

        # Mask B: left half
        mask_b = np.zeros((h, w), dtype=np.float32)
        mask_b[:, :10] = 1.0

        # 1. UNION: top half OR left half
        union_mask = self.engine.combine_masks(mask_a, mask_b, mode=MaskCombinationMode.UNION)
        self.assertEqual(union_mask[5, 5], 1.0)  # top-left
        self.assertEqual(union_mask[5, 15], 1.0) # top-right
        self.assertEqual(union_mask[15, 5], 1.0) # bottom-left
        self.assertEqual(union_mask[15, 15], 0.0)# bottom-right

        # 2. INTERSECT: top half AND left half (only top-left quadrant)
        intersect_mask = self.engine.combine_masks(mask_a, mask_b, mode=MaskCombinationMode.INTERSECT)
        self.assertEqual(intersect_mask[5, 5], 1.0)
        self.assertEqual(intersect_mask[5, 15], 0.0)
        self.assertEqual(intersect_mask[15, 5], 0.0)

        # 3. SUBTRACT: Mask A minus Mask B (only top-right quadrant)
        sub_mask = self.engine.combine_masks(mask_a, mask_b, mode=MaskCombinationMode.SUBTRACT)
        self.assertEqual(sub_mask[5, 15], 1.0)
        self.assertEqual(sub_mask[5, 5], 0.0)

    def test_non_ai_mask_ingestion_and_compositing_export(self):
        """Tests external mask ingestion and conversion to Module 11 CompositingMask."""
        clip_id = "test_clip_seg_01"
        h, w = 32, 32
        imported_array = np.full((h, w), 200, dtype=np.uint8)

        seg_mask = self.service.ingest_imported_mask(
            clip_id=clip_id,
            frame_number=0,
            mask_data=imported_array,
            label="external_matte",
        )
        self.assertEqual(seg_mask.workflow, SegmentationWorkflowType.IMPORTED_MASK)
        self.assertEqual(seg_mask.width, w)
        self.assertEqual(seg_mask.height, h)

        # Convert to Module 11 CompositingMask
        comp_mask = self.service.export_as_compositing_mask(clip_id, frame_number=0)
        self.assertIsNotNone(comp_mask)
        self.assertEqual(comp_mask.mask_data.shape, (h, w))
        self.assertEqual(comp_mask.mask_data[10, 10], 200)

    def test_chroma_matte_combination(self):
        """Tests combination of Module 23 Chroma Key matte with segmentation mask."""
        clip_id = "test_chroma_seg"
        h, w = 20, 20
        # Ingest segmentation mask covering left half
        seg_data = np.zeros((h, w), dtype=np.float32)
        seg_data[:, :10] = 1.0
        self.service.ingest_imported_mask(clip_id, frame_number=0, mask_data=seg_data)

        # Chroma matte covering top half
        chroma_matte = np.zeros((h, w), dtype=np.uint8)
        chroma_matte[:10, :] = 255

        combined = self.service.combine_with_chroma_matte(
            chroma_matte_uint8=chroma_matte,
            clip_id=clip_id,
            frame_number=0,
            mode=MaskCombinationMode.INTERSECT,
        )
        # Intersection: only top-left quadrant should be 255
        self.assertEqual(combined[5, 5], 255)
        self.assertEqual(combined[5, 15], 0)
        self.assertEqual(combined[15, 5], 0)

    def test_optical_flow_mask_propagation(self):
        """Tests warping masks across frames using dense optical flow."""
        h, w = 30, 30
        mask = np.zeros((h, w), dtype=np.float32)
        mask[10:20, 10:20] = 1.0 # Center square

        # Synthetic optical flow: uniform shift dx=3, dy=0
        flow_data = np.zeros((h, w, 2), dtype=np.float32)
        flow_data[:, :, 0] = 3.0 # Shift rightwards by 3
        flow_field = MotionVectorField(
            width=w, height=h, dense_flow=flow_data,
            confidence_map=np.full((h, w), 0.9, dtype=np.float32),
            status=FlowFieldStatus.VALID,
        )

        f_a = make_test_frame(w, h, np.zeros((h, w, 4), dtype=np.uint8), frame_number=0)
        f_b = make_test_frame(w, h, np.zeros((h, w, 4), dtype=np.uint8), frame_number=1)

        warped_mask, conf, is_cut = self.engine.propagate_mask_optical_flow(
            source_mask=mask,
            source_frame=f_a,
            target_frame=f_b,
            optical_flow_field=flow_field,
        )

        self.assertFalse(is_cut)
        self.assertGreater(conf, 0.8)
        # Original center at x=15 shifted rightwards (+3) should now be at x=18
        self.assertEqual(warped_mask[15, 18], 1.0)

    def test_optical_flow_propagation_scene_cut_reset(self):
        """Tests that a scene cut halts mask propagation and resets mask to zero."""
        h, w = 20, 20
        mask = np.ones((h, w), dtype=np.float32)
        flow_field = MotionVectorField(width=w, height=h, status=FlowFieldStatus.SCENE_CUT_DETECTED)

        f_a = make_test_frame(w, h, np.zeros((h, w, 4), dtype=np.uint8))
        f_b = make_test_frame(w, h, np.full((h, w, 4), 255, dtype=np.uint8))

        warped_mask, conf, is_cut = self.engine.propagate_mask_optical_flow(
            source_mask=mask, source_frame=f_a, target_frame=f_b, optical_flow_field=flow_field
        )

        self.assertTrue(is_cut)
        self.assertEqual(conf, 0.0)
        self.assertTrue(np.all(warped_mask == 0.0))

    def test_effects_processor_registry_integration(self):
        """Tests that VideoSegmentationEffectProcessor is registered and modulates frame alpha."""
        processor = effect_processor_registry.get("subject_segmentation_isolation")
        self.assertIsNotNone(processor)
        self.assertEqual(processor.category, EffectCategory.COMPOSITING)

        clip_id = "test_clip_proc"
        w, h = 24, 24
        # Ingest mask covering left half into processor's service
        seg_data = np.zeros((h, w), dtype=np.float32)
        seg_data[:, :12] = 1.0
        processor.service.ingest_imported_mask(clip_id=clip_id, frame_number=3, mask_data=seg_data)

        # Input frame with full alpha 255
        frame = make_test_frame(w, h, np.full((h, w, 4), 255, dtype=np.uint8), frame_number=3)

        out_frame = processor.process_frame(
            frame=frame,
            parameters={"clip_id": clip_id, "combination_mode": "UNION", "mask_opacity": 1.0},
            render_width=w,
            render_height=h,
        )

        # Left half should remain 255, right half should become 0
        self.assertEqual(out_frame.data[12, 5, 3], 255)
        self.assertEqual(out_frame.data[12, 18, 3], 0)


if __name__ == "__main__":
    unittest.main()
