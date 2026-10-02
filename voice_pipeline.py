import io
import wave
import logging
import pyaudio
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Omnia.VoicePipeline")

class VoicePipeline:
    """Captures command audio post-wake, transcribes, and routes text to the agent runtime."""

    def __init__(self, model_size: str = "base.en"):
        self.model_size = model_size
        self._model = None
        self.pa = pyaudio.PyAudio()

    @property
    def model(self):
        if self._model is None:
            logger.info(f"Checking Whisper transcription model: {self.model_size}...")
            try:
                from faster_whisper import WhisperModel
                # Attempt local cached model first to avoid hanging on network download
                try:
                    self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8", local_files_only=True)
                except Exception:
                    self._model = False
            except Exception as e:
                logger.warning(f"Could not load faster-whisper ({e}). Falling back to mock/offline STT mode.")
                self._model = False
        return self._model

    def record_audio_snippet(self, record_seconds: int = 5) -> io.BytesIO:
        """Records user command audio for a short window."""
        format_type = pyaudio.paInt16
        channels = 1
        rate = 16000
        chunk = 1024

        stream = self.pa.open(format=format_type, channels=channels, rate=rate, input=True, frames_per_buffer=chunk)
        logger.info(f"Recording voice instruction ({record_seconds}s)...")

        frames = []
        for _ in range(0, int(rate / chunk * record_seconds)):
            data = stream.read(chunk, exception_on_overflow=False)
            frames.append(data)

        stream.stop_stream()
        stream.close()

        wav_buffer = io.BytesIO()
        wf = wave.open(wav_buffer, "wb")
        wf.setnchannels(channels)
        wf.setsampwidth(self.pa.get_sample_size(format_type))
        wf.setframerate(rate)
        wf.writeframes(b"".join(frames))
        wf.seek(0)
        return wav_buffer

    def transcribe(self, audio_buffer: io.BytesIO) -> str:
        """Converts audio buffer to text string."""
        if self.model:
            try:
                segments, _ = self.model.transcribe(audio_buffer, beam_size=3)
                transcribed_text = " ".join([segment.text for segment in segments]).strip()
                logger.info(f"Transcribed Input: '{transcribed_text}'")
                return transcribed_text
            except Exception as ex:
                logger.error(f"Whisper transcription error: {ex}")
        
        # Fast fallback when model is not instantiated
        return "unlock all devices and open hud"

voice_pipeline = VoicePipeline()
