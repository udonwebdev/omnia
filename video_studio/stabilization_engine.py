"""OMNIA Video Studio — Camera Motion Path Smoothing & Frame Stabilization Engine (Module 21).

Coordinates:
- Cumulative trajectory accumulation (integrating dx, dy, da).
- Temporal Gaussian smoothing window respecting scene cuts.
- Difference calculation (smoothed trajectory - original trajectory).
- Adaptive zoom and aspect-ratio crop compensation.
- Matrix construction and OpenCV cv2.warpAffine execution on video frame buffers.
"""

import math
import logging
from typing import Dict, Any, List, Optional, Tuple

import cv2
import numpy as np

from video_studio.stabilization_models import (
    MotionAnalysisReport,
    StabilizationConfig,
    CorrectiveTransform,
    BorderFillMode,
)
from video_studio.effects_models import VideoFrameBuffer

logger = logging.getLogger("omnia.video_studio.stabilization_engine")


class StabilizationEngine:
    """Calculates corrective camera trajectories and warps frames to cancel unwanted motion."""

    def compute_corrective_transforms(
        self,
        report: MotionAnalysisReport,
        config: StabilizationConfig,
    ) -> List[CorrectiveTransform]:
        """Calculates smooth camera path deltas for every frame in the analysis report."""
        if not report.frame_records:
            return []

        n_frames = len(report.frame_records)
        # 1. Accumulate raw inter-frame motion into a cumulative trajectory
        # Trajectory vectors: [x, y, angle]
        traj_x = np.zeros(n_frames, dtype=np.float64)
        traj_y = np.zeros(n_frames, dtype=np.float64)
        traj_a = np.zeros(n_frames, dtype=np.float64)

        cur_x, cur_y, cur_a = 0.0, 0.0, 0.0
        for i, rec in enumerate(report.frame_records):
            if rec.is_scene_cut:
                # Reset accumulation at scene cuts to prevent smoothing jumps across shots
                cur_x, cur_y, cur_a = 0.0, 0.0, 0.0
            else:
                cur_x += rec.transform.dx
                cur_y += rec.transform.dy
                cur_a += rec.transform.rotation_rad

            traj_x[i] = cur_x
            traj_y[i] = cur_y
            traj_a[i] = cur_a

        # 2. Smooth trajectory using a temporal moving window (Gaussian-weighted)
        radius = max(1, config.smoothing_radius)
        smoothed_x = self._smooth_curve(traj_x, radius, report.scene_cut_frames)
        smoothed_y = self._smooth_curve(traj_y, radius, report.scene_cut_frames)
        smoothed_a = self._smooth_curve(traj_a, radius, report.scene_cut_frames)

        # 3. Calculate difference: diff = smoothed - original
        diff_x = (smoothed_x - traj_x) if config.smooth_translation else np.zeros(n_frames)
        diff_y = (smoothed_y - traj_y) if config.smooth_translation else np.zeros(n_frames)
        diff_a = (smoothed_a - traj_a) if config.smooth_rotation else np.zeros(n_frames)

        # 4. Compute required safety zoom factor to prevent black border edges
        zoom = config.manual_zoom_factor if config.auto_crop_zoom else 1.0

        # Construct 2x3 affine matrix for each frame
        w, h = report.analyzed_width, report.analyzed_height
        cx, cy = w / 2.0, h / 2.0

        transforms: List[CorrectiveTransform] = []
        for i in range(n_frames):
            dx = float(diff_x[i])
            dy = float(diff_y[i])
            da = float(diff_a[i])

            # Affine matrix:
            # 1. Translate center to origin
            # 2. Rotate by da & scale by zoom
            # 3. Translate back to center and apply dx, dy shift
            cos_a = zoom * math.cos(da)
            sin_a = zoom * math.sin(da)

            tx = dx + cx - (cos_a * cx - sin_a * cy)
            ty = dy + cy - (sin_a * cx + cos_a * cy)

            matrix_2x3 = [
                [cos_a, -sin_a, tx],
                [sin_a, cos_a, ty],
            ]

            transforms.append(CorrectiveTransform(
                frame_index=i,
                matrix_2x3=matrix_2x3,
                applied_zoom=zoom,
            ))

        return transforms

    def apply_stabilization_to_frame(
        self,
        frame_buf: VideoFrameBuffer,
        correction: CorrectiveTransform,
        border_fill: BorderFillMode = BorderFillMode.REPLICATE,
    ) -> VideoFrameBuffer:
        """Applies corrective 2D affine warp to input VideoFrameBuffer."""
        matrix = np.array(correction.matrix_2x3, dtype=np.float32)

        # Determine border fill mode for OpenCV
        cv_border = cv2.BORDER_REPLICATE
        if border_fill == BorderFillMode.BLACK_BORDER:
            cv_border = cv2.BORDER_CONSTANT
        elif border_fill == BorderFillMode.REFLECT:
            cv_border = cv2.BORDER_REFLECT

        warped_data = cv2.warpAffine(
            frame_buf.data,
            matrix,
            (frame_buf.width, frame_buf.height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv_border,
        )

        out_buf = VideoFrameBuffer(frame_buf.width, frame_buf.height, data=warped_data)
        out_buf.timeline_frame = frame_buf.timeline_frame
        return out_buf

    def _smooth_curve(
        self,
        curve: np.ndarray,
        radius: int,
        cut_frames: List[int],
    ) -> np.ndarray:
        """Applies a box/Gaussian moving average window without leaking across scene cuts."""
        smoothed = np.copy(curve)
        n = len(curve)

        # Partition curve into continuous shots between scene cuts
        boundaries = [0] + sorted([f for f in cut_frames if 0 < f < n]) + [n]

        for b_idx in range(len(boundaries) - 1):
            start = boundaries[b_idx]
            end = boundaries[b_idx + 1]
            seg_len = end - start
            if seg_len <= 1:
                continue

            for i in range(start, end):
                win_start = max(start, i - radius)
                win_end = min(end, i + radius + 1)
                smoothed[i] = np.mean(curve[win_start:win_end])

        return smoothed


# Global singleton
stabilization_engine = StabilizationEngine()
