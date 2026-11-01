"""OMNIA Video Studio — Audio Subsystem Domain Models & Buffer Contracts (Module 9).

Defines:
- SampleTime & RationalAudioTime: Sample-accurate time mapping and conversion.
- AudioChannelLayout: MONO, STEREO, SURROUND_5_1 (explicit conversion policy).
- AudioSampleFormat: FLOAT32 (internal engine standard), INT16, INT24.
- AudioBuffer: In-memory planar or interleaved float32 sample buffer with arithmetic operations.
- AudioBusType: TRACK, SUBMIX, AUX, MASTER.
- AudioBus: Bus routing definition, gain, pan, mute, solo, and processor chain.
- AudioRoutingGraph: Track-to-bus and bus-to-bus routing with cycle detection.
- AudioMeterSnapshot: Peak (dBFS), RMS (dBFS), true clip detection per channel.
- AudioDeviceDescriptor: Hardware output reporting with headless support.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Set
import math
import time
import uuid
import numpy as np

# ==============================================================================
# 1. Enums & Format Descriptors
# ==============================================================================

class AudioChannelLayout(str, Enum):
    MONO = "MONO"
    STEREO = "STEREO"
    SURROUND_5_1 = "SURROUND_5_1"

    @property
    def channel_count(self) -> int:
        if self == AudioChannelLayout.MONO:
            return 1
        elif self == AudioChannelLayout.STEREO:
            return 2
        elif self == AudioChannelLayout.SURROUND_5_1:
            return 6
        return 2

class AudioSampleFormat(str, Enum):
    FLOAT32 = "FLOAT32"
    INT16 = "INT16"
    INT24 = "INT24"

class AudioBusType(str, Enum):
    TRACK = "TRACK"
    SUBMIX = "SUBMIX"
    AUX = "AUX"
    MASTER = "MASTER"

class PanningLaw(str, Enum):
    EQUAL_POWER_3DB = "EQUAL_POWER_3DB"
    LINEAR = "LINEAR"

# ==============================================================================
# 2. Sample-Accurate Timing Abstraction
# ==============================================================================

@dataclass(frozen=True)
class SampleTime:
    """Sample-accurate integer position avoiding IEEE 754 floating drift."""
    sample_index: int = 0
    sample_rate: int = 48000

    def to_seconds(self) -> float:
        return self.sample_index / max(1, self.sample_rate)

    def to_timeline_frame(self, fps: float) -> int:
        """Converts audio sample index to sequence integer frame."""
        # Rational: sample_index * fps / sample_rate
        return int(round((self.sample_index * fps) / self.sample_rate))

    @classmethod
    def from_timeline_frame(cls, frame: int, fps: float, sample_rate: int = 48000) -> "SampleTime":
        """Converts sequence integer frame to precise start sample index."""
        # Exact integer calculation: floor or round
        sample_idx = int(round((frame * sample_rate) / max(0.001, fps)))
        return cls(sample_index=sample_idx, sample_rate=sample_rate)

    @classmethod
    def from_seconds(cls, seconds: float, sample_rate: int = 48000) -> "SampleTime":
        return cls(sample_index=int(round(seconds * sample_rate)), sample_rate=sample_rate)

# ==============================================================================
# 3. Audio Buffer Contract
# ==============================================================================

@dataclass
class AudioBuffer:
    """Canonical in-memory multi-channel audio buffer.
    
    Internal representation: float32 NumPy array with shape (channels, samples).
    Values nominally in [-1.0, 1.0], but floating point headroom allows intermediate values > 1.0.
    """
    sample_rate: int = 48000
    layout: AudioChannelLayout = AudioChannelLayout.STEREO
    data: np.ndarray = field(default_factory=lambda: np.zeros((2, 0), dtype=np.float32))
    start_sample: int = 0

    def __post_init__(self):
        if not isinstance(self.data, np.ndarray):
            self.data = np.asarray(self.data, dtype=np.float32)
        if self.data.ndim == 1:
            # Reshape 1D mono to (1, N)
            self.data = self.data.reshape(1, -1)
        if self.data.dtype != np.float32:
            self.data = self.data.astype(np.float32)

    @property
    def channels(self) -> int:
        return self.data.shape[0]

    @property
    def samples(self) -> int:
        return self.data.shape[1]

    @property
    def duration_seconds(self) -> float:
        return self.samples / max(1, self.sample_rate)

    @classmethod
    def silence(cls, samples: int, channels: int = 2, sample_rate: int = 48000, start_sample: int = 0) -> "AudioBuffer":
        layout = AudioChannelLayout.MONO if channels == 1 else (AudioChannelLayout.STEREO if channels == 2 else AudioChannelLayout.SURROUND_5_1)
        data = np.zeros((channels, samples), dtype=np.float32)
        return cls(sample_rate=sample_rate, layout=layout, data=data, start_sample=start_sample)

    def copy(self) -> "AudioBuffer":
        return AudioBuffer(
            sample_rate=self.sample_rate,
            layout=self.layout,
            data=np.copy(self.data),
            start_sample=self.start_sample,
        )

    def apply_gain(self, gain_linear: float) -> None:
        """Scales all channels in-place by a linear gain factor."""
        self.data *= float(gain_linear)

    def apply_gain_ramp(self, start_gain: float, end_gain: float) -> None:
        """Applies a smooth linear gain ramp to eliminate audio clicks across buffers."""
        if self.samples == 0:
            return
        ramp = np.linspace(start_gain, end_gain, self.samples, dtype=np.float32)
        self.data *= ramp

    def apply_panning(self, pan: float, law: PanningLaw = PanningLaw.EQUAL_POWER_3DB) -> None:
        """Applies stereo panning in-place.
        pan: -1.0 (Full Left) to 1.0 (Full Right), 0.0 (Center).
        Using 3dB Equal-Power law:
        L = cos((pan + 1) * pi / 4), R = sin((pan + 1) * pi / 4).
        """
        pan = max(-1.0, min(1.0, pan))
        if self.channels != 2:
            return

        if law == PanningLaw.EQUAL_POWER_3DB:
            angle = (pan + 1.0) * (math.pi / 4.0)
            gain_l = math.cos(angle)
            gain_r = math.sin(angle)
        else: # Linear
            gain_l = max(0.0, 1.0 - pan) / 2.0 if pan > 0 else 1.0
            gain_r = max(0.0, 1.0 + pan) / 2.0 if pan < 0 else 1.0

        self.data[0, :] *= gain_l
        self.data[1, :] *= gain_r

    def mix_into(self, target: "AudioBuffer", gain: float = 1.0) -> None:
        """Sums this buffer's samples into target buffer with channel adaptation."""
        samples_to_mix = min(self.samples, target.samples)
        if samples_to_mix <= 0:
            return

        src_ch = self.channels
        tgt_ch = target.channels

        if src_ch == tgt_ch:
            target.data[:, :samples_to_mix] += self.data[:, :samples_to_mix] * gain
        elif src_ch == 1 and tgt_ch == 2:
            # Mono to Stereo: Dual mono with -3dB gain compensation
            mono_gain = gain * (1.0 / math.sqrt(2.0))
            target.data[0, :samples_to_mix] += self.data[0, :samples_to_mix] * mono_gain
            target.data[1, :samples_to_mix] += self.data[0, :samples_to_mix] * mono_gain
        elif src_ch == 2 and tgt_ch == 1:
            # Stereo to Mono: (L + R) * 0.5 * gain
            downmix = (self.data[0, :samples_to_mix] + self.data[1, :samples_to_mix]) * 0.5 * gain
            target.data[0, :samples_to_mix] += downmix
        else:
            # Fallback channel mapping
            min_ch = min(src_ch, tgt_ch)
            target.data[:min_ch, :samples_to_mix] += self.data[:min_ch, :samples_to_mix] * gain

    def to_int16_bytes(self, clamp: bool = True) -> bytes:
        """Converts float32 audio to interleaved 16-bit PCM signed bytes."""
        clipped = np.clip(self.data, -1.0, 1.0) if clamp else self.data
        int_data = (clipped * 32767.0).astype(np.int16)
        # Interleave: (channels, samples) -> (samples, channels) -> bytes
        interleaved = np.ascontiguousarray(int_data.T)
        return interleaved.tobytes()

    @classmethod
    def from_int16_bytes(cls, pcm_bytes: bytes, channels: int = 2, sample_rate: int = 48000, start_sample: int = 0) -> "AudioBuffer":
        """Decodes interleaved 16-bit PCM bytes into float32 AudioBuffer."""
        if not pcm_bytes:
            return cls.silence(0, channels, sample_rate, start_sample)
        arr = np.frombuffer(pcm_bytes, dtype=np.int16)
        samples = len(arr) // channels
        arr = arr[:samples * channels].reshape((samples, channels)).T
        float_data = (arr / 32767.0).astype(np.float32)
        layout = AudioChannelLayout.MONO if channels == 1 else AudioChannelLayout.STEREO
        return cls(sample_rate=sample_rate, layout=layout, data=float_data, start_sample=start_sample)

