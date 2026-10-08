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

@tool
async def compile_user_intent_plan(natural_language_goal: str) -> str:
    """Compiles a user's natural language goal into a validated, executable TaskGraph.
    
    Args:
        natural_language_goal: High-level user command or mission.
    """
    from intent import intent_compiler
    tg, plan = await intent_compiler.compile_intent(natural_language_goal)
    if not tg:
        return f"[PLAN REJECTED / NEEDS CLARIFICATION] Status: {plan.validation.status.value}\nErrors: {plan.validation.errors}"
    return f"Plan compiled successfully with {len(plan.steps)} steps. Plan ID: {plan.plan_id}. Safety: {plan.validation.status.value}"

@tool
def explain_execution_plan(plan_id: str) -> str:
    """Returns a transparent, human-readable summary of the compiled execution plan.
    
    Args:
        plan_id: Identifier of the compiled plan.
    """
    from intent import intent_compiler
    history = intent_compiler.plan_history.get(plan_id)
    if not history:
        return f"Plan ID '{plan_id}' not found."
    return intent_compiler.explain_plan(history[-1])

@tool
def query_capability_registry(category: str = "") -> str:
    """Queries the authoritative Omnia Capability Registry for available capabilities.
    
    Args:
        category: Optional category filter (e.g. 'BROWSER', 'VISION', 'DEVICE', 'VOICE', 'SYSTEM').
    """
    from capabilities.registry import capability_registry
    from capabilities.models import CapabilityCategory
    cat = None
    if category:
        try:
            cat = CapabilityCategory[category.upper()]
        except KeyError:
            pass
    caps = capability_registry.list_capabilities(category=cat)
    lines = [f"Found {len(caps)} capability(ies):"]
    for c in caps:
        lines.append(f"- [{c.id}] v{c.version} ({c.health.value}) - {c.description[:60]}")
    return "\n".join(lines)

@tool
async def check_capability_health(capability_id: str = "") -> str:
    """Executes on-demand health probes across Omnia capabilities or checks a specific capability.
    
    Args:
        capability_id: Optional ID of a specific capability to probe.
    """
    from capabilities.health import capability_health_checker
    from capabilities.registry import capability_registry
    if capability_id:
        cap = capability_registry.get_capability(capability_id)
        if not cap:
            return f"Capability '{capability_id}' not found."
        return f"Capability [{cap.id}] is currently {cap.health.value}. Risk: {cap.risk_level.value}. Idempotency: {cap.idempotent.value}."
    results = await capability_health_checker.run_all_checks()
    return f"Probed {len(results)} capabilities: {results}"

@tool
def list_available_providers(capability_id: str) -> str:
    """Lists registered execution providers and their priorities for a target capability.
    
    Args:
        capability_id: Target capability ID (e.g. 'browser.navigate', 'voice.speak').
    """
    from capabilities.registry import capability_registry
    cap = capability_registry.get_capability(capability_id)
    if not cap:
        return f"Capability '{capability_id}' not found."
    if not cap.providers:
        return f"No execution providers registered for '{capability_id}'."
    lines = [f"Providers for '{capability_id}':"]
    for pid, p in cap.providers.items():
        lines.append(f"- {pid} [Prio: {p.priority}, Health: {p.health.value}, Latency: {p.latency_ms}ms, Env: {p.environment}]")
    return "\n".join(lines)

@tool
async def publish_custom_fabric_event(event_type: str, payload_json: str = "{}") -> str:
    """Publishes a typed event directly into the Omnia Event Fabric.
    
    Args:
        event_type: Validated event type string (e.g. 'device.connected', 'system.health_changed').
        payload_json: Serialized JSON dictionary of event payload.
    """
    import json
    from events import event_fabric, Event, EventEnvelope, EventPriority, EventSeverity, EventDurability
    try:
        data = json.loads(payload_json)
    except Exception:
        data = {"raw": payload_json}
    
    event = Event(
        envelope=EventEnvelope(
            event_type=event_type,
            source="omnia.tools",
            priority=EventPriority.NORMAL,
            severity=EventSeverity.INFO,
            durability=EventDurability.OPERATIONAL
        ),
        payload=data
    )
    ok = await event_fabric.publish(event)
    return f"Event '{event_type}' ({event.id}) {'published successfully' if ok else 'failed to publish'}."

@tool
def query_event_trace(correlation_id: str) -> str:
    """Queries ordered event journal history matching a correlation or task ID.
    
    Args:
        correlation_id: The task or correlation ID to trace.
    """
    from events import event_journal
    trace = event_journal.get_trace(correlation_id)
    if not trace:
        return f"No events recorded for trace '{correlation_id}'."
    lines = [f"Trace for '{correlation_id}' ({len(trace)} events):"]
    for item in trace:
        lines.append(f"- [{item['sequence']}] {item['event_type']} ({item['event_id']})")
    return "\n".join(lines)

