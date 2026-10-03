import asyncio
import os
import sys
import uvicorn
from google.antigravity import Agent, LocalAgentConfig
from google.antigravity.types import CapabilitiesConfig

from omnia_bus import app as bus_app
from omnia_tools import OMNIA_ALL_TOOLS
from wake_listener import WakeWordListener
from voice_pipeline import voice_pipeline
from mesh_discovery import mesh_registry


SYSTEM_DIRECTIVE = """
You are Omnia: an autonomous task orchestrator and device intelligence.
You possess access to a multi-device ADB mesh, desktop UI controls, browsing history vector memory,
and an autonomous Playwright browser agent.
Execute user goals immediately and proactively call the necessary tools.
"""

async def run_bus_server():
    """Runs the FastAPI and WebSocket state bus in the background."""
    config = uvicorn.Config(bus_app, host="127.0.0.1", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()

async def run_voice_interface(agent_instance):
    """Monitors wake-word events and pipes voice commands directly into the agent."""
    listener = WakeWordListener()

    async def handle_wake():
        audio_buffer = voice_pipeline.record_audio_snippet(record_seconds=4)
        command_text = voice_pipeline.transcribe(audio_buffer)
        if command_text:
            print(f"\n[Voice Command Detected]: {command_text}")
            response = await agent_instance.chat(command_text)
            async for token in response:
                sys.stdout.write(token)
                sys.stdout.flush()
            print()

    await listener.listen_loop(handle_wake)

async def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[CRITICAL] GEMINI_API_KEY not configured. Set environment variable to proceed.")
        sys.exit(1)

    # Configure Antigravity Runtime with complete capabilities and full tool registry
    agent_config = LocalAgentConfig(
        system_instructions=SYSTEM_DIRECTIVE,
        api_key=api_key,
        capabilities=CapabilitiesConfig(
            shell_execution=True,
            file_operations=True
        ),
        tools=OMNIA_ALL_TOOLS
    )

    print("=" * 60)
    print("         OMNIA UNIFIED AGENT RUNTIME STARTING         ")
    print("=" * 60)

    async with Agent(agent_config) as omnia_agent:
        # Launch the event bus, voice pipeline, and mesh discovery daemon concurrently
        bus_task = asyncio.create_task(run_bus_server())
        voice_task = asyncio.create_task(run_voice_interface(omnia_agent))
        mesh_task = asyncio.create_task(mesh_registry.start())

        print("[READY] All subsystems operational. Enter command below or speak wake-word.")
        
        try:
            while True:
                user_input = await asyncio.get_running_loop().run_in_executor(None, input, "\nOmnia > ")
                user_input = user_input.strip()
                if user_input.lower() in ["exit", "shutdown"]:
                    break
                if not user_input:
                    continue

                response = await omnia_agent.chat(user_input)
                async for chunk in response:
                    sys.stdout.write(chunk)
                    sys.stdout.flush()
                print()
        finally:
            bus_task.cancel()
            voice_task.cancel()
            mesh_registry.stop()
            mesh_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())