# ==============================================================================
# 4. Metering & Analysis Contracts
# ==============================================================================

@dataclass
class AudioMeterSnapshot:
    """Accurate sample peak and RMS levels derived from real audio buffers."""
    peak_linear: List[float]
    peak_db: List[float]
    rms_linear: List[float]
    rms_db: List[float]
    is_clipped: List[bool]
    timestamp: float = field(default_factory=time.time)

    @classmethod
    def calculate(cls, buffer: AudioBuffer) -> "AudioMeterSnapshot":
        if buffer.samples == 0:
            return cls(
                peak_linear=[0.0] * buffer.channels,
                peak_db=[-120.0] * buffer.channels,
                rms_linear=[0.0] * buffer.channels,
                rms_db=[-120.0] * buffer.channels,
                is_clipped=[False] * buffer.channels,
            )

        peaks = []
        peaks_db = []
        rms_vals = []
        rms_dbs = []
        clipped = []

        for ch in range(buffer.channels):
            ch_data = buffer.data[ch, :]
            pk = float(np.max(np.abs(ch_data))) if len(ch_data) > 0 else 0.0
            peaks.append(pk)
            # dBFS calculation: 20 * log10(peak)
            pk_db = 20.0 * math.log10(max(1e-6, pk))
            peaks_db.append(max(-120.0, pk_db))

            # RMS
            rms = float(np.sqrt(np.mean(ch_data ** 2))) if len(ch_data) > 0 else 0.0
            rms_vals.append(rms)
            rms_db = 20.0 * math.log10(max(1e-6, rms))
            rms_dbs.append(max(-120.0, rms_db))

            clipped.append(pk >= 0.9999)

        return cls(
            peak_linear=peaks,
            peak_db=peaks_db,
            rms_linear=rms_vals,
            rms_db=rms_dbs,
            is_clipped=clipped,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "peak_linear": [round(x, 4) for x in self.peak_linear],
            "peak_db": [round(x, 2) for x in self.peak_db],
            "rms_linear": [round(x, 4) for x in self.rms_linear],
            "rms_db": [round(x, 2) for x in self.rms_db],
            "is_clipped": self.is_clipped,
            "timestamp": self.timestamp,
        }

