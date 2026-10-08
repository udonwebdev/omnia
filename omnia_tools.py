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
from mesh_discovery import mesh_registry
from mesh_replicator import mesh_replicator

@tool
def list_mesh_nodes() -> str:
    """Returns a list of all auto-discovered peer nodes and ADB host machines on the local mesh network."""
    nodes = mesh_registry.get_active_nodes()
    if not nodes:
        return "No external mesh nodes discovered. Local node running in standalone mode."
    
    report = [f"Discovered {len(nodes)} active mesh peer(s):"]
    for nid, details in nodes.items():
        report.append(f"- ID: {nid} | IP: {details['ip']}:{details['port']} | Role: {details['role']}")
    return "\n".join(report)

@tool
async def broadcast_to_all_mesh_hosts(state: str, details: str = "") -> str:
    """Propagates a state change or UI update to all discovered nodes on the local network.
    
    Args:
        state: Target status identifier ('SYSTEM_IDLE', 'ALERT', 'DISPATCHING').
        details: Accompanying context or notification string.
    """
    delivered = await mesh_replicator.broadcast_state(state, details)
    return f"State '{state}' replicated across {len(delivered)} mesh node(s): {delivered}"

# --- Module 13: Multimodal Vision Tools ---
from vision import vision_engine, VisionSource

def _parse_source(src_str: str) -> VisionSource:
    s = src_str.lower().strip()
    if s == "android":
        return VisionSource.ANDROID
    elif s == "browser":
        return VisionSource.BROWSER
    return VisionSource.DESKTOP

@tool
async def capture_screen(source: str = "desktop") -> str:
    """Captures and validates a screen frame from desktop, android, or browser.
    
    Args:
        source: 'desktop', 'android', or 'browser'
    """
    try:
        src = _parse_source(source)
        frame = await vision_engine.capture(source=src)
        return f"Frame captured: ID {frame.frame_id[:8]} ({frame.width}x{frame.height}) via {src.value} in {frame.capture_duration_ms:.1f}ms."
    except Exception as e:
        return f"Capture failed: {str(e)}"

@tool
async def analyze_screen(source: str = "desktop") -> str:
    """Perceives and extracts visible text and UI elements from the active screen.
    
    Args:
        source: 'desktop', 'android', or 'browser'
    """
    try:
        src = _parse_source(source)
        obs = await vision_engine.observe(source=src)
        summary = [f"Analyzed frame {obs.frame.frame_id[:8]}: Detected {len(obs.elements)} visual element(s) in {obs.analysis_duration_ms:.1f}ms."]
        for i, el in enumerate(obs.elements[:5], 1):
            summary.append(f" {i}. [{el.element_type.value.upper()}] '{el.label}' (conf: {el.confidence:.2f})")
        if len(obs.elements) > 5:
            summary.append(f" ... and {len(obs.elements) - 5} more.")
        return "\n".join(summary)
    except Exception as e:
        return f"Analysis failed: {str(e)}"

@tool
async def find_visual_element(target_description: str, source: str = "desktop") -> str:
    """Locates and ranks visual elements matching a description (e.g., 'Continue button').
    
    Args:
        target_description: Target text or button name to search for on screen.
        source: 'desktop', 'android', or 'browser'
    """
    try:
        src = _parse_source(source)
        obs = await vision_engine.observe(source=src)
        candidate = await vision_engine.locate(target_description, obs)
        if not candidate:
            return f"No visual candidate found matching: '{target_description}'"
        el = candidate.element
        cx, cy = el.bounding_box.center
        return f"Found visual target '{el.label}' (Rank 1, Score {candidate.score:.2f}) at normalized center ({cx:.2f}, {cy:.2f}). Reason: {candidate.reason}"
    except Exception as e:
        return f"Locate failed: {str(e)}"

@tool
@guard_action
async def click_visual_element(target_description: str, expected_change: str, source: str = "desktop") -> str:
    """Executes the full Observe -> Locate -> Act -> Observe -> Verify loop on a target element.
    
    Args:
        target_description: Target button or text description to click.
        expected_change: What visual transition should happen afterwards.
        source: 'desktop', 'android', or 'browser'
    """
    try:
        src = _parse_source(source)
        result = await vision_engine.observe_act_verify(
            target_description=target_description,
            expected_change=expected_change,
            source=src,
            action_type="click"
        )
        return f"Visual interaction result: {result}"
    except Exception as e:
        return f"Visual interaction failed: {str(e)}"

@tool
async def verify_visual_state(expected_text: str, source: str = "desktop") -> str:
    """Captures the screen and verifies if expected text is visually present.
    
    Args:
        expected_text: The string that must be present on screen.
        source: 'desktop', 'android', or 'browser'
    """
    try:
        src = _parse_source(source)
        obs = await vision_engine.observe(source=src)
        found = any(expected_text.lower() in el.text.lower() for el in obs.elements)
        status = "VERIFIED" if found else "FAILED"
        return f"Verification {status}: Text '{expected_text}' {'found' if found else 'not found'} on {src.value}."
    except Exception as e:
        return f"Verification failed: {str(e)}"

