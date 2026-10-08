from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
import time
import uuid

class VisionSource(Enum):
    DESKTOP = "desktop"
    ANDROID = "android"
    BROWSER = "browser"

class ElementType(Enum):
    TEXT = "text"
    BUTTON = "button"
    INPUT = "input"
    LINK = "link"
    ICON = "icon"
    IMAGE = "image"
    DIALOG = "dialog"
    NAV = "nav"
    MENU = "menu"
    CHECKBOX = "checkbox"
    TOGGLE = "toggle"
    UNKNOWN = "unknown"

class VerificationStatus(Enum):
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    UNCERTAIN = "UNCERTAIN"

@dataclass
class BoundingBox:
    """Represents a normalized bounding box [0.0, 1.0]."""
    x: float
    y: float
    width: float
    height: float

    def to_pixels(self, frame_width: int, frame_height: int) -> Tuple[int, int, int, int]:
        """Converts normalized coordinates to integer pixel coordinates (x, y, w, h)."""
        px = int(round(self.x * frame_width))
        py = int(round(self.y * frame_height))
        pw = int(round(self.width * frame_width))
        ph = int(round(self.height * frame_height))
        return (px, py, pw, ph)

    @classmethod
    def from_pixels(cls, px: int, py: int, pw: int, ph: int, frame_width: int, frame_height: int) -> "BoundingBox":
        """Constructs a normalized bounding box from pixel dimensions."""
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError("Frame dimensions must be positive.")
        return cls(
            x=max(0.0, min(1.0, px / frame_width)),
            y=max(0.0, min(1.0, py / frame_height)),
            width=max(0.0, min(1.0, pw / frame_width)),
            height=max(0.0, min(1.0, ph / frame_height))
        )

    @property
    def center(self) -> Tuple[float, float]:
        """Returns the normalized center (cx, cy)."""
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)

    def center_pixel(self, frame_width: int, frame_height: int) -> Tuple[int, int]:
        """Returns the pixel center (cx, cy)."""
        cx, cy = self.center
        return (int(round(cx * frame_width)), int(round(cy * frame_height)))

@dataclass
class VisionFrame:
    """Strongly typed representation of a validated captured screen."""
    frame_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: VisionSource = VisionSource.DESKTOP
    device_id: Optional[str] = None
    host_id: str = "localhost"
    timestamp: float = field(default_factory=time.time)
    width: int = 0
    height: int = 0
    raw_bytes: bytes = b""
    format: str = "png"
    capture_duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_valid(self) -> Tuple[bool, str]:
        if not self.raw_bytes or len(self.raw_bytes) == 0:
            return False, "Frame bytes are empty"
        if self.width <= 0 or self.height <= 0:
            return False, f"Invalid dimensions: {self.width}x{self.height}"
        return True, "Valid"

@dataclass
class VisionElement:
    """A detected semantic UI element inside a VisionFrame."""
    element_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    element_type: ElementType = ElementType.UNKNOWN
    label: str = ""
    text: str = ""
    confidence: float = 0.0
    bounding_box: BoundingBox = field(default_factory=lambda: BoundingBox(0, 0, 0, 0))
    clickable: bool = True
    visible: bool = True
    enabled: bool = True

@dataclass
class VisionObservation:
    """Aggregated perception output from analyzing a frame."""
    frame: VisionFrame
    elements: List[VisionElement] = field(default_factory=list)
    raw_text: str = ""
    analysis_duration_ms: float = 0.0
    error: Optional[str] = None

@dataclass
class GroundingCandidate:
    """A ranked visual candidate matching a grounding query."""
    element: VisionElement
    rank: int
    score: float
    reason: str

@dataclass
class VisualDiffResult:
    """Structural difference between two frames."""
    changed_pixels_ratio: float
    major_regions_changed: int
    confidence: float
    description: str

@dataclass
class VisionVerification:
    """Result of visual verification comparing pre- and post-action frames."""
    status: VerificationStatus
    strategy: str
    diff: Optional[VisualDiffResult] = None
    expected: str = ""
    observed: str = ""
    reason: str = ""
    pre_frame_id: str = ""
    post_frame_id: str = ""

@dataclass
class VisionRecoveryRequest:
    """Structured hook for higher-level planning recovery."""
    failure_type: str
    expected_state: str
    observed_state: str
    pre_frame: Optional[VisionFrame] = None
    post_frame: Optional[VisionFrame] = None
