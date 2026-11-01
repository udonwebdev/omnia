"""OMNIA Video Studio — Video Motion Analysis & Trajectory Estimation Engine (Module 21).

Coordinates:
- Frame decoding and Shi-Tomasi feature detection (cv2.goodFeaturesToTrack).
- Lucas-Kanade sparse optical flow tracking (cv2.calcOpticalFlowPyrLK).
- Robust 2D affine / partial-affine RANSAC motion estimation (cv2.estimateAffinePartial2D).
- Automatic scene-cut detection and tracking failure isolation.
- Trajectory persistence and caching by asset ID.
"""

import os
import math
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple

import cv2
import numpy as np

from video_studio.stabilization_models import (
    MotionModelType,
    MotionTransform,
    FrameMotionRecord,
    MotionAnalysisReport,
)

logger = logging.getLogger("omnia.video_studio.motion_analysis")


class MotionAnalysisEngine:
    """Core computer vision engine estimating inter-frame camera motion."""

    def __init__(self):
        # Cache of completed motion analysis reports: {asset_id: MotionAnalysisReport}
        self._analysis_cache: Dict[str, MotionAnalysisReport] = {}

    def analyze_asset_motion(
        self,
        file_path: str,
        asset_id: str,
        motion_model: MotionModelType = MotionModelType.SIMILARITY,
        max_features: int = 200,
        cancel_check: Optional[Any] = None,
    ) -> MotionAnalysisReport:
        """Decodes source video, tracks features, and estimates inter-frame camera transforms."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Video file not found for motion analysis: '{file_path}'.")

        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open media file '{file_path}' for feature tracking.")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if total_frames <= 0:
            total_frames = 1

        frame_records: List[FrameMotionRecord] = []
        scene_cuts: List[int] = []
        has_tracking_failure = False

        # Read first frame
        ret, prev_frame = cap.read()
        if not ret:
            cap.release()
            raise RuntimeError(f"Unable to read initial frame from '{file_path}'.")

        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        prev_pts = cv2.goodFeaturesToTrack(
            prev_gray,
            maxCorners=max_features,
            qualityLevel=0.01,
            minDistance=30,
            blockSize=3,
        )

        # Initial frame (frame 0) has identity transform
        frame_records.append(FrameMotionRecord(
            frame_index=0,
            transform=MotionTransform(dx=0.0, dy=0.0, rotation_rad=0.0, scale=1.0),
            feature_count=len(prev_pts) if prev_pts is not None else 0,
            confidence_score=1.0,
            is_scene_cut=False,
            tracking_lost=False,
        ))

        frame_idx = 1
        confidences = [1.0]

        try:
            while True:
                if cancel_check and cancel_check():
                    logger.info(f"Motion analysis cancelled at frame {frame_idx}.")
                    break

                ret, curr_frame = cap.read()
                if not ret:
                    break

                curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)

                # Ensure sufficient feature points exist
                if prev_pts is None or len(prev_pts) < 10:
                    prev_pts = cv2.goodFeaturesToTrack(
                        prev_gray,
                        maxCorners=max_features,
                        qualityLevel=0.01,
                        minDistance=30,
                        blockSize=3,
                    )

                curr_pts, status, err = None, None, None
                if prev_pts is not None and len(prev_pts) > 0:
                    curr_pts, status, err = cv2.calcOpticalFlowPyrLK(
                        prev_gray, curr_gray, prev_pts, None
                    )

                # Filter valid tracked feature pairs
                valid_prev = []
                valid_curr = []
                if curr_pts is not None and status is not None:
                    valid_prev = prev_pts[status == 1]
                    valid_curr = curr_pts[status == 1]

                is_cut = False
                tracking_lost = False
                conf = 1.0
                transform = MotionTransform()

                # If tracking severely drops (less than 6 features), treat as scene cut or tracking failure
                if len(valid_prev) < 6:
                    is_cut = True
                    tracking_lost = True
                    conf = 0.0
                    has_tracking_failure = True
                    scene_cuts.append(frame_idx)
                    # Reset features from current frame
                    prev_pts = cv2.goodFeaturesToTrack(
                        curr_gray,
                        maxCorners=max_features,
                        qualityLevel=0.01,
                        minDistance=30,
                        blockSize=3,
                    )
                else:
                    # Estimate Affine / Partial 2D Transform using RANSAC
                    matrix, inliers = cv2.estimateAffinePartial2D(
                        valid_prev, valid_curr, method=cv2.RANSAC, ransacReprojThreshold=3.0
                    )

                    if matrix is not None:
                        dx = float(matrix[0, 2])
                        dy = float(matrix[1, 2])
                        cos_a = float(matrix[0, 0])
                        sin_a = float(matrix[1, 0])
                        scale = float(math.sqrt(cos_a * cos_a + sin_a * sin_a))
                        angle = float(math.atan2(sin_a, cos_a))

                        # Check for anomalous jumps (scene cut heuristic)
                        if abs(dx) > (w * 0.4) or abs(dy) > (h * 0.4):
                            is_cut = True
                            scene_cuts.append(frame_idx)
                            dx, dy, angle, scale = 0.0, 0.0, 0.0, 1.0

                        # Outlier ratio confidence
                        inlier_count = int(np.sum(inliers)) if inliers is not None else len(valid_prev)
                        conf = min(1.0, max(0.1, inlier_count / float(max(1, len(valid_prev)))))

                        transform = MotionTransform(
                            dx=dx,
                            dy=dy,
                            rotation_rad=angle,
                            scale=scale,
                        )
                    else:
                        tracking_lost = True
                        conf = 0.1

                    # Re-seed features if count drops low
                    if inliers is not None and np.sum(inliers) < 25:
                        prev_pts = cv2.goodFeaturesToTrack(
                            curr_gray,
                            maxCorners=max_features,
                            qualityLevel=0.01,
                            minDistance=30,
                            blockSize=3,
                        )
                    else:
                        prev_pts = valid_curr[inliers.flatten() == 1].reshape(-1, 1, 2) if inliers is not None else valid_curr.reshape(-1, 1, 2)

                frame_records.append(FrameMotionRecord(
                    frame_index=frame_idx,
                    transform=transform,
                    feature_count=len(valid_prev),
                    confidence_score=conf,
                    is_scene_cut=is_cut,
                    tracking_lost=tracking_lost,
                ))
                confidences.append(conf)

                prev_gray = curr_gray
                frame_idx += 1

        finally:
            cap.release()

        report_id = f"mrep_{uuid.uuid4().hex[:8]}"
        report = MotionAnalysisReport(
            report_id=report_id,
            asset_id=asset_id,
            total_frames=len(frame_records),
            motion_model=motion_model,
            frame_records=frame_records,
            average_confidence=float(np.mean(confidences)) if confidences else 1.0,
            scene_cut_frames=scene_cuts,
            has_tracking_failure=has_tracking_failure,
            analyzed_width=w,
            analyzed_height=h,
        )
        self._analysis_cache[asset_id] = report
        logger.info(f"Completed motion analysis for asset '{asset_id}': {len(frame_records)} frames tracked.")
        return report

    def get_cached_report(self, asset_id: str) -> Optional[MotionAnalysisReport]:
        return self._analysis_cache.get(asset_id)

    def clear_cache(self, asset_id: Optional[str] = None) -> None:
        if asset_id:
            self._analysis_cache.pop(asset_id, None)
        else:
            self._analysis_cache.clear()


# Global singleton
motion_analysis_engine = MotionAnalysisEngine()