# --- Module 14: Dynamic Task Graph & Self-Healing Tools ---
import json
from task_graph import (
    task_executor,
    TaskGraph,
    TaskNode,
    TaskState,
    IdempotencyLevel,
    ExecutionContext
)

@tool
def get_active_task_status(task_id: str) -> str:
    """Returns the current execution state, active node, and progress percentage of a task.
    
    Args:
        task_id: Unique task identifier.
    """
    task = task_executor.active_tasks.get(task_id)
    if not task:
        return f"Task '{task_id}' not found in active task registry."
    
    total = len(task.nodes)
    completed = sum(1 for n in task.nodes.values() if n.state.value == "COMPLETED")
    pct = (completed / total * 100.0) if total > 0 else 0.0
    return f"Task ID: {task.task_id} | State: {task.state.value} | Current Node: {task.current_node_id} | Progress: {pct:.1f}% ({completed}/{total}) | Replans: {task.replan_count}"

@tool
def cancel_active_task(task_id: str) -> str:
    """Cancels a running task graph and releases all held hardware/browser locks.
    
    Args:
        task_id: Unique task identifier to cancel.
    """
    if task_id in task_executor.active_tasks:
        task_executor.cancel_task(task_id)
        return f"Task '{task_id}' cancellation signal dispatched."
    return f"Task '{task_id}' not found."

@tool
def pause_active_task(task_id: str) -> str:
    """Pauses a running task, preserving current node state without executing further actions.
    
    Args:
        task_id: Unique task identifier to pause.
    """
    if task_id in task_executor.active_tasks:
        task_executor.pause_task(task_id)
        return f"Task '{task_id}' paused."
    return f"Task '{task_id}' not found."

@tool
def resume_active_task(task_id: str) -> str:
    """Resumes a paused task, allowing next steps to execute.
    
    Args:
        task_id: Unique task identifier to resume.
    """
    if task_id in task_executor.active_tasks:
        task_executor.resume_task(task_id)
        return f"Task '{task_id}' resumed."
    return f"Task '{task_id}' not found."

@tool
def list_active_orchestration_tasks() -> str:
    """Lists all running and managed autonomous task graphs."""
    tasks = task_executor.active_tasks
    if not tasks:
        return "No active tasks currently executing in the task engine."
    
    report = [f"Active Orchestration Tasks ({len(tasks)}):"]
    for tid, t in tasks.items():
        report.append(f"- ID: {tid} | Goal: '{t.goal}' | State: {t.state.value}")
    return "\n".join(report)

@tool
def scan_and_list_interrupted_tasks() -> str:
    """Scans durable database for tasks interrupted by unexpected crashes or dead heartbeats."""
    from persistence import crash_recovery_engine
    crashed = crash_recovery_engine.scan_for_crashes(heartbeat_timeout_sec=30.0)
    if not crashed:
        return "No interrupted tasks detected in durable storage."
    report = [f"Detected {len(crashed)} Interrupted Tasks:"]
    for c in crashed:
        report.append(f"- Task: {c['task_id']} | Goal: '{c['goal']}' | Status: {c['status']} | Node: {c['current_node_id']}")
    return "\n".join(report)

@tool
def get_task_checkpoint_summary(task_id: str) -> str:
    """Fetches latest verified durable checkpoint details for an interrupted or completed task."""
    from persistence import checkpoint_manager
    chk = checkpoint_manager.store.get_latest_checkpoint(task_id)
    if not chk:
        return f"No checkpoints found for task '{task_id}'."
    return (
        f"Checkpoint: {chk.checkpoint_id} (Checksum: {chk.checksum[:10]})\n"
        f"Task State: {chk.task_state} | Active Node: {chk.node_id}\n"
        f"Trigger: {chk.policy_trigger} | Node States: {chk.node_states}\n"
        f"Variables: {list(chk.variables.keys())}"
    )

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
    list_mesh_nodes,
    broadcast_to_all_mesh_hosts,
    capture_screen,
    analyze_screen,
    find_visual_element,
    click_visual_element,
    verify_visual_state,
    get_active_task_status,
    cancel_active_task,
    pause_active_task,
    resume_active_task,
    list_active_orchestration_tasks,
    scan_and_list_interrupted_tasks,
    get_task_checkpoint_summary,
]

# Backward compatibility alias
OMNIA_HARDWARE_TOOLS = OMNIA_ALL_TOOLS

if __name__ == "__main__":
    print(f"Omnia Tools registered successfully: {[t.__name__ for t in OMNIA_ALL_TOOLS]}")



