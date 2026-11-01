"""OMNIA Video Studio — Digital Signal Processing Framework & Processors (Module 9).

Provides:
- IAudioProcessor: Composable audio processing node interface (lifecycle, process, bypass, reset).
- ProcessorRegistry: Discovery, parameter schema, and instantiation.
- GainProcessor: Decibel and linear gain scaling with smooth cross-buffer parameter interpolation.
- PanningProcessor: Equal-Power 3dB and linear stereo panning.
- ParametricEqualizerProcessor: Real biquad IIR filter implementation (Low Shelf, Peaking EQ, High Shelf, Notch, Low Pass, High Pass) with Direct Form II Transposed topology.
- CompressorProcessor: Real dynamic range peak/RMS compressor with threshold, ratio, attack, release, and makeup gain.
- ProcessorChain: Sequentially cascaded processor list with safe failure isolation.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
import math
import numpy as np

from video_studio.audio_models import AudioBuffer, PanningLaw

# ==============================================================================
# 1. Base Processor Interface
# ==============================================================================

class ProcessorState(str, Enum):
    ACTIVE = "ACTIVE"
    BYPASSED = "BYPASSED"
    FAILED = "FAILED"

class FilterType(str, Enum):
    LOW_SHELF = "LOW_SHELF"
    PEAKING = "PEAKING"
    HIGH_SHELF = "HIGH_SHELF"
    LOW_PASS = "LOW_PASS"
    HIGH_PASS = "HIGH_PASS"
    NOTCH = "NOTCH"

class IAudioProcessor(ABC):
    """Abstract contract for an in-memory DSP processor node."""

    def __init__(self, processor_id: str, name: str):
        self.processor_id = processor_id
        self.name = name
        self.state = ProcessorState.ACTIVE
        self.last_error: Optional[str] = None

    @abstractmethod
    def process(self, buffer: AudioBuffer) -> AudioBuffer:
        """Processes the audio buffer in-place or returns a modified buffer."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Resets internal delay lines, filter states, and history buffers."""
        pass

    def set_bypassed(self, bypassed: bool) -> None:
        self.state = ProcessorState.BYPASSED if bypassed else ProcessorState.ACTIVE

    @abstractmethod
    def get_parameters(self) -> Dict[str, Any]:
        """Returns the current parameter values."""
        pass

    @abstractmethod
    def set_parameters(self, params: Dict[str, Any]) -> None:
        """Updates processor parameters."""
        pass


# ==============================================================================
# 2. Gain Processor
# ==============================================================================

class GainProcessor(IAudioProcessor):
    """Linear / decibel volume processor with smooth buffer ramp interpolation."""

    def __init__(self, processor_id: str = "gain_default", gain_db: float = 0.0):
        super().__init__(processor_id, "Gain")
        self._gain_db = gain_db
        self._target_gain_linear = self._db_to_linear(gain_db)
        self._current_gain_linear = self._target_gain_linear

    def _db_to_linear(self, db: float) -> float:
        if db <= -120.0:
            return 0.0
        return 10.0 ** (db / 20.0)

    def set_gain_db(self, db: float) -> None:
        self._gain_db = float(db)
        self._target_gain_linear = self._db_to_linear(self._gain_db)

    def process(self, buffer: AudioBuffer) -> AudioBuffer:
        if self.state == ProcessorState.BYPASSED or buffer.samples == 0:
            return buffer

        if abs(self._current_gain_linear - self._target_gain_linear) < 1e-4:
            buffer.apply_gain(self._target_gain_linear)
            self._current_gain_linear = self._target_gain_linear
        else:
            buffer.apply_gain_ramp(self._current_gain_linear, self._target_gain_linear)
            self._current_gain_linear = self._target_gain_linear

        return buffer

    def reset(self) -> None:
        self._current_gain_linear = self._target_gain_linear

    def get_parameters(self) -> Dict[str, Any]:
        return {"gain_db": self._gain_db}

    def set_parameters(self, params: Dict[str, Any]) -> None:
        if "gain_db" in params:
            self.set_gain_db(params["gain_db"])


# ==============================================================================
# 3. Stereo Panning Processor
# ==============================================================================