@tool
def replay_event_trace(correlation_id: str) -> str:
    """Performs a safe, read-only analytical reconstruction of an event trace without executing side effects.
    
    Args:
        correlation_id: The task or correlation ID to reconstruct.
    """
    from events import event_journal
    summary = event_journal.replay_trace(correlation_id)
    if not summary:
        return f"No events to replay for trace '{correlation_id}'."
    return "\n".join(summary)

@tool
async def create_autonomous_mission(objective: str, deadline_seconds: float = 3600.0) -> str:
    """Initializes and supervises a high-level long-running mission.
    
    Args:
        objective: The high-level autonomous goal or operational mission.
        deadline_seconds: Hard deadline duration in seconds.
    """
    from supervisor import autonomous_supervisor
    mission = await autonomous_supervisor.create_mission(
        objective=objective,
        deadline_sec=deadline_seconds
    )
    return f"Mission '{mission.mission_id}' created with status '{mission.status.value}' (Deadline: {deadline_seconds}s)."

@tool
def get_mission_status(mission_id: str) -> str:
    """Queries real-time supervisory status, progress, and phase of a mission.
    
    Args:
        mission_id: The unique mission identifier.
    """
    from supervisor import autonomous_supervisor
    m = autonomous_supervisor.get_mission(mission_id)
    if not m:
        return f"Mission '{mission_id}' not found."
    return (
        f"Mission: {m.mission_id} | Objective: '{m.objective}'\n"
        f"Status: {m.status.value} | Phase: {m.phase.value} | Progress: {m.progress:.1f}%\n"
        f"Recovery Attempts Used: {m.recovery_attempts_used}/{m.max_recovery_attempts} | Replans: {m.replans_used}/{m.max_replans}"
    )

@tool
async def pause_autonomous_mission(mission_id: str, reason: str = "User request") -> str:
    """Pauses a running autonomous mission safely.
    
    Args:
        mission_id: Unique mission identifier.
        reason: Reason for pausing.
    """
    from supervisor import autonomous_supervisor
    ok = await autonomous_supervisor.pause_mission(mission_id, reason=reason)
    return f"Mission '{mission_id}' {'paused' if ok else 'failed to pause'}."

@tool
async def resume_autonomous_mission(mission_id: str) -> str:
    """Resumes a paused autonomous mission.
    
    Args:
        mission_id: Unique mission identifier.
    """
    from supervisor import autonomous_supervisor
    ok = await autonomous_supervisor.resume_mission(mission_id)
    return f"Mission '{mission_id}' {'resumed' if ok else 'failed to resume'}."

@tool
async def abort_autonomous_mission(mission_id: str, reason: str = "User abort") -> str:
    """Aborts an active autonomous mission permanently.
    
    Args:
        mission_id: Unique mission identifier.
        reason: Reason for aborting.
    """
    from supervisor import autonomous_supervisor
    ok = await autonomous_supervisor.abort_mission(mission_id, reason=reason)
    return f"Mission '{mission_id}' {'aborted' if ok else 'failed to abort'}."

@tool
def list_active_missions() -> str:
    """Lists all active and monitored autonomous missions."""
    from supervisor import autonomous_supervisor
    missions = autonomous_supervisor.list_missions()
    if not missions:
        return "No active missions currently registered in Mission Control."
    lines = [f"Registered Missions ({len(missions)}):"]
    for m in missions:
        lines.append(f"- ID: {m.mission_id} | Goal: '{m.objective[:35]}' | Status: {m.status.value} | Progress: {m.progress:.1f}%")
    return "\n".join(lines)

# --- Module 20: Human Approval Gateway Tools ---
@tool
async def request_human_approval(
    action: str,
    title: str,
    summary: str,
    reason: str,
    risk_level: str = "HIGH",
    timeout_sec: float = 120.0
) -> str:
    """Creates a human approval request and waits for user decision."""
    from approval import approval_gateway
    req = await approval_gateway.create_request(
        requested_action=action,
        action_params={},
        title=title,
        summary=summary,
        reason=reason,
        risk_level=risk_level,
        timeout_sec=timeout_sec
    )
    await approval_gateway.present_request(req.approval_id, channel="HUD")
    res = await approval_gateway.wait_for_decision(req.approval_id, timeout_sec=timeout_sec)
    return f"Approval request '{req.approval_id}' resolved with status: {res.status.value}"

@tool
async def submit_human_approval_decision(
    approval_id: str,
    decision: str,
    reason: str = ""
) -> str:
    """Submits human decision (APPROVE, REJECT, DEFER, CANCEL) for a pending approval."""
    from approval import approval_gateway, ApprovalDecisionType
    dec_upper = decision.strip().upper()
    try:
        dec_type = ApprovalDecisionType[dec_upper]
    except KeyError:
        return f"Invalid decision '{decision}'. Must be one of APPROVE, REJECT, DEFER, CANCEL."
    ok, rel, msg = await approval_gateway.submit_decision(approval_id, dec_type, reason=reason)
    return f"Decision submitted: {msg} (Token: {rel.release_token if rel else 'None'})"

