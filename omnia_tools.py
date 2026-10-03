import httpx
try:
    from google.antigravity.tools import tool
except ImportError:
    # Google Antigravity SDK passes raw callables or uses a transparent decorator
    def tool(fn):
        return fn

from device_controller import DeviceController
from desktop_controller import desktop_ctl
from memory_engine import memory
from browser_driver import browser_driver
from browser_agent import browser_agent
from omnia_guard import guard_action

BUS_URL = "http://127.0.0.1:8000"
controller = DeviceController()

# --- Hardware & ADB Tools ---
@tool
async def unlock_all_devices() -> str:
    """Wakes up and dismisses lock screens concurrently across all connected Android devices."""
    results = await controller.wake_and_unlock_mesh()
    return f"Unlock dispatched to {len(results)} device(s): {results}"

@tool
async def play_youtube_video(video_id: str) -> str:
    """Launches and plays a YouTube video across all devices simultaneously."""
    results = await controller.launch_youtube(video_id)
    return f"Play command for video '{video_id}' dispatched to {len(results)} device(s)."

@tool
async def broadcast_url_to_mesh(url: str) -> str:
    """Opens a target URL across default browsers on all connected Android devices."""
    results = await controller.trigger_browser_url(url)
    return f"Broadcasted URL {url} to {len(results)} device(s)."

@tool
@guard_action
async def execute_mesh_shell_command(shell_command: str) -> str:
    """Runs a raw shell command concurrently across all connected devices."""
    results = await controller.broadcast_shell(shell_command)
    return f"Command executed across {len(results)} device(s)."

# --- Desktop & HUD Tools ---
@tool
async def update_hud_state(state: str, details: str = "") -> str:
    """Updates the fullscreen Omnia HUD state ('SYSTEM_IDLE', 'SYSTEM_LOCKED', 'SCREEN_UNLOCKED', 'DISPATCHING')."""
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            await client.post(f"{BUS_URL}/api/state", json={"state": state, "message": details})
            return f"HUD state updated to {state}."
    except Exception as e:
        return f"HUD update failed: {e}"

@tool
def lock_host_screen() -> str:
    """Locks the local workstation display immediately."""
    success = desktop_ctl.lock_workstation()
    return "Workstation locked successfully." if success else "Failed to lock workstation."

@tool
def launch_hud_interface() -> str:
    """Launches the full-screen Omnia HUD monitor display in the default browser."""
    success = desktop_ctl.open_hud()
    return "HUD launched." if success else "Failed to launch HUD."

# --- Web Context & Memory Tools ---
@tool
def search_recent_web_context(query: str) -> str:
    """Searches memory for active tabs, recently opened URLs, or web page content."""
    matches = memory.search_context(query=query, limit=3)
    if not matches:
        return f"No browsing context found matching: '{query}'"
    output = ["Relevant context matches:"]
    for i, m in enumerate(matches, 1):
        output.append(f"{i}. Title: {m['title']}\n   URL: {m['url']}\n   Snippet: {m['snippet']}")
    return "\n".join(output)

# --- Autonomous Web Execution Tools ---
@tool
async def open_url_in_browser(url: str) -> str:
    """Directly navigates the agent browser to a URL."""
    final_url = await browser_driver.navigate(url)
    return f"Browser navigated to: {final_url}"

@tool
@guard_action
async def execute_web_task(target_url: str, objective: str) -> str:
    """Executes multi-step browser tasks (forms, search, extraction) autonomously."""
    result = await browser_agent.run_task(target_url=target_url, instruction=objective)
    return f"Web task finished: {result}"

# --- Speech Synthesis & Audio Responder Tools ---
from audio_synthesizer import audio_synth
from audio_playback import audio_player

@tool
async def speak_phrase(text: str) -> str:
    """Synthesizes and speaks a response out loud across the workstation audio system.
    
    Args:
        text: Natural language sentence to speak to the user.
    """
    await update_hud_state("SPEAKING", text[:60])
    raw_audio = await audio_synth.synthesize_to_bytes(text)
    await audio_player.play_audio_bytes(raw_audio)
    await update_hud_state("SYSTEM_IDLE", "Standing by.")
    return f"Spoke phrase: '{text}'"

@tool
def stop_speech_playback() -> str:
    """Immediately stops and clears any active audio speech or media on the host."""
    audio_player.interrupt()
    return "Speech output aborted."

# Complete Tool Registry
OMNIA_ALL_TOOLS = [
    unlock_all_devices,
    play_youtube_video,
    broadcast_url_to_mesh,
    execute_mesh_shell_command,
    update_hud_state,
    lock_host_screen,
    launch_hud_interface,
    search_recent_web_context,
    open_url_in_browser,
    execute_web_task,
    speak_phrase,
    stop_speech_playback,
]

# Backward compatibility alias
OMNIA_HARDWARE_TOOLS = OMNIA_ALL_TOOLS

if __name__ == "__main__":
    print(f"Omnia Tools registered successfully: {[t.__name__ for t in OMNIA_ALL_TOOLS]}")