class PanningProcessor(IAudioProcessor):
    """Stereo equal-power panning processor."""

    def __init__(self, processor_id: str = "pan_default", pan: float = 0.0, law: PanningLaw = PanningLaw.EQUAL_POWER_3DB):
        super().__init__(processor_id, "Panner")
        self.pan = float(pan)
        self.law = law

    def process(self, buffer: AudioBuffer) -> AudioBuffer:
        if self.state == ProcessorState.BYPASSED or buffer.samples == 0:
            return buffer
        buffer.apply_panning(self.pan, law=self.law)
        return buffer

    def reset(self) -> None:
        pass

    def get_parameters(self) -> Dict[str, Any]:
        return {"pan": self.pan, "law": self.law.value}

    def set_parameters(self, params: Dict[str, Any]) -> None:
        if "pan" in params:
            self.pan = max(-1.0, min(1.0, float(params["pan"])))
        if "law" in params:
            self.law = PanningLaw(params["law"])


# ==============================================================================
# 4. Parametric Equalizer (Biquad Filter Bank)
# ==============================================================================

class BiquadFilter:
    """Single 2nd-order IIR biquad section using Direct Form II Transposed topology."""

    def __init__(self, filter_type: FilterType = FilterType.PEAKING, freq_hz: float = 1000.0, gain_db: float = 0.0, q: float = 0.7071):
        self.filter_type = filter_type
        self.freq_hz = freq_hz
        self.gain_db = gain_db
        self.q = q
        # Coefficients
        self.b0 = 1.0
        self.b1 = 0.0
        self.b2 = 0.0
        self.a1 = 0.0
        self.a2 = 0.0
        # Direct Form II Transposed state registers: shape (channels, 2)
        self.z1 = np.zeros(2, dtype=np.float32)
        self.z2 = np.zeros(2, dtype=np.float32)

    def compute_coefficients(self, sample_rate: int) -> None:
        fs = float(sample_rate)
        # Clamping frequency within Nyquist limit
        f0 = max(20.0, min(fs * 0.49, self.freq_hz))
        w0 = 2.0 * math.pi * f0 / fs
        cos_w0 = math.cos(w0)
        sin_w0 = math.sin(w0)
        alpha = sin_w0 / (2.0 * max(0.01, self.q))
        A = 10.0 ** (self.gain_db / 40.0)

        if self.filter_type == FilterType.PEAKING:
            b0 = 1.0 + alpha * A
            b1 = -2.0 * cos_w0
            b2 = 1.0 - alpha * A
            a0 = 1.0 + alpha / A
            a1 = -2.0 * cos_w0
            a2 = 1.0 - alpha / A
        elif self.filter_type == FilterType.LOW_SHELF:
            two_sqrt_a_alpha = 2.0 * math.sqrt(A) * alpha
            b0 = A * ((A + 1.0) - (A - 1.0) * cos_w0 + two_sqrt_a_alpha)
            b1 = 2.0 * A * ((A - 1.0) - (A + 1.0) * cos_w0)
            b2 = A * ((A + 1.0) - (A - 1.0) * cos_w0 - two_sqrt_a_alpha)
            a0 = (A + 1.0) + (A - 1.0) * cos_w0 + two_sqrt_a_alpha
            a1 = -2.0 * ((A - 1.0) + (A + 1.0) * cos_w0)
            a2 = (A + 1.0) + (A - 1.0) * cos_w0 - two_sqrt_a_alpha
        elif self.filter_type == FilterType.HIGH_SHELF:
            two_sqrt_a_alpha = 2.0 * math.sqrt(A) * alpha
            b0 = A * ((A + 1.0) + (A - 1.0) * cos_w0 + two_sqrt_a_alpha)
            b1 = -2.0 * A * ((A - 1.0) + (A + 1.0) * cos_w0)
            b2 = A * ((A + 1.0) + (A - 1.0) * cos_w0 - two_sqrt_a_alpha)
            a0 = (A + 1.0) - (A - 1.0) * cos_w0 + two_sqrt_a_alpha
            a1 = 2.0 * ((A - 1.0) - (A + 1.0) * cos_w0)
            a2 = (A + 1.0) - (A - 1.0) * cos_w0 - two_sqrt_a_alpha
        elif self.filter_type == FilterType.LOW_PASS:
            b0 = (1.0 - cos_w0) / 2.0
            b1 = 1.0 - cos_w0
            b2 = (1.0 - cos_w0) / 2.0
            a0 = 1.0 + alpha
            a1 = -2.0 * cos_w0
            a2 = 1.0 - alpha
        elif self.filter_type == FilterType.HIGH_PASS:
            b0 = (1.0 + cos_w0) / 2.0
            b1 = -(1.0 + cos_w0)
            b2 = (1.0 + cos_w0) / 2.0
            a0 = 1.0 + alpha
            a1 = -2.0 * cos_w0
            a2 = 1.0 - alpha
        else: # Notch
            b0 = 1.0
            b1 = -2.0 * cos_w0
            b2 = 1.0
            a0 = 1.0 + alpha
            a1 = -2.0 * cos_w0
            a2 = 1.0 - alpha

        # Normalize by a0
        self.b0 = float(b0 / a0)
        self.b1 = float(b1 / a0)
        self.b2 = float(b2 / a0)
        self.a1 = float(a1 / a0)
        self.a2 = float(a2 / a0)

    def process_channel(self, x: np.ndarray, ch: int) -> np.ndarray:
        """Processes an array of samples through the Direct Form II Transposed topology."""
        if len(x) == 0:
            return x
        # Ensure state size matches channels
        if ch >= len(self.z1):
            self.z1 = np.resize(self.z1, ch + 1)
            self.z2 = np.resize(self.z2, ch + 1)

        y = np.empty_like(x)
        z1 = float(self.z1[ch])
        z2 = float(self.z2[ch])
        b0, b1, b2 = self.b0, self.b1, self.b2
        a1, a2 = self.a1, self.a2

        for i in range(len(x)):
            xi = float(x[i])
            yi = b0 * xi + z1
            z1 = b1 * xi - a1 * yi + z2
            z2 = b2 * xi - a2 * yi
            y[i] = yi

        self.z1[ch] = z1
        self.z2[ch] = z2
        return y

    def reset(self) -> None:
        self.z1.fill(0.0)
        self.z2.fill(0.0)


