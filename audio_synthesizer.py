import asyncio
import io
import logging
from typing import AsyncGenerator
import edge_tts
from pydub import AudioSegment
from audio_transcoder import audio_transcoder

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Omnia.AudioSynthesizer")

class AudioSynthesizer:
    """Streams neural text-to-speech audio chunks directly from text inputs."""

    def __init__(self, voice: str = "en-US-ChristopherNeural"):
        self.voice = voice

    async def stream_audio_pcm(self, text: str) -> AsyncGenerator[bytes, None]:
        """Synthesizes text and yields audio stream chunks."""
        communicate = edge_tts.Communicate(text, self.voice)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    async def synthesize_to_bytes(self, text: str) -> bytes:
        """Synthesizes full text to raw MP3 byte payload."""
        communicate = edge_tts.Communicate(text, self.voice)
        audio_buffer = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_buffer.extend(chunk["data"])
        return bytes(audio_buffer)

    async def synthesize_for_telephony(self, text: str) -> bytes:
        """Synthesizes text and converts directly to 8kHz mu-law for phone streams."""
        raw_audio = await self.synthesize_to_bytes(text)
        try:
            # Decode MP3 to raw PCM using pydub
            seg = AudioSegment.from_file(io.BytesIO(raw_audio), format="mp3")
            seg = seg.set_channels(1).set_frame_rate(16000).set_sample_width(2)
            pcm_bytes = seg.raw_data
            return audio_transcoder.pcm_to_mulaw(pcm_bytes, in_rate=16000)
        except Exception as e:
            logger.warning(f"Telephony transcoding fallback ({e})")
            return audio_transcoder.pcm_to_mulaw(raw_audio, in_rate=16000)

audio_synth = AudioSynthesizer()