@tool
def list_pending_human_approvals() -> str:
    """Lists all pending approval requests awaiting human decision."""
    from approval import approval_gateway
    pending = approval_gateway.list_pending()
    if not pending:
        return "No pending approval requests."
    lines = [f"Pending Approvals ({len(pending)}):"]
    for r in pending:
        lines.append(f"- ID: {r.approval_id} | Title: '{r.title}' | Action: '{r.requested_action}' | Risk: {r.risk_level} | Status: {r.status.value}")
    return "\n".join(lines)

@tool
def get_approval_details(approval_id: str) -> str:
    """Retrieves full details and status of a specific approval request."""
    from approval import approval_gateway
    req = approval_gateway.get_approval(approval_id)
    if not req:
        return f"Approval request '{approval_id}' not found."
    return (
        f"Approval Details [{req.approval_id}]:\n"
        f"Title:       {req.title}\n"
        f"Status:      {req.status.value}\n"
        f"Action:      {req.requested_action}\n"
        f"Risk Level:  {req.risk_level}\n"
        f"Summary:     {req.summary}\n"
        f"Fingerprint: {req.fingerprint[:16]}...\n"
        f"Reversible:  {req.is_reversible}\n"
        f"Expires At:  {req.expires_at}"
    )

@tool
async def emergency_invalidate_approvals(reason: str) -> str:
    """Cancels and invalidates all pending approval requests immediately."""
    from approval import approval_gateway
    count = await approval_gateway.emergency_invalidate(reason=reason)
    return f"Emergency invalidation completed: {count} pending approval(s) invalidated."

# --- Module 21: Autonomous Resource Scheduler Tools ---
@tool
def get_scheduler_status() -> str:
    """Retrieves real-time telemetry, queue depth, and worker slot allocation from the Resource Scheduler."""
    from scheduler import resource_scheduler
    t = resource_scheduler.get_telemetry()
    return (
        f"Scheduler Telemetry:\n"
        f"Health:            {t.health.value}\n"
        f"Pressure:          {t.pressure.value}\n"
        f"Ready Queue:       {t.ready_queue_depth}\n"
        f"Waiting Queue:     {t.waiting_queue_depth}\n"
        f"Active Schedules:  {t.active_schedules}\n"
        f"Execution Slots:   {t.idle_slots} idle / {t.total_slots} total\n"
        f"Reservations:      {t.active_reservations}\n"
        f"Deadlocks Detected:{t.deadlock_count}\n"
        f"Starvations Reaped:{t.starvation_count}\n"
        f"Preemptions:       {t.preemption_count}"
    )

@tool
def list_scheduled_work() -> str:
    """Lists all active and waiting tasks managed by the Autonomous Resource Scheduler."""
    from scheduler import scheduler_persistence_manager
    schedules = scheduler_persistence_manager.list_active_schedules()
    if not schedules:
        return "No active schedules currently managed by the scheduler."
    lines = [f"Active Schedules ({len(schedules)}):"]
    for s in schedules:
        lines.append(f"- ID: {s.schedule_id} | Task: {s.task_id} | State: {s.state.value} | Priority Score: {s.priority_score:.1f} | Slot: {s.assigned_slot_id or 'None'}")
    return "\n".join(lines)

@tool
async def trigger_scheduling_cycle() -> str:
    """Triggers an immediate scheduling cycle to allocate resources and admit waiting work."""
    from scheduler import resource_scheduler
    decisions = await resource_scheduler.schedule_next()
    return f"Scheduling cycle executed: {len(decisions)} decision(s) made ({sum(1 for d in decisions if d.decision.value == 'ADMIT')} admitted)."

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
    compile_user_intent_plan,
    explain_execution_plan,
    query_capability_registry,
    check_capability_health,
    list_available_providers,
    publish_custom_fabric_event,
    query_event_trace,
    replay_event_trace,
    create_autonomous_mission,
    get_mission_status,
    pause_autonomous_mission,
    resume_autonomous_mission,
    abort_autonomous_mission,
    list_active_missions,
    request_human_approval,
    submit_human_approval_decision,
    list_pending_human_approvals,
    get_approval_details,
    emergency_invalidate_approvals,
    get_scheduler_status,
    list_scheduled_work,
    trigger_scheduling_cycle,
]

# Backward compatibility alias
OMNIA_HARDWARE_TOOLS = OMNIA_ALL_TOOLS

if __name__ == "__main__":
    print(f"Omnia Tools registered successfully: {[t.__name__ for t in OMNIA_ALL_TOOLS]}")



