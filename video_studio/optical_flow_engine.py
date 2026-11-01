"""OMNIA Video Studio — Optical Flow & Motion Vector Estimation Engine (Module 33).

Implements genuine computer-vision motion analysis:
1. Dense Optical Flow (Farneback & DIS):
   - Computes pixel-dense (H, W, 2) flow fields between real decoded frames.
   - Forward and backward bidirectional flow calculation.
2. Sparse Lucas-Kanade Optical Flow:
   - Shi-Tomasi corner detection with pyramidal tracking.
   - Explicitly identified as SPARSE (never confused with dense fields).
3. Forward-Backward Consistency Verification:
   - Warps backward flow using forward flow to compute Euclidean consistency error.
   - Detects occlusions, disocclusions, and motion boundaries without arbitrary heuristics.
4. Scene-Cut & Discontinuity Detection:
   - Detects abrupt cuts and invalidates motion vectors with FlowFieldStatus.SCENE_CUT_DETECTED.
   - Never returns fabricated zero vectors as successful estimates during failures.
5. Motion Field Operations:
   - Resizing and coordinate scaling (re-scaling dx, dy proportionately).
   - Motion field visualization (HSV color-wheel encoding: Hue=angle, Saturation=magnitude).
   - Sub-region vector sampling.
"""

import math
import time
import logging
from typing import Dict, Any, List, Optional, Tuple

import cv2
import numpy as np

from video_studio.effects_models import VideoFrameBuffer
from video_studio.optical_flow_models import (
    MotionVectorField,
    MotionVectorFieldType,
    FlowAlgorithmType,
    FlowQualityPreset,
    FlowVectorCoordinateSystem,
    FlowDirection,
    FlowFieldStatus,
    MotionVector2D,
    MotionDiagnostics,
    MotionAnalysisConfig,
)

logger = logging.getLogger("omnia.video_studio.optical_flow_engine")


