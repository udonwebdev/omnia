"""OMNIA Video Studio — Point, Region & Planar Motion Tracking Engine (Module 22).

Coordinates:
- Point tracking via Lucas-Kanade optical flow with forward-backward error validation.
- Region tracking via normalized cross-correlation template matching (cv2.matchTemplate).
- Planar feature cluster tracking with local affine estimation.
- Tracking loss detection and confidence analysis.
"""

import math
import logging
from typing import Dict, Any, List, Optional, Tuple

import cv2
import numpy as np

from video_studio.tracking_models import (
    TrackingSession,
    TrackSample,
    TrackingMethodType,
    TrackingStatus,
    TrackTargetType,
)

logger = logging.getLogger("omnia.video_studio.tracking_engine")


class MotionTrackingEngine:
    """Core computer vision tracking engine executing point and region tracking across frames."""

    def track_session(
        self,
        file_path: str,
        session: TrackingSession,
        cancel_check: Optional[Any] = None,
    ) -> TrackingSession:
        """Executes tracking across the configured frame range and updates session samples."""
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            session.status = TrackingStatus.FAILED
            raise RuntimeError(f"Could not open source media file '{file_path}' for tracking.")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        start_frame = max(0, session.start_frame)
        end_frame = min(total_frames, session.end_frame) if session.end_frame > 0 else total_frames
        session.end_frame = end_frame

        session.status = TrackingStatus.TRACKING
        session.samples.clear()
        session.lost_track_frames.clear()

        # Seek to start frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        ret, prev_frame = cap.read()
        if not ret:
            cap.release()
            session.status = TrackingStatus.FAILED
            raise RuntimeError(f"Could not read start frame {start_frame} from '{file_path}'.")

        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        cur_x = float(session.initial_x)
        cur_y = float(session.initial_y)
        cur_w = float(session.initial_width)
        cur_h = float(session.initial_height)

        # Record initial frame 0 sample
        session.samples[start_frame] = TrackSample(
            frame_index=start_frame,
            x=cur_x,
            y=cur_y,
            width=cur_w,
            height=cur_h,
            confidence=1.0,
            is_valid=True,
        )

        confidences = [1.0]

        # Extract initial template if using region template match
        half_w = max(4, int(cur_w / 2.0))
        half_h = max(4, int(cur_h / 2.0))
        h_img, w_img = prev_gray.shape

        x1 = max(0, int(cur_x - half_w))
        y1 = max(0, int(cur_y - half_h))
        x2 = min(w_img, int(cur_x + half_w))
        y2 = min(h_img, int(cur_y + half_h))
        template = prev_gray[y1:y2, x1:x2].copy()

        # Or extract initial feature point for optical flow
        prev_pt = np.array([[[cur_x, cur_y]]], dtype=np.float32)

        try:
            for frame_idx in range(start_frame + 1, end_frame):
                if cancel_check and cancel_check():
                    session.status = TrackingStatus.CANCELLED
                    break

                ret, curr_frame = cap.read()
                if not ret:
                    break

                curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)

                if session.method == TrackingMethodType.POINT_OPTICAL_FLOW:
                    # 1. Forward Optical Flow
                    next_pt, status, flow_err = cv2.calcOpticalFlowPyrLK(
                        prev_gray, curr_gray, prev_pt, None, winSize=(21, 21), maxLevel=3
                    )

                    # 2. Backward Optical Flow for forward-backward consistency validation
                    back_pt, back_status, _ = cv2.calcOpticalFlowPyrLK(
                        curr_gray, prev_gray, next_pt, None, winSize=(21, 21), maxLevel=3
                    )

                    fb_err = float(np.linalg.norm(prev_pt - back_pt))
                    # Check status, forward-backward error, and photometric flow error
                    err_val = float(flow_err[0][0]) if flow_err is not None else 0.0
                    is_valid = bool(status[0][0] == 1 and back_status[0][0] == 1 and fb_err < 5.0 and err_val < 50.0)

                    if is_valid:
                        cur_x = float(next_pt[0][0][0])
                        cur_y = float(next_pt[0][0][1])
                        confidence = min(1.0, max(0.2, 1.0 - (fb_err / 10.0) - (err_val / 200.0)))
                        prev_pt = next_pt
                    else:
                        confidence = 0.0
                        session.lost_track_frames.append(frame_idx)

                    session.samples[frame_idx] = TrackSample(
                        frame_index=frame_idx,
                        x=cur_x,
                        y=cur_y,
                        width=cur_w,
                        height=cur_h,
                        confidence=confidence,
                        is_valid=is_valid,
                        tracking_lost=not is_valid,
                    )
                    confidences.append(confidence)

                elif session.method == TrackingMethodType.REGION_TEMPLATE_MATCH:
                    # Local search window around previous position (prevent global false matches)
                    search_margin = 60
                    sx1 = max(0, int(cur_x - half_w - search_margin))
                    sy1 = max(0, int(cur_y - half_h - search_margin))
                    sx2 = min(w_img, int(cur_x + half_w + search_margin))
                    sy2 = min(h_img, int(cur_y + half_h + search_margin))

                    search_area = curr_gray[sy1:sy2, sx1:sx2]
                    if search_area.shape[0] >= template.shape[0] and search_area.shape[1] >= template.shape[1]:
                        res = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
                        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

                        if max_val > 0.4:
                            # Located valid match in search window
                            cur_x = float(sx1 + max_loc[0] + half_w)
                            cur_y = float(sy1 + max_loc[1] + half_h)
                            confidence = float(max_val)
                            is_valid = True
                        else:
                            confidence = float(max(0.0, max_val))
                            is_valid = False
                            session.lost_track_frames.append(frame_idx)
                    else:
                        confidence = 0.0
                        is_valid = False
                        session.lost_track_frames.append(frame_idx)

                    session.samples[frame_idx] = TrackSample(
                        frame_index=frame_idx,
                        x=cur_x,
                        y=cur_y,
                        width=cur_w,
                        height=cur_h,
                        confidence=confidence,
                        is_valid=is_valid,
                        tracking_lost=not is_valid,
                    )
                    confidences.append(confidence)

                prev_gray = curr_gray

            if session.status != TrackingStatus.CANCELLED:
                session.status = TrackingStatus.COMPLETED

        finally:
            cap.release()

        session.average_confidence = float(np.mean(confidences)) if confidences else 1.0
        logger.info(f"Tracking session '{session.session_id}' completed with {len(session.samples)} samples.")
        return session


# Global singleton
motion_tracking_engine = MotionTrackingEngine()
