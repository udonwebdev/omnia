"""OMNIA Video Studio — LUT Parser, Validator & Trilinear Interpolation (Module 16).

Handles:
- .cube format parsing (1D and 3D LUTs).
- Domain and dimension validation.
- Safe trilinear interpolation applying 3D LUTs to float32 image buffers.
- Intensity blending between original and graded pixels.
"""

from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import logging

from video_studio.color_models import LUTDescriptor, LUTType

logger = logging.getLogger("omnia.video_studio.color_lut")

class LUTParser:
    """Parses and validates Adobe / DaVinci Resolve .cube Look-Up Table files."""

    @staticmethod
    def parse_cube_content(content: str, lut_id: str, name: str = "Imported LUT") -> LUTDescriptor:
        """Parses the text of a .cube file safely."""
        lines = content.strip().splitlines()
        lut_type = LUTType.LUT_3D
        size = 0
        data_points: List[List[float]] = []
        domain_min = [0.0, 0.0, 0.0]
        domain_max = [1.0, 1.0, 1.0]

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            tag = parts[0].upper()

            if tag == "TITLE":
                name = " ".join(parts[1:]).strip('"')
            elif tag == "LUT_3D_SIZE":
                lut_type = LUTType.LUT_3D
                size = int(parts[1])
            elif tag == "LUT_1D_SIZE":
                lut_type = LUTType.LUT_1D
                size = int(parts[1])
            elif tag == "DOMAIN_MIN":
                domain_min = [float(x) for x in parts[1:4]]
            elif tag == "DOMAIN_MAX":
                domain_max = [float(x) for x in parts[1:4]]
            else:
                # Expect numeric triplets
                if len(parts) >= 3:
                    try:
                        r, g, b = float(parts[0]), float(parts[1]), float(parts[2])
                        data_points.append([r, g, b])
                    except ValueError:
                        continue

        if size <= 0:
            raise ValueError("Malformed .cube LUT: missing or invalid LUT_3D_SIZE / LUT_1D_SIZE.")

        expected_count = size ** 3 if lut_type == LUTType.LUT_3D else size
        if len(data_points) < expected_count:
            raise ValueError(f"Incomplete LUT data: expected {expected_count} entries, found {len(data_points)}.")

        table = np.array(data_points[:expected_count], dtype=np.float32)
        if lut_type == LUTType.LUT_3D:
            # Reshape standard order (R fastest, then G, then B) -> (size, size, size, 3)
            # where index order is [B, G, R]
            table = table.reshape((size, size, size, 3))

        return LUTDescriptor(
            lut_id=lut_id,
            name=name,
            lut_type=lut_type,
            size=size,
            data=table,
        )


class LUTProcessor:
    """Applies 1D and 3D LUT tables to float32 RGB buffers with trilinear interpolation."""

    @staticmethod
    def apply_lut(rgb_buffer: np.ndarray, lut: LUTDescriptor) -> np.ndarray:
        """Applies a LUTDescriptor to a float32 RGB buffer with shape (H, W, 3)."""
        if not lut.is_enabled or lut.data is None or lut.intensity <= 1e-4:
            return rgb_buffer

        table = lut.data
        intensity = max(0.0, min(1.0, float(lut.intensity)))

        if lut.lut_type == LUTType.LUT_3D:
            graded = LUTProcessor._trilinear_interpolate_3d(rgb_buffer, table, lut.size)
        else:
            graded = LUTProcessor._interpolate_1d(rgb_buffer, table, lut.size)

        if abs(intensity - 1.0) < 1e-4:
            return graded
        else:
            return (rgb_buffer * (1.0 - intensity) + graded * intensity).astype(np.float32)

    @staticmethod
    def _interpolate_1d(rgb: np.ndarray, table: np.ndarray, size: int) -> np.ndarray:
        """Applies 1D LUT table via linear interpolation per channel."""
        clamped = np.clip(rgb, 0.0, 1.0) * (size - 1)
        idx_low = np.floor(clamped).astype(np.int32)
        idx_high = np.clip(idx_low + 1, 0, size - 1)
        weight = clamped - idx_low

        out = np.zeros_like(rgb)
        for ch in range(3):
            val_low = table[idx_low[:, :, ch], ch]
            val_high = table[idx_high[:, :, ch], ch]
            out[:, :, ch] = val_low * (1.0 - weight[:, :, ch]) + val_high * weight[:, :, ch]
        return out

    @staticmethod
    def _trilinear_interpolate_3d(rgb: np.ndarray, table: np.ndarray, size: int) -> np.ndarray:
        """Trilinear interpolation in 3D LUT cube: table ordered as [b, g, r, ch]."""
        clamped = np.clip(rgb, 0.0, 1.0) * (size - 1)
        r = clamped[:, :, 0]
        g = clamped[:, :, 1]
        b = clamped[:, :, 2]

        r0 = np.floor(r).astype(np.int32)
        r1 = np.clip(r0 + 1, 0, size - 1)
        dr = (r - r0)[:, :, np.newaxis]

        g0 = np.floor(g).astype(np.int32)
        g1 = np.clip(g0 + 1, 0, size - 1)
        dg = (g - g0)[:, :, np.newaxis]

        b0 = np.floor(b).astype(np.int32)
        b1 = np.clip(b0 + 1, 0, size - 1)
        db = (b - b0)[:, :, np.newaxis]

        # 8 cube corners
        c000 = table[b0, g0, r0]
        c100 = table[b0, g0, r1]
        c010 = table[b0, g1, r0]
        c110 = table[b0, g1, r1]
        c001 = table[b1, g0, r0]
        c101 = table[b1, g0, r1]
        c011 = table[b1, g1, r0]
        c111 = table[b1, g1, r1]

        # Interpolate along R
        c00 = c000 * (1.0 - dr) + c100 * dr
        c10 = c010 * (1.0 - dr) + c110 * dr
        c01 = c001 * (1.0 - dr) + c101 * dr
        c11 = c011 * (1.0 - dr) + c111 * dr

        # Interpolate along G
        c0 = c00 * (1.0 - dg) + c10 * dg
        c1 = c01 * (1.0 - dg) + c11 * dg

        # Interpolate along B
        return (c0 * (1.0 - db) + c1 * db).astype(np.float32)

# Global singleton
lut_processor = LUTProcessor()
