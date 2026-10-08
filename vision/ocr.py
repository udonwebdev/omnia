import io
import logging
from typing import List, Dict, Any, Optional
from PIL import Image
import numpy as np

from vision.models import VisionFrame, BoundingBox

logger = logging.getLogger("Omnia.Vision.OCR")

class OCREngine:
    """Pluggable OCR engine capable of extracting text and coordinate boxes."""

    def __init__(self):
        self._rapid_ocr = None
        self._initialized = False

    def _get_engine(self):
        if not self._initialized:
            try:
                from rapidocr_onnxruntime import RapidOCR
                self._rapid_ocr = RapidOCR()
                logger.info("RapidOCR local ONNX engine initialized successfully.")
            except Exception as e:
                logger.warning(f"Failed to load RapidOCR ({e}).")
                self._rapid_ocr = None
            self._initialized = True
        return self._rapid_ocr

    def extract_text_regions(self, frame: VisionFrame) -> List[Dict[str, Any]]:
        """Processes frame image and returns list of detected text boxes with confidences."""
        engine = self._get_engine()
        if not engine:
            logger.warning("No local OCR engine available.")
            return []

        try:
            pil_img = Image.open(io.BytesIO(frame.raw_bytes)).convert("RGB")
            img_arr = np.array(pil_img)
            
            ocr_results, _ = engine(img_arr)
            if not ocr_results:
                return []

            regions = []
            f_w, f_h = frame.width, frame.height

            for item in ocr_results:
                # Format: [box_points, text, confidence]
                # box_points is [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
                box_pts = item[0]
                text = str(item[1]).strip()
                confidence = float(item[2])

                # Extract min/max bounds
                xs = [p[0] for p in box_pts]
                ys = [p[1] for p in box_pts]
                min_x, max_x = min(xs), max(xs)
                min_y, max_y = min(ys), max(ys)

                px = int(round(min_x))
                py = int(round(min_y))
                pw = int(round(max_x - min_x))
                ph = int(round(max_y - min_y))

                bbox = BoundingBox.from_pixels(px, py, pw, ph, f_w, f_h)

                regions.append({
                    "text": text,
                    "confidence": confidence,
                    "bounding_box": bbox,
                    "pixels": (px, py, pw, ph)
                })

            return regions

        except Exception as ex:
            logger.error(f"Error during OCR execution: {ex}")
            return []

ocr_engine = OCREngine()
