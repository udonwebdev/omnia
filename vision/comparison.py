import io
import logging
from typing import Optional, Tuple
from PIL import Image, ImageChops
import numpy as np

from vision.models import VisionFrame, VisualDiffResult, BoundingBox

logger = logging.getLogger("Omnia.Vision.Comparison")

class ScreenDiffEngine:
    """Compares pre- and post-action visual frames to detect state transitions."""

    @staticmethod
    def _to_pil(frame: VisionFrame) -> Image.Image:
        return Image.open(io.BytesIO(frame.raw_bytes)).convert("RGB")

    def compare_frames(
        self,
        before: VisionFrame,
        after: VisionFrame,
        tolerance_pixel_val: int = 15,
        target_region: Optional[BoundingBox] = None
    ) -> VisualDiffResult:
        """Calculates pixel difference ratio and structural changes between two frames."""
        try:
            img1 = self._to_pil(before)
            img2 = self._to_pil(after)

            # Resize if dimensions differ
            if img1.size != img2.size:
                img2 = img2.resize(img1.size)

            w, h = img1.size
            total_pixels = w * h

            if target_region:
                px, py, pw, ph = target_region.to_pixels(w, h)
                box = (px, py, min(w, px + pw), min(h, py + ph))
                img1 = img1.crop(box)
                img2 = img2.crop(box)
                w, h = img1.size
                total_pixels = w * h

            arr1 = np.array(img1, dtype=np.int16)
            arr2 = np.array(img2, dtype=np.int16)

            # Compute absolute channel difference
            diff_arr = np.abs(arr1 - arr2)
            max_diff = np.max(diff_arr, axis=2)

            # Mask pixels that exceed threshold
            changed_mask = max_diff > tolerance_pixel_val
            changed_pixels = int(np.sum(changed_mask))
            ratio = changed_pixels / max(1, total_pixels)

            # Grid-based analysis to detect major distinct changed regions (e.g., 4x4 grid)
            grid_rows, grid_cols = 4, 4
            cell_h, cell_w = h // grid_rows, w // grid_cols
            major_regions = 0

            for r in range(grid_rows):
                for c in range(grid_cols):
                    cell_mask = changed_mask[r * cell_h:(r + 1) * cell_h, c * cell_w:(c + 1) * cell_w]
                    cell_ratio = np.mean(cell_mask)
                    if cell_ratio > 0.10: # If more than 10% of cell changed
                        major_regions += 1

            confidence = min(1.0, 0.7 + (ratio * 0.3)) if ratio > 0.01 else 0.95

            desc = f"Pixel change: {ratio * 100:.2f}%, {major_regions} major region(s) altered."
            return VisualDiffResult(
                changed_pixels_ratio=ratio,
                major_regions_changed=major_regions,
                confidence=confidence,
                description=desc
            )

        except Exception as e:
            logger.error(f"Frame comparison failure: {e}")
            return VisualDiffResult(
                changed_pixels_ratio=0.0,
                major_regions_changed=0,
                confidence=0.0,
                description=f"Comparison error: {e}"
            )

diff_engine = ScreenDiffEngine()
