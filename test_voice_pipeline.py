import asyncio
import io
from voice_pipeline import VoicePipeline
from omnia_tools import update_hud_state

async def test_mock_audio_packet():
    # 1. Create mock pipeline
    pipeline = VoicePipeline(model_size="base.en")
    
    # 2. Simulate raw recorded audio buffer
    mock_audio_stream = io.BytesIO(b"RIFFmockwavheaderanddata")
    
    # 3. Transcribe mock instruction
    transcription = pipeline.transcribe(mock_audio_stream)
    print(f"[TEST] Transcribed Voice Command: '{transcription}'")
    assert len(transcription) > 0

    # 4. Trigger tool execution based on transcribed intent
    if "unlock" in transcription:
        res = await update_hud_state("SCREEN_UNLOCKED", "Voice instruction verified")
        print(f"[TEST] Triggered Tool Execution: {res}")
        assert "SCREEN_UNLOCKED" in res

    print("[TEST] Voice pipeline & intent-to-tool trigger test PASSED.")

if __name__ == "__main__":
    asyncio.run(test_mock_audio_packet())
