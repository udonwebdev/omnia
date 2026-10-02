import audioop
import io
import wave
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Omnia.AudioTranscoder")

class AudioTranscoder:
    """Handles audio transcoding between telephony mu-law (8kHz) and agent linear PCM (16kHz)."""

    @staticmethod
    def mulaw_to_wav_16k(mulaw_bytes: bytes) -> io.BytesIO:
        """Converts raw 8kHz mu-law payload to 16kHz Linear PCM WAV."""
        # Convert 8kHz mu-law to 8kHz linear PCM 16-bit
        pcm_8k = audioop.ulaw2lin(mulaw_bytes, 2)
        # Resample from 8000Hz to 16000Hz
        pcm_16k, _ = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, None)

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(pcm_16k)
        wav_buffer.seek(0)
        return wav_buffer

    @staticmethod
    def pcm_to_mulaw(pcm_bytes: bytes, in_rate: int = 16000) -> bytes:
        """Converts Linear PCM to 8kHz mu-law for telephony playback."""
        if in_rate != 8000:
            pcm_8k, _ = audioop.ratecv(pcm_bytes, 2, 1, in_rate, 8000, None)
        else:
            pcm_8k = pcm_bytes
        return audioop.lin2ulaw(pcm_8k, 2)

audio_transcoder = AudioTranscoder()