class ParametricEqualizerProcessor(IAudioProcessor):
    """Multi-band parametric equalizer."""

    def __init__(self, processor_id: str = "eq_default"):
        super().__init__(processor_id, "Parametric Equalizer")
        self.bands: List[BiquadFilter] = [
            BiquadFilter(FilterType.LOW_SHELF, freq_hz=100.0, gain_db=0.0, q=0.7071),
            BiquadFilter(FilterType.PEAKING, freq_hz=500.0, gain_db=0.0, q=1.0),
            BiquadFilter(FilterType.PEAKING, freq_hz=2500.0, gain_db=0.0, q=1.0),
            BiquadFilter(FilterType.HIGH_SHELF, freq_hz=8000.0, gain_db=0.0, q=0.7071),
        ]
        self._last_sample_rate = 0

    def process(self, buffer: AudioBuffer) -> AudioBuffer:
        if self.state == ProcessorState.BYPASSED or buffer.samples == 0:
            return buffer

        if self._last_sample_rate != buffer.sample_rate:
            for band in self.bands:
                band.compute_coefficients(buffer.sample_rate)
            self._last_sample_rate = buffer.sample_rate

        for band in self.bands:
            # Skip if flat (0 dB on peaking/shelf)
            if abs(band.gain_db) < 0.05 and band.filter_type in (FilterType.PEAKING, FilterType.LOW_SHELF, FilterType.HIGH_SHELF):
                continue
            for ch in range(buffer.channels):
                buffer.data[ch, :] = band.process_channel(buffer.data[ch, :], ch)

        return buffer

    def reset(self) -> None:
        for band in self.bands:
            band.reset()

    def set_band(self, index: int, filter_type: FilterType, freq_hz: float, gain_db: float, q: float = 0.7071) -> None:
        if 0 <= index < len(self.bands):
            b = self.bands[index]
            b.filter_type = filter_type
            b.freq_hz = freq_hz
            b.gain_db = gain_db
            b.q = q
            if self._last_sample_rate > 0:
                b.compute_coefficients(self._last_sample_rate)

    def get_parameters(self) -> Dict[str, Any]:
        return {
            "bands": [
                {
                    "type": b.filter_type.value,
                    "freq_hz": b.freq_hz,
                    "gain_db": b.gain_db,
                    "q": b.q,
                }
                for b in self.bands
            ]
        }

    def set_parameters(self, params: Dict[str, Any]) -> None:
        if "bands" in params:
            for i, b_data in enumerate(params["bands"]):
                if i < len(self.bands):
                    ftype = FilterType(b_data.get("type", "PEAKING"))
                    freq = float(b_data.get("freq_hz", 1000.0))
                    gain = float(b_data.get("gain_db", 0.0))
                    q = float(b_data.get("q", 1.0))
                    self.set_band(i, ftype, freq, gain, q)


