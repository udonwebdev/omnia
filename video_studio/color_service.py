"""OMNIA Video Studio — Color Grading & Look Development Service (Module 16).

Manages:
- Clip-level, track-level, and sequence-level ColorGradeDocuments.
- Reusable creative Looks and Look presets (e.g. Cinematic Warm, Teal & Orange, Monochrome Noir).
- LUT library management (.cube import, caching, and intensity adjustment).
- Real-time scope measurement dispatching.
- Capability registry integration for Module 1.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging
import uuid
import time

from video_studio.color_models import (
    ColorGradeDocument,
    PrimaryGrade,
    LiftGammaGain,
    WheelBalance,
    ColorCurves,
    CurvePoint,
    HSLQualifier,
    LUTDescriptor,
    ColorScopeData,
    ColorSpace,
)
from video_studio.color_pipeline import color_pipeline_processor, ColorPipelineProcessor
from video_studio.color_lut import lut_processor, LUTParser, LUTProcessor
from video_studio.compositing_models import VideoFrameBuffer

logger = logging.getLogger("omnia.video_studio.color_service")

class ColorService:
    """Central service managing video color grading, looks, and scopes."""

    def __init__(
        self,
        processor: Optional[ColorPipelineProcessor] = None,
    ):
        self.processor = processor or color_pipeline_processor
        # Active grade documents per clip: {item_id: ColorGradeDocument}
        self._clip_grades: Dict[str, ColorGradeDocument] = {}
        # Reusable looks catalog: {look_id: ColorGradeDocument}
        self._looks: Dict[str, ColorGradeDocument] = {}
        # Imported LUT library: {lut_id: LUTDescriptor}
        self._luts: Dict[str, LUTDescriptor] = {}
        self._init_built_in_looks()

    def _init_built_in_looks(self) -> None:
        """Initializes a focused set of real, non-destructive cinematic looks."""
        # 1. Warm Golden Hour
        warm = ColorGradeDocument(
            grade_id="look_golden_hour",
            name="Golden Hour",
            primary=PrimaryGrade(temperature=35.0, tint=5.0, contrast=1.1, saturation=1.15),
            wheels=LiftGammaGain(
                lift=WheelBalance(r=0.02, g=-0.01, b=-0.03, master=-0.02),
                gain=WheelBalance(r=0.05, g=0.02, b=-0.04, master=0.03),
            ),
        )
        self._looks[warm.grade_id] = warm

        # 2. Teal & Orange
        teal_orange = ColorGradeDocument(
            grade_id="look_teal_orange",
            name="Teal & Orange",
            primary=PrimaryGrade(contrast=1.15, saturation=1.1),
            wheels=LiftGammaGain(
                lift=WheelBalance(r=-0.04, g=0.01, b=0.05, master=-0.01), # Teal shadows
                gain=WheelBalance(r=0.06, g=0.02, b=-0.05, master=0.02),  # Orange highlights
            ),
        )
        self._looks[teal_orange.grade_id] = teal_orange

        # 3. Noir High-Contrast Monochrome
        noir = ColorGradeDocument(
            grade_id="look_noir",
            name="Monochrome Noir",
            primary=PrimaryGrade(contrast=1.35, saturation=0.0, highlights=-10.0, shadows=-15.0),
        )
        self._looks[noir.grade_id] = noir

    # ==========================================================================
    # 1. Grade Document Lifecycle
    # ==========================================================================

    def get_clip_grade(self, item_id: str) -> ColorGradeDocument:
        """Retrieves or lazily instantiates a ColorGradeDocument for a timeline item."""
        if item_id not in self._clip_grades:
            self._clip_grades[item_id] = ColorGradeDocument(
                grade_id=f"grade_{uuid.uuid4().hex[:8]}",
                name=f"Clip Grade {item_id[:6]}",
            )
        return self._clip_grades[item_id]

    def update_clip_grade(self, item_id: str, grade: ColorGradeDocument) -> ColorGradeDocument:
        grade.revision += 1
        grade.updated_at = time.time()
        self._clip_grades[item_id] = grade
        return grade

    def reset_clip_grade(self, item_id: str) -> ColorGradeDocument:
        grade = ColorGradeDocument(
            grade_id=f"grade_{uuid.uuid4().hex[:8]}",
            name="Reset Grade",
        )
        self._clip_grades[item_id] = grade
        return grade

    # ==========================================================================
    # 2. Look Preset Application & Custom Looks
    # ==========================================================================

    def list_looks(self) -> List[Dict[str, Any]]:
        return [l.to_dict() for l in self._looks.values()]

    def apply_look_to_clip(self, look_id: str, item_id: str) -> Optional[ColorGradeDocument]:
        look = self._looks.get(look_id)
        if not look:
            return None

        # Deep clone look into active clip grade
        cloned_grade = ColorGradeDocument(
            grade_id=f"grade_{uuid.uuid4().hex[:8]}",
            name=f"{look.name} (Applied)",
            source_color_space=look.source_color_space,
            working_color_space=look.working_color_space,
            primary=PrimaryGrade(**look.primary.to_dict()),
            wheels=LiftGammaGain(
                lift=WheelBalance(**look.wheels.lift.to_dict()),
                gamma=WheelBalance(**look.wheels.gamma.to_dict()),
                gain=WheelBalance(**look.wheels.gain.to_dict()),
                offset=WheelBalance(**look.wheels.offset.to_dict()),
            ),
            curves=ColorCurves(
                master=[CurvePoint(p.x, p.y) for p in look.curves.master],
                red=[CurvePoint(p.x, p.y) for p in look.curves.red],
                green=[CurvePoint(p.x, p.y) for p in look.curves.green],
                blue=[CurvePoint(p.x, p.y) for p in look.curves.blue],
            ),
            hsl_qualifier=HSLQualifier(**look.hsl_qualifier.to_dict()),
            lut=look.lut,
            is_enabled=True,
        )
        self._clip_grades[item_id] = cloned_grade
        return cloned_grade

    def save_clip_as_look(self, item_id: str, look_name: str) -> ColorGradeDocument:
        grade = self.get_clip_grade(item_id)
        look_id = f"look_{uuid.uuid4().hex[:8]}"
        look = ColorGradeDocument(
            grade_id=look_id,
            name=look_name,
            primary=PrimaryGrade(**grade.primary.to_dict()),
            wheels=LiftGammaGain(
                lift=WheelBalance(**grade.wheels.lift.to_dict()),
                gamma=WheelBalance(**grade.wheels.gamma.to_dict()),
                gain=WheelBalance(**grade.wheels.gain.to_dict()),
                offset=WheelBalance(**grade.wheels.offset.to_dict()),
            ),
            curves=ColorCurves(
                master=[CurvePoint(p.x, p.y) for p in grade.curves.master],
                red=[CurvePoint(p.x, p.y) for p in grade.curves.red],
                green=[CurvePoint(p.x, p.y) for p in grade.curves.green],
                blue=[CurvePoint(p.x, p.y) for p in grade.curves.blue],
            ),
            hsl_qualifier=HSLQualifier(**grade.hsl_qualifier.to_dict()),
            lut=grade.lut,
        )
        self._looks[look_id] = look
        return look

    # ==========================================================================
    # 3. LUT Import & Assignment
    # ==========================================================================

    def import_cube_lut(self, lut_name: str, cube_content: str) -> LUTDescriptor:
        lut_id = f"lut_{uuid.uuid4().hex[:8]}"
        lut = LUTParser.parse_cube_content(cube_content, lut_id=lut_id, name=lut_name)
        self._luts[lut_id] = lut
        return lut

    def attach_lut_to_clip(self, item_id: str, lut_id: str, intensity: float = 1.0) -> bool:
        lut = self._luts.get(lut_id)
        if not lut:
            return False

        grade = self.get_clip_grade(item_id)
        lut_copy = LUTDescriptor(
            lut_id=lut.lut_id,
            name=lut.name,
            lut_type=lut.lut_type,
            size=lut.size,
            intensity=intensity,
            is_enabled=True,
            data=lut.data,
        )
        grade.lut = lut_copy
        self.update_clip_grade(item_id, grade)
        return True

    # ==========================================================================
    # 4. Capability Registry
    # ==========================================================================

    def register_capabilities(self) -> None:
        """Registers Module 16 color grading capabilities into OMNIA Video Studio registry."""
        try:
            from video_studio.registry import video_studio_capability_registry
            from video_studio.registry_models import (
                VideoStudioCapabilityDescriptor,
                VideoStudioCategory,
                ImplementationState,
            )
            caps = [
                VideoStudioCapabilityDescriptor(
                    id="video.color.primary",
                    name="Primary Color Correction",
                    description="Exposure, contrast, temperature, tint, lift, gamma, gain grading.",
                    category=VideoStudioCategory.COLOR,
                    implementation_state=ImplementationState.IMPLEMENTED,
                    tags=["color", "primary", "exposure", "white_balance"],
                ),
                VideoStudioCapabilityDescriptor(
                    id="video.color.curves",
                    name="Color Curves Engine",
                    description="Parametric RGB and luma spline curves.",
                    category=VideoStudioCategory.COLOR,
                    implementation_state=ImplementationState.IMPLEMENTED,
                    tags=["color", "curves"],
                ),
                VideoStudioCapabilityDescriptor(
                    id="video.color.lut_processor",
                    name="3D LUT Engine",
                    description="3D .cube Look-Up Table parser with trilinear interpolation.",
                    category=VideoStudioCategory.COLOR,
                    implementation_state=ImplementationState.IMPLEMENTED,
                    tags=["color", "lut", "cube"],
                ),
                VideoStudioCapabilityDescriptor(
                    id="video.color.scopes",
                    name="Real-Time Color Scopes",
                    description="Decoded frame histogram, waveform, vectorscope, and RGB parade.",
                    category=VideoStudioCategory.COLOR,
                    implementation_state=ImplementationState.IMPLEMENTED,
                    tags=["color", "scopes", "waveform", "vectorscope"],
                ),
                VideoStudioCapabilityDescriptor(
                    id="video.color.hsl_qualifier",
                    name="HSL Secondary Qualifier",
                    description="Secondary hue, saturation, and luminance mask selection.",
                    category=VideoStudioCategory.COLOR,
                    implementation_state=ImplementationState.IMPLEMENTED,
                    tags=["color", "hsl", "secondary"],
                ),
            ]
            for c in caps:
                try:
                    video_studio_capability_registry.register(c, auth_token="core")
                except Exception as e:
                    logger.debug(f"Capability '{c.id}' registration note: {e}")
        except Exception as ex:
            logger.debug(f"Capabilities registry not available: {ex}")

# Global singleton
color_service = ColorService()
color_service.register_capabilities()