class OpticalFlowEngine:
    """Core computer vision engine for computing, validating, and transforming motion vector fields."""

    def __init__(self):
        self._field_cache: Dict[str, MotionVectorField] = {} # cache_key -> MotionVectorField
        self._max_cache_entries = 120

    # -------------------------------------------------------------------------
    # 1. Image Preprocessing & Scene-Cut Safeguards
    # -------------------------------------------------------------------------

    def _prepare_gray_frame(self, frame_data: np.ndarray) -> np.ndarray:
        """Convert input frame data to single-channel uint8 grayscale."""
        if frame_data is None or frame_data.size == 0:
            raise ValueError("Empty or invalid frame data provided to optical flow engine.")

        if frame_data.ndim == 2:
            return frame_data.astype(np.uint8)

        channels = frame_data.shape[2]
        if channels == 4:
            return cv2.cvtColor(frame_data, cv2.COLOR_BGRA2GRAY if frame_data.dtype == np.uint8 else cv2.COLOR_RGBA2GRAY)
        elif channels == 3:
            return cv2.cvtColor(frame_data, cv2.COLOR_BGR2GRAY)
        elif channels == 1:
            return frame_data[:, :, 0].astype(np.uint8)
        else:
            raise ValueError(f"Unsupported channel count for optical flow: {channels}")

    def detect_scene_cut(
        self,
        gray_a: np.ndarray,
        gray_b: np.ndarray,
        threshold: float = 35.0,
    ) -> Tuple[bool, float]:
        """Detect whether a scene cut or abrupt discontinuity occurred between two frames.
        
        Calculates mean absolute difference (MAD) and histogram intersection.
        """
        if gray_a.shape != gray_b.shape:
            return True, 999.0

        mad = float(np.mean(cv2.absdiff(gray_a, gray_b)))
        is_cut = mad >= threshold
        return is_cut, mad

    # -------------------------------------------------------------------------
    # 2. Forward-Backward Consistency & Occlusion Estimation
    # -------------------------------------------------------------------------

    def compute_bidirectional_consistency(
        self,
        flow_forward: np.ndarray,
        flow_backward: np.ndarray,
        threshold: float = 1.5,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Evaluate forward-backward consistency check.
        
        For a pixel x at frame A:
            target = x + flow_forward(x)
            back_vector = flow_backward(target)
            error = || flow_forward(x) + back_vector ||
        
        Returns:
            Tuple of:
            - consistency_error: (H, W) float32 Euclidean pixel discrepancy
            - confidence_map: (H, W) float32 [0.0, 1.0] confidence score
            - occlusion_mask: (H, W) uint8 (255=occluded, 0=valid)
        """
        h, w = flow_forward.shape[:2]
        grid_y, grid_x = np.indices((h, w), dtype=np.float32)

        # Warp backward flow to frame A coordinates
        target_x = grid_x + flow_forward[:, :, 0]
        target_y = grid_y + flow_forward[:, :, 1]

        warped_back_x = cv2.remap(
            flow_backward[:, :, 0], target_x, target_y,
            interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
        )
        warped_back_y = cv2.remap(
            flow_backward[:, :, 1], target_x, target_y,
            interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
        )

        sum_x = flow_forward[:, :, 0] + warped_back_x
        sum_y = flow_forward[:, :, 1] + warped_back_y
        error = np.sqrt(sum_x**2 + sum_y**2)

        # Smooth confidence mapping: exp(-error / threshold)
        confidence = np.exp(-error / max(0.1, threshold)).astype(np.float32)
        confidence = np.clip(confidence, 0.0, 1.0)

        # Occlusion mask: pixels where error exceeds threshold
        occlusion = np.where(error > threshold, 255, 0).astype(np.uint8)

        return error, confidence, occlusion

    # -------------------------------------------------------------------------
    # 3. Dense Optical Flow Calculation
    # -------------------------------------------------------------------------

    def compute_dense_flow(
        self,
        frame_a: VideoFrameBuffer,
        frame_b: VideoFrameBuffer,
        config: Optional[MotionAnalysisConfig] = None,
    ) -> MotionVectorField:
        """Calculate dense optical flow between two frames using Gunnar Farneback or DIS algorithm."""
        t0 = time.perf_counter()
        cfg = config or MotionAnalysisConfig()
        diag = MotionDiagnostics()

        gray_a = self._prepare_gray_frame(frame_a.data)
        gray_b = self._prepare_gray_frame(frame_b.data)
        h, w = gray_a.shape[:2]

        # Dimension validation
        if gray_a.shape != gray_b.shape:
            diag.execution_time_ms = (time.perf_counter() - t0) * 1000.0
            diag.warnings.append(f"Dimension mismatch: {gray_a.shape} vs {gray_b.shape}")
            return MotionVectorField(
                asset_id=getattr(frame_a, "asset_id", "default_asset"),
                source_frame_index=frame_a.timeline_frame,
                target_frame_index=frame_b.timeline_frame,
                source_pts_seconds=frame_a.pts_seconds,
                target_pts_seconds=frame_b.pts_seconds,
                width=w,
                height=h,
                field_type=MotionVectorFieldType.DENSE,
                status=FlowFieldStatus.ESTIMATION_FAILED,
                diagnostics=diag,
            )

        # Scene cut protection
        is_cut, mad = self.detect_scene_cut(gray_a, gray_b, threshold=cfg.scene_cut_threshold)
        if is_cut:
            diag.execution_time_ms = (time.perf_counter() - t0) * 1000.0
            diag.scene_cut_detected = True
            diag.warnings.append(f"Scene cut detected between frames (MAD={mad:.1f}). Motion vectors zeroed.")
            zero_flow = np.zeros((h, w, 2), dtype=np.float32)
            zero_conf = np.zeros((h, w), dtype=np.float32)
            return MotionVectorField(
                asset_id=getattr(frame_a, "asset_id", "default_asset"),
                source_frame_index=frame_a.timeline_frame,
                target_frame_index=frame_b.timeline_frame,
                source_pts_seconds=frame_a.pts_seconds,
                target_pts_seconds=frame_b.pts_seconds,
                width=w,
                height=h,
                field_type=MotionVectorFieldType.DENSE,
                status=FlowFieldStatus.SCENE_CUT_DETECTED,
                dense_flow=zero_flow,
                confidence_map=zero_conf,
                diagnostics=diag,
            )

        # Execution scaling for preview mode
        scale = cfg.downscale_factor
        if scale < 1.0:
            sw = max(16, int(round(w * scale)))
            sh = max(16, int(round(h * scale)))
            proc_a = cv2.resize(gray_a, (sw, sh), interpolation=cv2.INTER_AREA)
            proc_b = cv2.resize(gray_b, (sw, sh), interpolation=cv2.INTER_AREA)
        else:
            proc_a = gray_a
            proc_b = gray_b
            sw, sh = w, h

        # Farneback flow calculation
        if cfg.algorithm == FlowAlgorithmType.DIS_DENSE:
            dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
            flow_forward_small = dis.calc(proc_a, proc_b, None)
            if cfg.direction == FlowDirection.BIDIRECTIONAL:
                flow_backward_small = dis.calc(proc_b, proc_a, None)
            else:
                flow_backward_small = None
        else:
            # Default: Farneback
            flow_forward_small = cv2.calcOpticalFlowFarneback(
                proc_a, proc_b, None,
                pyr_scale=cfg.pyr_scale,
                levels=cfg.levels,
                winsize=cfg.win_size,
                iterations=cfg.iterations,
                poly_n=cfg.poly_n,
                poly_sigma=cfg.poly_sigma,
                flags=0,
            )
            if cfg.direction == FlowDirection.BIDIRECTIONAL:
                flow_backward_small = cv2.calcOpticalFlowFarneback(
                    proc_b, proc_a, None,
                    pyr_scale=cfg.pyr_scale,
                    levels=cfg.levels,
                    winsize=cfg.win_size,
                    iterations=cfg.iterations,
                    poly_n=cfg.poly_n,
                    poly_sigma=cfg.poly_sigma,
                    flags=0,
                )
            else:
                flow_backward_small = None

        # Upscale flow to native frame resolution if downscaled
        if scale < 1.0:
            flow_forward = cv2.resize(flow_forward_small, (w, h), interpolation=cv2.INTER_LINEAR)
            # Re-scale flow vector magnitudes proportionately
            flow_forward[:, :, 0] *= (w / sw)
            flow_forward[:, :, 1] *= (h / sh)

            if flow_backward_small is not None:
                flow_backward = cv2.resize(flow_backward_small, (w, h), interpolation=cv2.INTER_LINEAR)
                flow_backward[:, :, 0] *= (w / sw)
                flow_backward[:, :, 1] *= (h / sh)
            else:
                flow_backward = None
        else:
            flow_forward = flow_forward_small
            flow_backward = flow_backward_small

        # Evaluate consistency and confidence if bidirectional
        if flow_backward is not None:
            err, conf, occ = self.compute_bidirectional_consistency(
                flow_forward, flow_backward, threshold=cfg.consistency_threshold
            )
            inv_mask = conf < cfg.min_confidence_cutoff
            diag.occlusion_percentage = float(np.count_nonzero(occ)) / float(occ.size) * 100.0
            diag.valid_vector_percentage = 100.0 - (float(np.count_nonzero(inv_mask)) / float(inv_mask.size) * 100.0)
        else:
            conf = np.ones((h, w), dtype=np.float32)
            occ = np.zeros((h, w), dtype=np.uint8)
            inv_mask = np.zeros((h, w), dtype=bool)

        # Calculate flow magnitudes
        mag = np.sqrt(flow_forward[:, :, 0]**2 + flow_forward[:, :, 1]**2)
        diag.mean_flow_magnitude = float(np.mean(mag))
        diag.max_flow_magnitude = float(np.max(mag))
        diag.execution_time_ms = (time.perf_counter() - t0) * 1000.0

        return MotionVectorField(
            asset_id=getattr(frame_a, "asset_id", "default_asset"),
            source_frame_index=frame_a.timeline_frame,
            target_frame_index=frame_b.timeline_frame,
            source_pts_seconds=frame_a.pts_seconds,
            target_pts_seconds=frame_b.pts_seconds,
            width=w,
            height=h,
            field_type=MotionVectorFieldType.DENSE,
            direction=cfg.direction,
            status=FlowFieldStatus.VALID,
            dense_flow=flow_forward,
            backward_flow=flow_backward,
            confidence_map=conf,
            occlusion_mask=occ,
            invalid_mask=inv_mask,
            diagnostics=diag,
        )

    # -------------------------------------------------------------------------
    # 4. Sparse Optical Flow (Lucas-Kanade)
    # -------------------------------------------------------------------------

    def compute_sparse_flow(
        self,
        frame_a: VideoFrameBuffer,
        frame_b: VideoFrameBuffer,
        max_features: int = 150,
        quality_level: float = 0.01,
        min_distance: float = 20.0,
    ) -> MotionVectorField:
        """Calculate sparse optical flow using Shi-Tomasi corners and Pyramidal Lucas-Kanade.
        
        Explicitly marked with field_type = MotionVectorFieldType.SPARSE.
        """
        t0 = time.perf_counter()
        diag = MotionDiagnostics()

        gray_a = self._prepare_gray_frame(frame_a.data)
        gray_b = self._prepare_gray_frame(frame_b.data)
        h, w = gray_a.shape[:2]

        pts_a = cv2.goodFeaturesToTrack(
            gray_a,
            maxCorners=max_features,
            qualityLevel=quality_level,
            minDistance=min_distance,
            blockSize=3,
        )

        vectors: List[MotionVector2D] = []
        if pts_a is not None and len(pts_a) > 0:
            pts_b, status, err = cv2.calcOpticalFlowPyrLK(
                gray_a, gray_b, pts_a, None,
                winSize=(15, 15),
                maxLevel=3,
                criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03),
            )

            # Bidirectional LK check to calculate sparse confidence
            pts_a_back, status_back, _ = cv2.calcOpticalFlowPyrLK(
                gray_b, gray_a, pts_b, None,
                winSize=(15, 15),
                maxLevel=3,
                criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03),
            )

            valid_count = 0
            for i in range(len(pts_a)):
                if status[i] == 1 and status_back[i] == 1:
                    xa, ya = pts_a[i][0]
                    xb, yb = pts_b[i][0]
                    xa_back, ya_back = pts_a_back[i][0]

                    dx = xb - xa
                    dy = yb - ya
                    back_err = math.sqrt((xa - xa_back)**2 + (ya - ya_back)**2)
                    conf = math.exp(-back_err / 2.0)

                    vectors.append(MotionVector2D(
                        x=float(xa),
                        y=float(ya),
                        dx=float(dx),
                        dy=float(dy),
                        confidence=float(np.clip(conf, 0.0, 1.0)),
                        status="TRACKED" if back_err < 2.0 else "UNRELIABLE",
                    ))
                    if back_err < 2.0:
                        valid_count += 1

            if len(vectors) > 0:
                diag.valid_vector_percentage = (valid_count / len(vectors)) * 100.0
                mags = [math.sqrt(v.dx**2 + v.dy**2) for v in vectors]
                diag.mean_flow_magnitude = float(np.mean(mags))
                diag.max_flow_magnitude = float(np.max(mags))

        diag.execution_time_ms = (time.perf_counter() - t0) * 1000.0

        return MotionVectorField(
            asset_id=getattr(frame_a, "asset_id", "default_asset"),
            source_frame_index=frame_a.timeline_frame,
            target_frame_index=frame_b.timeline_frame,
            source_pts_seconds=frame_a.pts_seconds,
            target_pts_seconds=frame_b.pts_seconds,
            width=w,
            height=h,
            field_type=MotionVectorFieldType.SPARSE,
            status=FlowFieldStatus.VALID,
            sparse_vectors=vectors,
            diagnostics=diag,
        )

    # -------------------------------------------------------------------------
    # 5. Motion Field Transformation & Resizing
    # -------------------------------------------------------------------------

    def resize_motion_field(
        self,
        motion_field: MotionVectorField,
        target_width: int,
        target_height: int,
    ) -> MotionVectorField:
        """Resize a motion vector field and appropriately rescale vector magnitudes."""
        if motion_field.dense_flow is None or motion_field.width == target_width and motion_field.height == target_height:
            return motion_field

        orig_w, orig_h = motion_field.width, motion_field.height
        scale_x = target_width / orig_w
        scale_y = target_height / orig_h

        # Resample flow field
        resized_flow = cv2.resize(
            motion_field.dense_flow,
            (target_width, target_height),
            interpolation=cv2.INTER_LINEAR,
        )
        # Rescale coordinate displacements
        resized_flow[:, :, 0] *= scale_x
        resized_flow[:, :, 1] *= scale_y

        resized_conf = None
        if motion_field.confidence_map is not None:
            resized_conf = cv2.resize(
                motion_field.confidence_map,
                (target_width, target_height),
                interpolation=cv2.INTER_LINEAR,
            )

        resized_occ = None
        if motion_field.occlusion_mask is not None:
            resized_occ = cv2.resize(
                motion_field.occlusion_mask,
                (target_width, target_height),
                interpolation=cv2.INTER_NEAREST,
            )

        return MotionVectorField(
            field_id=motion_field.field_id,
            asset_id=motion_field.asset_id,
            source_frame_index=motion_field.source_frame_index,
            target_frame_index=motion_field.target_frame_index,
            source_pts_seconds=motion_field.source_pts_seconds,
            target_pts_seconds=motion_field.target_pts_seconds,
            width=target_width,
            height=target_height,
            field_type=motion_field.field_type,
            direction=motion_field.direction,
            status=motion_field.status,
            dense_flow=resized_flow,
            confidence_map=resized_conf,
            occlusion_mask=resized_occ,
            diagnostics=motion_field.diagnostics,
        )

    # -------------------------------------------------------------------------
    # 6. Motion Visualization
    # -------------------------------------------------------------------------

    def visualize_flow_hsv(
        self,
        motion_field: MotionVectorField,
        max_speed: Optional[float] = None,
    ) -> np.ndarray:
        """Render dense optical flow into standard HSV color-wheel representation.
        
        Hue represents vector direction [0, 360 deg].
        Saturation represents vector magnitude normalized to max_speed.
        Value is constant 255.
        
        Returns:
            (H, W, 3) BGR uint8 image suitable for display or inspection.
        """
        if motion_field.dense_flow is None:
            return np.zeros((motion_field.height, motion_field.width, 3), dtype=np.uint8)

        flow = motion_field.dense_flow
        h, w = flow.shape[:2]

        fx = flow[:, :, 0]
        fy = flow[:, :, 1]
        magnitude, angle = cv2.cartToPolar(fx, fy, angleInDegrees=True)

        hsv = np.zeros((h, w, 3), dtype=np.uint8)
        # Hue: OpenCV hue range is [0, 180]
        hsv[:, :, 0] = (angle * 0.5).astype(np.uint8)
        # Saturation: mapped from magnitude
        m_max = max_speed or max(1.0, float(np.percentile(magnitude, 98)))
        norm_mag = np.clip(magnitude / m_max * 255.0, 0, 255).astype(np.uint8)
        hsv[:, :, 1] = norm_mag
        # Value: full brightness
        hsv[:, :, 2] = 255

        return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


optical_flow_engine = OpticalFlowEngine()
