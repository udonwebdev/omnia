import asyncio
import os
import sys
from google.antigravity import Agent, LocalAgentConfig
from google.antigravity.types import CapabilitiesConfig
from omnia_tools import OMNIA_HARDWARE_TOOLS
from wake_listener import WakeWordListener
from voice_pipeline import voice_pipeline

# Define the central operating directive for Omnia
OMNIA_SYSTEM_INSTRUCTION = """
You are Omnia, an advanced autonomous operating intelligence and distributed orchestration engine.
Your purpose:
1. Orchestrate hardware targets, device meshes, and local systems via tool-calling.
2. Ingest contextual events across active platforms and execute tasks with zero latency.
3. Stream operational status and reasoning steps directly.
4. Execute terminal and system operations autonomously within safe governance boundaries.
"""

import re
from audio_synthesizer import audio_synth
from audio_playback import audio_player

async def speak_streamed_chunks(response_stream):
    """Accumulates text chunks into sentences and pipes them immediately into audio synthesis."""
    sentence_buffer = ""
    sentence_delimiters = re.compile(r"([.!?]+(\s+|$))")

    async for chunk in response_stream:
        sys.stdout.write(chunk)
        sys.stdout.flush()
        sentence_buffer += chunk

        match = sentence_delimiters.search(sentence_buffer)
        if match:
            split_idx = match.end()
            sentence = sentence_buffer[:split_idx].strip()
            sentence_buffer = sentence_buffer[split_idx:]
            
            if sentence:
                raw_audio = await audio_synth.synthesize_to_bytes(sentence)
                asyncio.create_task(audio_player.play_audio_bytes(raw_audio))

    if sentence_buffer.strip():
        raw_audio = await audio_synth.synthesize_to_bytes(sentence_buffer.strip())
        await audio_player.play_audio_bytes(raw_audio)

async def start_voice_runtime(agent_instance):
    """Starts always-on wake listener and auto-dispatches instructions to Antigravity agent."""
    listener = WakeWordListener()

    async def handle_wake():
        # Record 4-second voice instruction
        audio_buffer = voice_pipeline.record_audio_snippet(record_seconds=4)
        command_text = voice_pipeline.transcribe(audio_buffer)

        if command_text:
            print(f"\n[Voice Instruction Received]: {command_text}")
            response = await agent_instance.chat(command_text)
            await speak_streamed_chunks(response)
            print()

    await listener.listen_loop(handle_wake)

async def run_omnia():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY environment variable is not set.")
        sys.exit(1)

    # Configure Antigravity Runtime Capabilities
    config = LocalAgentConfig(
        system_instructions=OMNIA_SYSTEM_INSTRUCTION,
        api_key=api_key,
        capabilities=CapabilitiesConfig(
            shell_execution=True,
            file_operations=True
        ),
        tools=OMNIA_HARDWARE_TOOLS
    )

    print("==================================================")
    print("   OMNIA CORE ONLINE — Antigravity Agent Runtime   ")
    print("==================================================")

    async with Agent(config) as omnia:
        while True:
            try:
                user_input = input("\nOmnia > ").strip()
                if user_input.lower() in ["exit", "quit", "shutdown"]:
                    print("[Omnia] Shutting down session.")
                    break
                if not user_input:
                    continue

                response = await omnia.chat(user_input)
                
                # Stream the agent's response tokens in real-time
                async for chunk in response:
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
                print()

            except (KeyboardInterrupt, EOFError):
                print("\n[Omnia] Session interrupted.")
                break

if __name__ == "__main__":
    asyncio.run(run_omnia())