# ==============================================================================
# 5. Audio Bus & Routing Models
# ==============================================================================

@dataclass
class AudioBus:
    """An audio submix or output bus with level, pan, mute, solo, and processor chain."""
    bus_id: str
    name: str
    bus_type: AudioBusType = AudioBusType.SUBMIX
    layout: AudioChannelLayout = AudioChannelLayout.STEREO
    gain_db: float = 0.0
    pan: float = 0.0 # -1.0 to 1.0
    is_muted: bool = False
    is_solo: bool = False
    target_bus_id: Optional[str] = None # None means Master output
    processors: List[Dict[str, Any]] = field(default_factory=list)
    meter: Optional[AudioMeterSnapshot] = None

    @property
    def gain_linear(self) -> float:
        if self.gain_db <= -120.0:
            return 0.0
        return 10.0 ** (self.gain_db / 20.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bus_id": self.bus_id,
            "name": self.name,
            "bus_type": self.bus_type.value,
            "layout": self.layout.value,
            "gain_db": self.gain_db,
            "pan": self.pan,
            "is_muted": self.is_muted,
            "is_solo": self.is_solo,
            "target_bus_id": self.target_bus_id,
            "processors_count": len(self.processors),
        }

@dataclass
class AudioRoutingGraph:
    """Manages audio track-to-bus and bus-to-bus routing with cycle detection."""
    buses: Dict[str, AudioBus] = field(default_factory=dict)
    track_routes: Dict[str, str] = field(default_factory=dict) # track_id -> bus_id

    def add_bus(self, bus: AudioBus) -> None:
        self.buses[bus.bus_id] = bus

    def route_track(self, track_id: str, bus_id: str) -> bool:
        if bus_id not in self.buses:
            raise ValueError(f"Target bus '{bus_id}' does not exist.")
        self.track_routes[track_id] = bus_id
        return True

    def route_bus(self, source_bus_id: str, target_bus_id: Optional[str]) -> bool:
        if source_bus_id not in self.buses:
            raise ValueError(f"Source bus '{source_bus_id}' not found.")
        if target_bus_id and target_bus_id not in self.buses:
            raise ValueError(f"Target bus '{target_bus_id}' not found.")
        if target_bus_id == source_bus_id:
            raise ValueError("Direct bus feedback cycle: bus cannot route into itself.")

        # Cycle validation
        visited = set()
        curr = target_bus_id
        while curr:
            if curr == source_bus_id:
                raise ValueError(f"Cyclic routing detected between bus '{source_bus_id}' and '{target_bus_id}'.")
            visited.add(curr)
            curr = self.buses[curr].target_bus_id

        self.buses[source_bus_id].target_bus_id = target_bus_id
        return True

# ==============================================================================
# 6. Audio Device & Hardware Discovery
# ==============================================================================

@dataclass
class AudioDeviceDescriptor:
    device_id: str
    name: str
    is_default: bool = False
    is_output: bool = True
    max_channels: int = 2
    supported_sample_rates: List[int] = field(default_factory=lambda: [44100, 48000, 96000])
    is_available: bool = True
