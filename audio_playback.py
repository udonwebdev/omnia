import io
import asyncio
import logging
import pyaudio
from pydub import AudioSegment

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Omnia.AudioPlayback")

class AudioPlaybackQueue:
    """Manages audio output on desktop speakers with interruption capabilities."""

    def __init__(self):
        self.pa = pyaudio.PyAudio()
        self.interrupted = False
        self.is_playing = False

    def interrupt(self):
        """Immediately halts current audio playback on barge-in."""
        logger.info("Audio barge-in triggered: Halting output.")
        self.interrupted = True

    async def play_audio_bytes(self, raw_data: bytes, format_hint: str = "mp3"):
        """Decodes compressed audio bytes and streams to desktop speakers."""
        self.interrupted = False
        self.is_playing = True

        loop = asyncio.get_running_loop()

        def _play():
            try:
                sound = AudioSegment.from_file(io.BytesIO(raw_data), format=format_hint)
                stream = self.pa.open(
                    format=self.pa.get_format_from_width(sound.sample_width),
                    channels=sound.channels,
                    rate=sound.frame_rate,
                    output=True
                )
                
                chunk_size = 1024
                raw_bytes = sound.raw_data
                for i in range(0, len(raw_bytes), chunk_size):
                    if self.interrupted:
                        break
                    stream.write(raw_bytes[i:i + chunk_size])

                stream.stop_stream()
                stream.close()
            except Exception as e:
                logger.error(f"Playback error: {e}")
            finally:
                self.is_playing = False

        await loop.run_in_executor(None, _play)

audio_player = AudioPlaybackQueue()