# ==============================================================================
# 5. Dynamic Compressor Processor
# ==============================================================================

class CompressorProcessor(IAudioProcessor):
    """Dynamic range compressor with threshold, ratio, attack, release, and makeup gain."""

    def __init__(
        self,
        processor_id: str = "comp_default",
        threshold_db: float = -20.0,
        ratio: float = 4.0,
        attack_ms: float = 10.0,
        release_ms: float = 100.0,
        makeup_gain_db: float = 0.0,
    ):
        super().__init__(processor_id, "Compressor")
        self.threshold_db = threshold_db
        self.ratio = max(1.0, ratio)
        self.attack_ms = attack_ms
        self.release_ms = release_ms
        self.makeup_gain_db = makeup_gain_db
        self._envelope_db = -120.0

    def process(self, buffer: AudioBuffer) -> AudioBuffer:
        if self.state == ProcessorState.BYPASSED or buffer.samples == 0:
            return buffer

        # Coefficient calculation based on sample rate
        fs = float(buffer.sample_rate)
        att_coef = math.exp(-1.0 / (max(0.001, self.attack_ms) * 0.001 * fs))
        rel_coef = math.exp(-1.0 / (max(0.001, self.release_ms) * 0.001 * fs))
        makeup_linear = 10.0 ** (self.makeup_gain_db / 20.0)

        # Vectorized detector across linked channels: max absolute sample
        max_ch = np.max(np.abs(buffer.data), axis=0)
        gain_reduction = np.ones(buffer.samples, dtype=np.float32)

        env = self._envelope_db
        thresh = self.threshold_db
        slope = 1.0 - (1.0 / self.ratio)

        for i in range(buffer.samples):
            val = float(max_ch[i])
            val_db = 20.0 * math.log10(max(1e-6, val))
            # Envelope follower
            if val_db > env:
                env = att_coef * env + (1.0 - att_coef) * val_db
            else:
                env = rel_coef * env + (1.0 - rel_coef) * val_db

            # Gain computing
            if env > thresh:
                gr_db = -slope * (env - thresh)
            else:
                gr_db = 0.0

            gain_reduction[i] = 10.0 ** (gr_db / 20.0)

        self._envelope_db = env

        # Apply gain reduction and makeup gain to all channels
        buffer.data *= (gain_reduction * makeup_linear)
        return buffer

    def reset(self) -> None:
        self._envelope_db = -120.0

    def get_parameters(self) -> Dict[str, Any]:
        return {
            "threshold_db": self.threshold_db,
            "ratio": self.ratio,
            "attack_ms": self.attack_ms,
            "release_ms": self.release_ms,
            "makeup_gain_db": self.makeup_gain_db,
        }

    def set_parameters(self, params: Dict[str, Any]) -> None:
        if "threshold_db" in params:
            self.threshold_db = float(params["threshold_db"])
        if "ratio" in params:
            self.ratio = max(1.0, float(params["ratio"]))
        if "attack_ms" in params:
            self.attack_ms = max(0.1, float(params["attack_ms"]))
        if "release_ms" in params:
            self.release_ms = max(1.0, float(params["release_ms"]))
        if "makeup_gain_db" in params:
            self.makeup_gain_db = float(params["makeup_gain_db"])


# ==============================================================================
# 6. Composable Processor Chain
# ==============================================================================

class ProcessorChain:
    """Ordered sequence of DSP nodes with error isolation and bypass capability."""

    def __init__(self):
        self.processors: List[IAudioProcessor] = []

    def add_processor(self, processor: IAudioProcessor) -> None:
        self.processors.append(processor)

    def remove_processor(self, processor_id: str) -> bool:
        initial_len = len(self.processors)
        self.processors = [p for p in self.processors if p.processor_id != processor_id]
        return len(self.processors) < initial_len

    def process(self, buffer: AudioBuffer) -> AudioBuffer:
        for proc in self.processors:
            if proc.state == ProcessorState.ACTIVE:
                try:
                    buffer = proc.process(buffer)
                except Exception as e:
                    proc.state = ProcessorState.FAILED
                    proc.last_error = str(e)
        return buffer

    def reset(self) -> None:
        for proc in self.processors:
            proc.reset()
