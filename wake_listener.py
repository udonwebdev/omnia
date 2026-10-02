import struct
import logging
import asyncio
import pvporcupine
import pyaudio
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Omnia.WakeListener")

BUS_STATE_URL = "http://127.0.0.1:8000/api/state"

class WakeWordListener:
    """Listens continuously for the wake word trigger and signals the orchestrator."""

    def __init__(self, keyword: str = "jarvis", sensitivity: float = 0.6):
        self.keyword = keyword
        self.sensitivity = sensitivity
        self.porcupine = None
        self.audio_stream = None
        self.pa = None

    def initialize(self):
        # Initializes Porcupine engine with target keyword
        self.porcupine = pvporcupine.create(
            keywords=[self.keyword],
            sensitivities=[self.sensitivity]
        )
        self.pa = pyaudio.PyAudio()
        self.audio_stream = self.pa.open(
            rate=self.porcupine.sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=self.porcupine.frame_length
        )
        logger.info(f"Wake listener initialized for keyword: '{self.keyword}'")

    async def notify_hud(self, state: str, detail: str):
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                await client.post(BUS_STATE_URL, json={"state": state, "message": detail})
        except Exception:
            pass

    async def listen_loop(self, on_wake_callback):
        self.initialize()
        logger.info("Omnia Voice Ear is active. Listening for trigger word...")
        
        loop = asyncio.get_running_loop()
        while True:
            # Non-blocking audio frame read
            pcm = await loop.run_in_executor(
                None, 
                self.audio_stream.read, 
                self.porcupine.frame_length, 
                False
            )
            pcm_unpacked = struct.unpack_from("h" * self.porcupine.frame_length, pcm)
            result = self.porcupine.process(pcm_unpacked)

            if result >= 0:
                logger.info(">>> WAKE WORD DETECTED: OMNIA ACTIVE <<<")
                await self.notify_hud("LISTENING", "Awaiting voice directive...")
                await on_wake_callback()
                await self.notify_hud("SYSTEM_IDLE", "Standing by.")

    def cleanup(self):
        if self.audio_stream:
            self.audio_stream.close()
        if self.pa:
            self.pa.terminate()
        if self.porcupine:
            self.porcupine.delete()
