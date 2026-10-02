import json
import base64
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Response
from audio_transcoder import audio_transcoder
from voice_pipeline import voice_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Omnia.TelephonyGateway")

telephony_router = APIRouter(prefix="/telephony")

@telephony_router.post("/incoming-call")
async def handle_incoming_call():
    """Returns TwiML instruction to connect the caller directly to the Omnia media stream."""
    twiml_response = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>Connecting to Omnia Intelligence Engine.</Say>
    <Connect>
        <Stream url="ws://127.0.0.1:8000/telephony/ws/audio" />
    </Connect>
</Response>"""
    return Response(content=twiml_response, media_type="application/xml")

@telephony_router.websocket("/ws/audio")
async def telephony_audio_stream(websocket: WebSocket):
    """Processes bidirectional telephony audio streams."""
    await websocket.accept()
    logger.info("Telephony audio stream connection accepted.")

    buffer = bytearray()
    stream_sid = None

    try:
        while True:
            raw_message = await websocket.receive_text()
            data = json.loads(raw_message)
            event_type = data.get("event")

            if event_type == "start":
                stream_sid = data["start"]["streamSid"]
                logger.info(f"Inbound stream active. Stream SID: {stream_sid}")

            elif event_type == "media":
                payload_chunk = base64.b64decode(data["media"]["payload"])
                buffer.extend(payload_chunk)

                # Process in ~3 second voice intervals (8000 bytes/sec * 3 = 24000 bytes)
                if len(buffer) >= 24000:
                    raw_mulaw = bytes(buffer)
                    buffer.clear()

                    # Transcode and transcribe
                    wav_io = audio_transcoder.mulaw_to_wav_16k(raw_mulaw)
                    transcription = voice_pipeline.transcribe(wav_io)

                    if transcription.strip():
                        logger.info(f"[Phone Inbound Direct]: {transcription}")
                        # Event bus routing occurs here

            elif event_type == "stop":
                logger.info(f"Stream {stream_sid} disconnected by remote caller.")
                break

    except WebSocketDisconnect:
        logger.info("Telephony client disconnected.")
    except Exception as e:
        logger.error(f"Error handling telephony audio stream: {e}")

telephony_app = telephony_router  # Alias for backward compatibility
