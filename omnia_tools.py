import httpx
import uuid
import time
from typing import Optional, Dict, Any, List
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

# --- Module 22: Distributed Coordination Tools ---
@tool
def get_coordination_status() -> str:
    """Returns cluster coordination health, leader role, current epoch, and lease status."""
    from coordination import coordination_service
    t = coordination_service.get_telemetry()
    return (
        f"Coordination Telemetry:\n"
        f"Local Node:          {t.local_node_id}\n"
        f"Role:                {t.role.value}\n"
        f"Epoch:               {t.current_epoch}\n"
        f"Active Leader:       {t.current_leader or 'None'}\n"
        f"Cluster Members:     {t.cluster_size}\n"
        f"Quorum Size:         {t.quorum_size} (Has Quorum: {t.has_quorum})\n"
        f"Active Claims:       {t.active_claims}\n"
        f"Active Locks:        {t.active_locks}\n"
        f"Fencing Violations:  {t.fencing_violations}\n"
        f"Ownership Conflicts: {t.ownership_conflicts}"
    )

@tool
def list_cluster_members() -> str:
    """Lists all active, suspected, or quarantined nodes in the distributed cluster."""
    from coordination import coordination_service
    members = coordination_service.membership.get_active_members()
    if not members:
        return "No active cluster members registered."
    lines = [f"Active Cluster Nodes ({len(members)}):"]
    for m in members:
        lines.append(f"- Node: {m.node_id} ({m.node_name}) | Trust: {m.trust_state.value} | State: {m.membership_state.value} | Endpoint: {m.endpoint_url}")
    return "\n".join(lines)

@tool
def claim_task_ownership(task_id: str) -> str:
    """Claims exclusive distributed ownership over a task to prevent duplicate node execution."""
    from coordination import coordination_service
    success, claim, msg = coordination_service.claim_task_ownership(task_id)
    if success and claim:
        return f"Ownership claimed for task '{task_id}' (Claim ID: {claim.claim_id}, Fencing Token: {claim.fencing_token})."
    return f"Ownership claim rejected for task '{task_id}': {msg}"

@tool
def start_cluster_election() -> str:
    """Triggers a consensus-backed leader election cycle in the distributed cluster."""
    from coordination import coordination_service
    success, epoch, token = coordination_service.elect_leader()
    if success:
        return f"Election SUCCESS: Local node elected leader for Epoch {epoch} (Fencing Token: {token})."
    return f"Election FAILED: Could not achieve quorum majority for Epoch {epoch}."

# --- Module 23: Distributed Replication & State Synchronization Tools ---
@tool
def get_replication_status() -> str:
    """Returns cluster state replication telemetry, lag, and divergence status."""
    from replication import replication_service
    t = replication_service.get_telemetry()
    return (
        f"Replication Telemetry:\n"
        f"Local Node:          {t.local_node_id}\n"
        f"Cluster Epoch:       {t.cluster_epoch}\n"
        f"Total Namespaces:    {t.total_namespaces}\n"
        f"Active Peers:        {t.active_peers}\n"
        f"Deltas Applied:      {t.total_deltas_applied}\n"
        f"Snapshots Installed: {t.total_snapshots_installed}\n"
        f"Active Conflicts:    {t.active_conflicts}\n"
        f"Fencing Rejections:  {t.fencing_rejections}\n"
        f"Integrity Failures:  {t.integrity_failures}\n"
        f"Divergence Count:    {t.divergence_count}"
    )

@tool
def list_replication_namespaces() -> str:
    """Lists all configured state namespaces with their replication and sensitivity classifications."""
    from replication import namespace_registry
    namespaces = namespace_registry.list_namespaces()
    lines = [f"Replication Namespaces ({len(namespaces)}):"]
    for ns in namespaces:
        reps = "REPLICATED" if ns.is_replicable() else "LOCAL_ONLY/BLOCKED"
        lines.append(f"- ID: {ns.namespace_id} | Policy: {ns.consistency_policy.value} | Sensitivity: {ns.sensitivity.value} | Status: {reps}")
    return "\n".join(lines)

@tool
def trigger_state_reconciliation(namespace_id: str) -> str:
    """Performs an anti-entropy divergence check and reconciliation for a namespace."""
    from replication import replication_service
    recs = replication_service.list_records(namespace_id)
    return f"Reconciliation executed for namespace '{namespace_id}': {len(recs)} local records evaluated."

# --- Module 24: Distributed Configuration & Control Plane Tools ---
from config import config_control_plane, RolloutStrategy, ConfigScope

@tool
def get_config_status() -> str:
    """Returns telemetry and status of runtime configuration control plane (active version, schemas, rollouts, drift)."""
    telemetry = config_control_plane.get_telemetry()
    return json.dumps(telemetry.to_dict(), indent=2)

@tool
def get_config_value(key: str, node_id: str = "", device_id: str = "") -> str:
    """Resolves an authoritative configuration parameter according to hierarchical precedence (DEVICE > NODE > CLUSTER > GLOBAL)."""
    val = config_control_plane.resolve_effective_value(
        key=key,
        node_id=node_id if node_id else None,
        device_id=device_id if device_id else None
    )
    schema = config_control_plane.get_schema(key)
    is_masked = schema.is_secret if schema else (isinstance(val, str) and val.startswith("secret://"))
    display = "[SECRET_MASKED]" if is_masked else val
    return json.dumps({"key": key, "effective_value": display})

@tool
def propose_config_change(changes_json: str, justification: str = "", parent_version: int = 0) -> str:
    """Proposes and stages a configuration version with optimistic concurrency and validation checks."""
    try:
        changes = json.loads(changes_json)
    except Exception as e:
        return f"INVALID_JSON: {e}"

    p_ver = parent_version if parent_version > 0 else None
    ok, new_ver, errors = config_control_plane.propose_version(
        values=changes,
        author="operator_tool",
        justification=justification or "Operator proposed configuration modification",
        parent_version=p_ver
    )
    if not ok:
        return f"PROPOSAL_FAILED: {errors}"
    return f"PROPOSAL_STAGED: Version {new_ver.version} staged (Hash: {new_ver.content_hash[:8]})."

@tool
def rollout_config_version(version: int, strategy: str = "ALL_AT_ONCE", batch_size: int = 1, target_nodes_json: str = "[]") -> str:
    """Activates and rolls out a staged configuration version across cluster nodes."""
    try:
        strat = RolloutStrategy(strategy.upper())
    except Exception:
        strat = RolloutStrategy.ALL_AT_ONCE

    try:
        target_nodes = json.loads(target_nodes_json)
        if not target_nodes:
            target_nodes = ["local_node"]
    except Exception:
        target_nodes = ["local_node"]

    ok, rollout, msg = config_control_plane.activate_version(
        version_num=version,
        target_nodes=target_nodes,
        strategy=strat,
        batch_size=batch_size
    )
    return f"ROLLOUT_RESULT: success={ok}, message='{msg}', rollout_id='{rollout.rollout_id if rollout else None}'"

@tool
def rollback_config_version(current_version: int, target_version: int = 0, reason: str = "Operator request", target_nodes_json: str = "[]") -> str:
    """Atomically rolls back the cluster configuration to a prior version."""
    t_ver = target_version if target_version > 0 else None
    try:
        target_nodes = json.loads(target_nodes_json)
        if not target_nodes:
            target_nodes = ["local_node"]
    except Exception:
        target_nodes = ["local_node"]

    ok, target_obj, msg = config_control_plane.rollback_version(
        current_version_num=current_version,
        target_version_num=t_ver,
        reason=reason,
        target_nodes=target_nodes
    )
    return f"ROLLBACK_RESULT: success={ok}, target_version={target_obj.version if target_obj else None}, message='{msg}'"

@tool
def detect_config_drift(node_id: str, actual_values_json: str, actual_version: int = 0) -> str:
    """Inspects a node's active runtime parameters against cluster authority to detect configuration drift."""
    try:
        actual_vals = json.loads(actual_values_json)
    except Exception as e:
        return f"INVALID_JSON: {e}"

    drifts = config_control_plane.detect_node_drift(
        node_id=node_id,
        actual_values=actual_vals,
        actual_version=actual_version
    )
    return json.dumps([d.to_dict() for d in drifts], indent=2)

@tool
def diff_config_versions(base_version: int, target_version: int) -> str:
    """Renders a formatted diff between two configuration versions with secrets masked."""
    base_obj = config_control_plane.persistence.get_version(base_version)
    target_obj = config_control_plane.persistence.get_version(target_version)
    if not base_obj or not target_obj:
        return f"ERROR: Version not found. base={base_version if base_obj else 'MISSING'}, target={target_version if target_obj else 'MISSING'}"

    changes = config_control_plane.diff_engine.compute_diff(
        old_values=base_obj.values,
        new_values=target_obj.values,
        schemas=config_control_plane._schemas
    )
    return config_control_plane.diff_engine.format_diff_report(changes, mask_secrets=True)

# --- Module 25: Secrets, Credentials & Secure Identity Lifecycle Tools ---
from secrets import secrets_service, SecretType

@tool
def get_secret_metadata(secret_id: str) -> str:
    """Returns metadata for a registered secret (version, provider, scope, status, expiration). Never exposes plaintext."""
    meta = secrets_service.get_secret_metadata(secret_id)
    if not meta:
        return f"SECRET_NOT_FOUND: Secret '{secret_id}' does not exist in catalog."
    return json.dumps(meta.to_dict(), indent=2)

@tool
def acquire_secret_lease(secret_uri: str, requester: str, purpose: str, capability: str, ttl_seconds: float = 300.0) -> str:
    """Contextually requests authorization and issues a short-lived lease for a credential. Returns lease metadata, not raw secret."""
    try:
        handle = secrets_service.acquire_secret(
            uri_or_id=secret_uri,
            requester=requester,
            purpose=purpose,
            capability=capability,
            ttl_seconds=ttl_seconds
        )
        return json.dumps({
            "status": "LEASE_ISSUED",
            "lease": handle.lease.to_dict(),
            "secret_id": handle.secret_id,
            "version": handle.version
        }, indent=2)
    except Exception as e:
        return f"ACQUISITION_DENIED: {e}"

@tool
def release_secret_lease(lease_id: str) -> str:
    """Releases and invalidates an active credential lease."""
    ok = secrets_service.release_secret(lease_id)
    return f"LEASE_RELEASED: lease_id='{lease_id}', success={ok}"

@tool
def rotate_secret(secret_id: str, new_plaintext: str) -> str:
    """Triggers zero-downtime rotation for a credential with pre-activation validation."""
    ok, ver, msg = secrets_service.rotate_secret(secret_id, new_plaintext)
    return f"ROTATION_RESULT: success={ok}, version={ver.version if ver else None}, message='{msg}'"

@tool
def revoke_secret(secret_id: str, reason: str = "Operator revoked") -> str:
    """Immediately revokes an active secret and terminates all associated active leases."""
    ok, msg = secrets_service.revoke_secret(secret_id, reason=reason)
    return f"REVOCATION_RESULT: success={ok}, message='{msg}'"

@tool
def mark_secret_compromised(secret_id: str, incident_id: str) -> str:
    """Triggers emergency compromise protocol: blocks access, revokes leases, and emits security alert."""
    ok, msg = secrets_service.mark_compromised(secret_id, incident_id=incident_id)
    return f"COMPROMISE_HANDLED: success={ok}, message='{msg}'"

@tool
def get_secrets_telemetry() -> str:
    """Returns safe operational metrics for secrets without revealing sensitive values."""
    telem = secrets_service.get_telemetry()
    return json.dumps(telem.to_dict(), indent=2)

@tool
def redact_sensitive_text(text: str) -> str:
    """Redacts known secrets, API keys, tokens, and authorization headers from arbitrary text."""
    from secrets.redaction import redaction_engine
    return redaction_engine.redact_text(text)

# --- Video Studio Optional Subsystem (Module 0 & 1) ---
from video_studio.service import video_studio_service
from video_studio.registry import video_studio_capability_registry
from video_studio.registry_models import VideoStudioCategory

@tool
def get_video_studio_status() -> str:
    """Queries the operational readiness, lifecycle status, and compute hardware of optional OMNIA Video Studio."""
    summary = video_studio_service.get_status_summary()
    return json.dumps(summary, indent=2)

@tool
def list_video_studio_capabilities(category: Optional[str] = None) -> str:
    """Lists registered Video Studio capabilities and their real implementation and availability states."""
    cat_enum = None
    if category:
        try:
            cat_enum = VideoStudioCategory(category.upper())
        except Exception:
            pass
    caps = video_studio_capability_registry.list(category=cat_enum)
    res = [
        {
            "id": c.id,
            "name": c.name,
            "category": c.category.value,
            "implementation_state": c.implementation_state.value,
            "is_enabled": video_studio_capability_registry.is_enabled(c.id),
            "is_available": video_studio_capability_registry.is_available(c.id),
            "runtime_status": video_studio_capability_registry.get_status(c.id).value
        }
        for c in caps
    ]
    return json.dumps(res, indent=2)

@tool
def check_video_studio_capability(capability_id: str) -> str:
    """Performs deep health and dependency check on a specific Video Studio capability."""
    health = video_studio_capability_registry.get_health(capability_id)
    return json.dumps(health.to_dict(), indent=2)

# --- Module 2: Media Asset Engine & Ingest Tools ---
@tool
def import_media_asset(
    project_id: str,
    file_path: str,
    display_name: Optional[str] = None,
    bin_id: Optional[str] = None,
    allow_duplicates: bool = False
) -> str:
    """Ingests, probes, validates, and registers a media file into the Video Studio project library."""
    from video_studio.media_ingest import media_ingest_service
    ok, asset, msg = media_ingest_service.ingest_file(
        project_id=project_id,
        source_file_path=file_path,
        display_name=display_name,
        target_bin_id=bin_id,
        allow_duplicates=allow_duplicates,
    )
    res = {
        "success": ok,
        "message": msg,
        "asset": asset.to_dict() if asset else None,
    }
    return json.dumps(res, indent=2)

@tool
def get_media_asset(project_id: str, asset_id: str) -> str:
    """Retrieves normalized metadata for an ingested media asset in Video Studio."""
    from video_studio.media_library import media_library_registry
    lib = media_library_registry.get_or_create(project_id)
    asset = lib.get_asset(asset_id)
    if not asset:
        return json.dumps({"error": f"Asset '{asset_id}' not found in project '{project_id}'."})
    return json.dumps(asset.to_dict(), indent=2)

@tool
def list_media_assets(project_id: str, bin_id: Optional[str] = None) -> str:
    """Lists media assets in a Video Studio project or specific bin."""
    from video_studio.media_library import media_library_registry, MediaSearchQuery
    lib = media_library_registry.get_or_create(project_id)
    if bin_id:
        assets = lib.search_assets(MediaSearchQuery(bin_id=bin_id, include_sub_bins=False))
    else:
        assets = lib.list_assets()
    return json.dumps([a.to_dict() for a in assets], indent=2)

@tool
def create_media_bin(project_id: str, name: str, parent_bin_id: Optional[str] = None, color: str = "#808080") -> str:
    """Creates a logical bin (folder) in the Video Studio project media library."""
    from video_studio.media_library import media_library_registry
    lib = media_library_registry.get_or_create(project_id)
    try:
        b = lib.create_bin(name=name, parent_bin_id=parent_bin_id, color=color)
        return json.dumps({"success": True, "bin": b.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def search_media_assets(
    project_id: str,
    query_text: Optional[str] = None,
    media_type: Optional[str] = None,
    tag: Optional[str] = None,
    bin_id: Optional[str] = None
) -> str:
    """Searches the project media library by text query, media type, tag, or bin."""
    from video_studio.media_library import media_library_registry, MediaSearchQuery
    from video_studio.media_models import AssetMediaType
    lib = media_library_registry.get_or_create(project_id)
    types = None
    if media_type:
        try:
            types = [AssetMediaType(media_type.upper())]
        except Exception:
            pass
    tags = [tag] if tag else None
    results = lib.search_assets(MediaSearchQuery(
        query_text=query_text,
        media_types=types,
        tags=tags,
        bin_id=bin_id
    ))
    return json.dumps([a.to_dict() for a in results], indent=2)

# --- Module 3: Media Analysis & Derivatives Tools ---
@tool
def analyze_media_asset(project_id: str, asset_id: str) -> str:
    """Runs the deep media analysis pipeline on an asset (container, streams, color, timecode)."""
    from video_studio.media_library import media_library_registry
    from video_studio.analysis_jobs import media_analysis_job_manager
    lib = media_library_registry.get_or_create(project_id)
    asset = lib.get_asset(asset_id)
    if not asset:
        return json.dumps({"error": f"Asset '{asset_id}' not found."})

    job = media_analysis_job_manager.submit_job(
        project_id=project_id,
        asset_id=asset_id,
        file_path=asset.file_location,
        fingerprint=asset.content_hash_sha256 or "default_fp",
    )
    # Execute analysis synchronously for tool invocation
    executed = media_analysis_job_manager.execute_job_synchronously(job.job_id)
    return json.dumps(executed.to_dict(), indent=2)

@tool
def get_asset_thumbnail(project_id: str, asset_id: str, timestamp_seconds: float = 1.0, width: int = 320, height: int = 180) -> str:
    """Generates or retrieves a cached representative video thumbnail for an asset."""
    from video_studio.media_library import media_library_registry
    from video_studio.thumbnail_engine import thumbnail_engine
    lib = media_library_registry.get_or_create(project_id)
    asset = lib.get_asset(asset_id)
    if not asset:
        return json.dumps({"error": f"Asset '{asset_id}' not found."})

    thumb_path = thumbnail_engine.generate_thumbnail(
        file_path=asset.file_location,
        asset_id=asset_id,
        timestamp_seconds=timestamp_seconds,
        width=width,
        height=height,
    )
    return json.dumps({"asset_id": asset_id, "timestamp_seconds": timestamp_seconds, "thumbnail_path": thumb_path}, indent=2)

@tool
def get_asset_waveform(project_id: str, asset_id: str, stream_index: int = 0, resolution: str = "MEDIUM") -> str:
    """Generates or retrieves cached normalized audio peak waveform data for an asset."""
    from video_studio.media_library import media_library_registry
    from video_studio.waveform_engine import waveform_engine
    from video_studio.analysis_models import WaveformResolution, ChannelMode
    lib = media_library_registry.get_or_create(project_id)
    asset = lib.get_asset(asset_id)
    if not asset:
        return json.dumps({"error": f"Asset '{asset_id}' not found."})

    res_enum = WaveformResolution.MEDIUM
    try:
        res_enum = WaveformResolution(resolution.upper())
    except Exception:
        pass

    wf = waveform_engine.generate_waveform(
        file_path=asset.file_location,
        asset_id=asset_id,
        stream_index=stream_index,
        resolution=res_enum,
        channel_mode=ChannelMode.COMBINED,
        duration_seconds=asset.duration_seconds or 10.0,
        channels=asset.audio_channels or 2,
        sample_rate=asset.sample_rate or 48000,
    )
    return json.dumps(waveform_engine._serialize_dataset(wf), indent=2)

@tool
def generate_contact_sheet(project_id: str, asset_id: str, frame_count: int = 9) -> str:
    """Generates a contact sheet of representative chronological frames for shot analysis."""
    from video_studio.media_library import media_library_registry
    from video_studio.thumbnail_engine import thumbnail_engine
    lib = media_library_registry.get_or_create(project_id)
    asset = lib.get_asset(asset_id)
    if not asset:
        return json.dumps({"error": f"Asset '{asset_id}' not found."})

    res = thumbnail_engine.generate_contact_sheet(
        file_path=asset.file_location,
        asset_id=asset_id,
        duration_seconds=asset.duration_seconds or 10.0,
        frame_count=frame_count,
    )
    return json.dumps({
        "asset_id": res.asset_id,
        "total_frames": res.total_frames,
        "frames": [
            {"index": f.frame_index, "timestamp": f.timestamp_seconds, "timecode": f.timecode_str, "uri": f.image_uri}
            for f in res.frames
        ]
    }, indent=2)

# --- Module 4: Sequence & Timeline Tools ---
@tool
def create_video_sequence(project_id: str, name: str, fps: float = 24.0, width: int = 1920, height: int = 1080) -> str:
    """Creates a new canonical non-destructive timeline sequence in Video Studio."""
    from video_studio.timeline_service import timeline_service
    from video_studio.timeline_models import SequenceSettings
    settings = SequenceSettings(width=width, height=height, frame_rate=fps)
    seq = timeline_service.create_sequence(project_id=project_id, name=name, settings=settings)
    return json.dumps(seq.to_dict(), indent=2)

@tool
def get_video_sequence(project_id: str, sequence_id: str) -> str:
    """Retrieves full sequence structure including tracks, clips, markers, and regions."""
    from video_studio.timeline_service import timeline_service
    seq = timeline_service.get_sequence(sequence_id)
    if not seq:
        return json.dumps({"error": f"Sequence '{sequence_id}' not found."})
    return json.dumps(seq.to_dict(), indent=2)

@tool
def add_timeline_clip(
    project_id: str,
    sequence_id: str,
    track_id: str,
    asset_id: str,
    start_frame: int = 0,
    duration_frames: int = 24,
    source_in_frame: int = 0,
    name: str = "Clip"
) -> str:
    """Places a non-destructive media clip on a timeline track."""
    from video_studio.timeline_service import timeline_service
    item = timeline_service.add_clip(
        sequence_id=sequence_id,
        track_id=track_id,
        asset_id=asset_id,
        name=name,
        start_frame=start_frame,
        duration_frames=duration_frames,
        source_in_frame=source_in_frame,
    )
    if not item:
        return json.dumps({"success": False, "error": f"Failed to place clip on track {track_id}."})
    return json.dumps({"success": True, "item": item.to_dict()}, indent=2)

@tool
def add_timeline_marker(project_id: str, sequence_id: str, frame: int, name: str = "Marker", category: str = "GENERAL", color_hex: str = "#00f0ff") -> str:
    """Adds a marker to a sequence timeline."""
    from video_studio.timeline_service import timeline_service
    from video_studio.timeline_models import MarkerCategory
    cat = MarkerCategory.GENERAL
    try:
        cat = MarkerCategory(category.upper())
    except Exception:
        pass
    m = timeline_service.add_marker(sequence_id=sequence_id, frame=frame, name=name, category=cat, color_hex=color_hex)
    if not m:
        return json.dumps({"success": False, "error": f"Failed to add marker to {sequence_id}."})
    return json.dumps({"success": True, "marker": m.to_dict()}, indent=2)

@tool
def query_timeline_items(project_id: str, sequence_id: str, start_frame: int, end_frame: int) -> str:
    """Queries all timeline items intersecting a specific frame range."""
    from video_studio.timeline_service import timeline_service
    from video_studio.timeline_query import timeline_query_engine
    seq = timeline_service.get_sequence(sequence_id)
    if not seq:
        return json.dumps({"error": f"Sequence '{sequence_id}' not found."})
    items = timeline_query_engine.get_items_intersecting_range(seq, start_frame, end_frame)
    return json.dumps([it.to_dict() for it in items], indent=2)

@tool
def trim_timeline_item(project_id: str, sequence_id: str, item_id: str, trim_type: str, delta_frames: int) -> str:
    """Trims timeline item start (TRIM_START) or end (TRIM_END) by delta frames."""
    from video_studio.timeline_service import timeline_service
    from video_studio.timeline_edit_engine import timeline_edit_engine
    seq = timeline_service.get_sequence(sequence_id)
    if not seq:
        return json.dumps({"success": False, "error": f"Sequence '{sequence_id}' not found."})
    try:
        if trim_type.upper() == "START" or trim_type.upper() == "TRIM_START":
            ok = timeline_edit_engine.trim_start(seq, item_id, delta_frames)
        else:
            ok = timeline_edit_engine.trim_end(seq, item_id, delta_frames)
        return json.dumps({"success": ok, "revision": seq.revision, "duration_frames": seq.duration_frames}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def split_timeline_clip(project_id: str, sequence_id: str, item_id: str, split_frame: int) -> str:
    """Splits (razor cuts) a timeline item at split_frame into two slices."""
    from video_studio.timeline_service import timeline_service
    from video_studio.timeline_edit_engine import timeline_edit_engine
    seq = timeline_service.get_sequence(sequence_id)
    if not seq:
        return json.dumps({"success": False, "error": f"Sequence '{sequence_id}' not found."})
    try:
        left, right = timeline_edit_engine.split_item(seq, item_id, split_frame)
        return json.dumps({
            "success": True,
            "revision": seq.revision,
            "left_item": left.to_dict(),
            "right_item": right.to_dict(),
        }, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def move_timeline_clip(project_id: str, sequence_id: str, item_id: str, new_start_frame: int, target_track_id: str = "") -> str:
    """Moves a timeline clip to a new start frame, optionally moving to a new track."""
    from video_studio.timeline_service import timeline_service
    from video_studio.timeline_edit_engine import timeline_edit_engine
    seq = timeline_service.get_sequence(sequence_id)
    if not seq:
        return json.dumps({"success": False, "error": f"Sequence '{sequence_id}' not found."})
    try:
        tgt_track = target_track_id if target_track_id else None
        ok = timeline_edit_engine.move_item(seq, item_id, new_start_frame, target_track_id=tgt_track)
        return json.dumps({"success": ok, "revision": seq.revision}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def set_timeline_clip_enabled(project_id: str, sequence_id: str, item_id: str, is_enabled: bool) -> str:
    """Toggles active state of a clip on the timeline."""
    from video_studio.timeline_service import timeline_service
    from video_studio.timeline_edit_engine import timeline_edit_engine
    seq = timeline_service.get_sequence(sequence_id)
    if not seq:
        return json.dumps({"success": False, "error": f"Sequence '{sequence_id}' not found."})
    try:
        ok = timeline_edit_engine.set_item_enabled(seq, item_id, is_enabled)
        return json.dumps({"success": ok, "revision": seq.revision}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def link_timeline_items(project_id: str, sequence_id: str, item_ids_json: str) -> str:
    """Links multiple timeline items so they move in sync."""
    from video_studio.timeline_service import timeline_service
    from video_studio.timeline_edit_engine import timeline_edit_engine
    seq = timeline_service.get_sequence(sequence_id)
    if not seq:
        return json.dumps({"success": False, "error": f"Sequence '{sequence_id}' not found."})
    try:
        ids = json.loads(item_ids_json)
        link_id = timeline_edit_engine.link_items(seq, ids)
        return json.dumps({"success": True, "link_id": link_id, "revision": seq.revision}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def undo_timeline_edit(project_id: str, sequence_id: str) -> str:
    """Rolls back the most recent timeline edit operation."""
    from video_studio.timeline_service import timeline_service
    from video_studio.timeline_edit_engine import timeline_edit_engine
    seq = timeline_service.get_sequence(sequence_id)
    if not seq:
        return json.dumps({"success": False, "error": f"Sequence '{sequence_id}' not found."})
    ok = timeline_edit_engine.undo(seq)
    return json.dumps({"success": ok, "revision": seq.revision}, indent=2)

@tool
def redo_timeline_edit(project_id: str, sequence_id: str) -> str:
    """Re-applies the most recent undone timeline operation."""
    from video_studio.timeline_service import timeline_service
    from video_studio.timeline_edit_engine import timeline_edit_engine
    seq = timeline_service.get_sequence(sequence_id)
    if not seq:
        return json.dumps({"success": False, "error": f"Sequence '{sequence_id}' not found."})
    ok = timeline_edit_engine.redo(seq)
    return json.dumps({"success": ok, "revision": seq.revision}, indent=2)

@tool
def ripple_trim_timeline_item(project_id: str, sequence_id: str, item_id: str, trim_side: str, delta_frames: int, affected_tracks_json: str = "[]", ripple_linked: bool = True) -> str:
    """Ripple trims an item at start or end, shifting downstream content."""
    from video_studio.timeline_service import timeline_service
    from video_studio.timeline_advanced_edit import advanced_timeline_edit_engine
    seq = timeline_service.get_sequence(sequence_id)
    if not seq:
        return json.dumps({"success": False, "error": f"Sequence '{sequence_id}' not found."})
    try:
        aff_tracks = json.loads(affected_tracks_json) if affected_tracks_json else None
        if not aff_tracks:
            aff_tracks = None
        if "START" in trim_side.upper():
            ok = advanced_timeline_edit_engine.ripple_trim_start(seq, item_id, delta_frames, affected_track_ids=aff_tracks, ripple_linked=ripple_linked)
        else:
            ok = advanced_timeline_edit_engine.ripple_trim_end(seq, item_id, delta_frames, affected_track_ids=aff_tracks, ripple_linked=ripple_linked)
        return json.dumps({"success": ok, "revision": seq.revision, "duration_frames": seq.duration_frames}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def rolling_edit_timeline(project_id: str, sequence_id: str, prev_item_id: str, next_item_id: str, delta_frames: int, roll_linked: bool = True) -> str:
    """Performs a rolling edit between two adjacent clips, maintaining combined duration."""
    from video_studio.timeline_service import timeline_service
    from video_studio.timeline_advanced_edit import advanced_timeline_edit_engine
    seq = timeline_service.get_sequence(sequence_id)
    if not seq:
        return json.dumps({"success": False, "error": f"Sequence '{sequence_id}' not found."})
    try:
        ok = advanced_timeline_edit_engine.rolling_edit(seq, prev_item_id, next_item_id, delta_frames, roll_linked=roll_linked)
        return json.dumps({"success": ok, "revision": seq.revision}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def slip_edit_timeline_clip(project_id: str, sequence_id: str, item_id: str, delta_frames: int, slip_linked: bool = True) -> str:
    """Slips source media range without altering timeline position or duration."""
    from video_studio.timeline_service import timeline_service
    from video_studio.timeline_advanced_edit import advanced_timeline_edit_engine
    seq = timeline_service.get_sequence(sequence_id)
    if not seq:
        return json.dumps({"success": False, "error": f"Sequence '{sequence_id}' not found."})
    try:
        ok = advanced_timeline_edit_engine.slip_edit(seq, item_id, delta_frames, slip_linked=slip_linked)
        return json.dumps({"success": ok, "revision": seq.revision}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def slide_edit_timeline_clip(project_id: str, sequence_id: str, item_id: str, delta_frames: int, slide_linked: bool = True) -> str:
    """Slides an item along timeline while trimming surrounding clips."""
    from video_studio.timeline_service import timeline_service
    from video_studio.timeline_advanced_edit import advanced_timeline_edit_engine
    seq = timeline_service.get_sequence(sequence_id)
    if not seq:
        return json.dumps({"success": False, "error": f"Sequence '{sequence_id}' not found."})
    try:
        ok = advanced_timeline_edit_engine.slide_edit(seq, item_id, delta_frames, slide_linked=slide_linked)
        return json.dumps({"success": ok, "revision": seq.revision}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def ripple_delete_timeline_clips(project_id: str, sequence_id: str, item_ids_json: str, affected_tracks_json: str = "[]", ripple_linked: bool = True) -> str:
    """Deletes clips and ripples downstream timeline content leftward."""
    from video_studio.timeline_service import timeline_service
    from video_studio.timeline_advanced_edit import advanced_timeline_edit_engine
    seq = timeline_service.get_sequence(sequence_id)
    if not seq:
        return json.dumps({"success": False, "error": f"Sequence '{sequence_id}' not found."})
    try:
        ids = json.loads(item_ids_json)
        aff_tracks = json.loads(affected_tracks_json) if affected_tracks_json else None
        if not aff_tracks:
            aff_tracks = None
        ok = advanced_timeline_edit_engine.ripple_delete(seq, ids, affected_track_ids=aff_tracks, ripple_linked=ripple_linked)
        return json.dumps({"success": ok, "revision": seq.revision, "duration_frames": seq.duration_frames}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def manage_timeline_gaps(project_id: str, sequence_id: str, action: str, track_id: str = "", frame: int = 0, duration_frames: int = 0) -> str:
    """Detects, closes, or inserts timeline gaps ('DETECT', 'CLOSE', 'INSERT')."""
    from video_studio.timeline_service import timeline_service
    from video_studio.timeline_advanced_edit import advanced_timeline_edit_engine
    seq = timeline_service.get_sequence(sequence_id)
    if not seq:
        return json.dumps({"success": False, "error": f"Sequence '{sequence_id}' not found."})
    try:
        act = action.upper()
        if act == "DETECT":
            gaps = advanced_timeline_edit_engine.detect_gaps(seq, track_id=track_id if track_id else None)
            return json.dumps({"success": True, "gaps": [g.to_dict() for g in gaps]}, indent=2)
        elif act == "CLOSE":
            ok = advanced_timeline_edit_engine.close_gap(seq, track_id, gap_start_frame=frame)
            return json.dumps({"success": ok, "revision": seq.revision}, indent=2)
        elif act == "INSERT":
            ok = advanced_timeline_edit_engine.insert_gap(seq, track_id, insert_frame=frame, duration_frames=duration_frames)
            return json.dumps({"success": ok, "revision": seq.revision}, indent=2)
        else:
            return json.dumps({"success": False, "error": f"Unknown action: {action}"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


# --- Video Studio Module 7: Playback Engine Tools ---
@tool
def create_playback_session(sequence_id: str, quality: str = "FULL", target_fps: float = 30.0) -> str:
    """Creates a real-time playback session for a timeline sequence ('FULL', 'HALF', 'QUARTER', 'DRAFT')."""
    from video_studio.timeline_service import timeline_service
    from video_studio.playback_engine import playback_engine
    from video_studio.playback_models import PlaybackQuality
    seq = timeline_service.get_sequence(sequence_id)
    if not seq:
        return json.dumps({"success": False, "error": f"Sequence '{sequence_id}' not found."})
    try:
        q_enum = PlaybackQuality[quality.upper()] if quality.upper() in PlaybackQuality.__members__ else PlaybackQuality.FULL
        session = playback_engine.create_session(seq, quality=q_enum, target_fps=target_fps)
        return json.dumps({"success": True, "session": session.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def control_playback_session(session_id: str, command: str, frame: int = 0, delta: int = 1) -> str:
    """Controls a playback session ('PLAY', 'PAUSE', 'STOP', 'SEEK', 'STEP', 'RENDER')."""
    from video_studio.playback_engine import playback_engine
    cmd = command.upper()
    try:
        if cmd == "PLAY":
            s = playback_engine.play(session_id)
            return json.dumps({"success": True, "session": s.to_dict()}, indent=2)
        elif cmd == "PAUSE":
            s = playback_engine.pause(session_id)
            return json.dumps({"success": True, "session": s.to_dict()}, indent=2)
        elif cmd == "STOP":
            s = playback_engine.stop(session_id)
            return json.dumps({"success": True, "session": s.to_dict()}, indent=2)
        elif cmd == "SEEK":
            f = playback_engine.seek(session_id, frame)
            return json.dumps({"success": True, "current_frame": f.timeline_frame, "is_gap": f.is_gap, "frame": f.to_dict()}, indent=2)
        elif cmd == "STEP":
            f = playback_engine.step_frame(session_id, delta=delta)
            return json.dumps({"success": True, "current_frame": f.timeline_frame, "is_gap": f.is_gap, "frame": f.to_dict()}, indent=2)
        elif cmd == "RENDER":
            f = playback_engine.render_frame(session_id, frame)
            return json.dumps({"success": True, "current_frame": f.timeline_frame, "is_gap": f.is_gap, "frame": f.to_dict()}, indent=2)
        else:
            return json.dumps({"success": False, "error": f"Unknown command: {command}"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def get_playback_metrics(session_id: str) -> str:
    """Retrieves real-time playback telemetry, dropped frames, and decoding statistics."""
    from video_studio.playback_engine import playback_engine
    session = playback_engine.get_session(session_id)
    if not session:
        return json.dumps({"success": False, "error": f"Session '{session_id}' not found."})
    return json.dumps({"success": True, "metrics": session.metrics.to_dict()}, indent=2)


# --- Video Studio Module 8: Animation & Keyframe Automation Tools ---
@tool
def add_property_keyframe(property_id: str, frame: int, value: float, interpolation: str = "LINEAR", handle_left: float = 0.0, handle_right: float = 0.0) -> str:
    """Adds or updates a keyframe on an animatable property (e.g. opacity, scale, position)."""
    from video_studio.animation_service import animation_service
    from video_studio.animation_models import InterpolationMode
    try:
        interp_enum = InterpolationMode[interpolation.upper()] if interpolation.upper() in InterpolationMode.__members__ else InterpolationMode.LINEAR
        kf = animation_service.set_keyframe(
            property_id=property_id,
            frame=frame,
            value=value,
            interpolation=interp_enum,
            handle_left=(handle_left, 0.0),
            handle_right=(handle_right, 0.0),
        )
        return json.dumps({"success": True, "keyframe": kf.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def evaluate_animated_property(property_id: str, frame: int) -> str:
    """Evaluates an animatable property value at a specific frame using Bezier/Linear interpolation."""
    from video_studio.animation_service import animation_service
    from video_studio.animation_evaluator import animation_evaluator
    prop = animation_service.get_property(property_id)
    if not prop:
        return json.dumps({"success": False, "error": f"Property '{property_id}' not found."})
    try:
        val = animation_evaluator.evaluate(prop, frame)
        return json.dumps({"success": True, "property_id": property_id, "frame": frame, "value": val}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def query_property_keyframes(property_id: str) -> str:
    """Returns all keyframes defined on an animatable property."""
    from video_studio.animation_service import animation_service
    prop = animation_service.get_property(property_id)
    if not prop:
        return json.dumps({"success": False, "error": f"Property '{property_id}' not found."})
    return json.dumps({
        "success": True,
        "property_id": prop.property_id,
        "property_name": prop.property_name,
        "target_id": prop.target_id,
        "default_value": prop.default_value,
        "keyframes": [kf.to_dict() for kf in prop.keyframes]
    }, indent=2)



# --- Video Studio Module 9: Audio Engine & Mixer Tools ---
@tool
def render_timeline_audio_slice(sequence_id: str, start_frame: int, duration_frames: int, sample_rate: int = 48000) -> str:
    """Renders and mixes an audio slice across tracks and buses with meters."""
    from video_studio.timeline_service import timeline_service
    from video_studio.audio_service import audio_engine_service
    seq = timeline_service.get_sequence(sequence_id)
    if not seq:
        return json.dumps({"success": False, "error": f"Sequence '{sequence_id}' not found."})
    try:
        buf = audio_engine_service.render_timeline_audio(seq, start_frame=start_frame, duration_frames=duration_frames, sample_rate=sample_rate)
        from video_studio.audio_models import AudioMeterSnapshot
        meters = AudioMeterSnapshot.calculate(buf)
        return json.dumps({
            "success": True,
            "samples_count": buf.samples,
            "channels": buf.channels,
            "sample_rate": buf.sample_rate,
            "meters": meters.to_dict(),
        }, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def configure_audio_bus(sequence_id: str, bus_id: str, name: str, gain_db: float = 0.0, pan: float = 0.0, target_bus_id: str = "") -> str:
    """Creates or updates an audio submix bus with routing and level controls."""
    from video_studio.timeline_service import timeline_service
    from video_studio.audio_mixer import multitrack_audio_mixer
    from video_studio.audio_models import AudioBus, AudioBusType
    seq = timeline_service.get_sequence(sequence_id)
    if not seq:
        return json.dumps({"success": False, "error": f"Sequence '{sequence_id}' not found."})
    try:
        graph = multitrack_audio_mixer.get_or_create_routing(seq)
        bus = AudioBus(
            bus_id=bus_id,
            name=name,
            bus_type=AudioBusType.SUBMIX,
            gain_db=gain_db,
            pan=pan,
            target_bus_id=target_bus_id if target_bus_id else None,
        )
        graph.add_bus(bus)
        if target_bus_id:
            graph.route_bus(bus_id, target_bus_id)
        return json.dumps({"success": True, "bus": bus.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def get_audio_meters(sequence_id: str) -> str:
    """Returns the most recent peak and RMS audio meter readings for the sequence."""
    from video_studio.audio_service import audio_engine_service
    meters = audio_engine_service.get_meters(sequence_id)
    return json.dumps({"success": True, "meters": meters}, indent=2)

@tool
def list_audio_devices() -> str:
    """Discovers available audio output devices with capability reporting."""
    from video_studio.audio_service import audio_engine_service
    devices = audio_engine_service.list_devices()
    return json.dumps({
        "success": True,
        "devices": [
            {
                "device_id": d.device_id,
                "name": d.name,
                "is_default": d.is_default,
                "max_channels": d.max_channels,
                "supported_sample_rates": d.supported_sample_rates,
                "is_available": d.is_available,
            }
            for d in devices
        ]
    }, indent=2)

# --- Video Studio Module 10 & 11: Effects & Compositing Tools ---
@tool
def add_video_effect(clip_id: str, effect_id: str, parameters_json: str = "{}") -> str:
    """Adds a video effect to a timeline clip (e.g., 'effect.transform', 'effect.color_correction', 'effect.opacity')."""
    from video_studio.effects_service import effects_service
    try:
        params = json.loads(parameters_json) if parameters_json else {}
        inst = effects_service.add_effect_to_clip(clip_id, effect_id, parameters=params)
        return json.dumps({"success": True, "effect": inst.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def configure_clip_compositing(clip_id: str, opacity: float = 1.0, blend_mode: str = "NORMAL") -> str:
    """Configures layer opacity and blend mode ('NORMAL', 'MULTIPLY', 'SCREEN', 'ADD', 'DIFFERENCE', 'OVERLAY')."""
    from video_studio.compositor import multilayer_compositor
    from video_studio.compositing_models import BlendMode
    try:
        b_enum = BlendMode(blend_mode.upper())
        multilayer_compositor.set_clip_opacity(clip_id, opacity)
        multilayer_compositor.set_clip_blend_mode(clip_id, b_enum)
        return json.dumps({"success": True, "clip_id": clip_id, "opacity": opacity, "blend_mode": b_enum.value}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def list_available_video_effects() -> str:
    """Lists all registered video effect processors and their parameter schemas."""
    from video_studio.effects_processors import effect_processor_registry
    effects = effect_processor_registry.list_effects()
    return json.dumps({"success": True, "effects": effects}, indent=2)

# --- Video Studio Module 12: Transition Tools ---
@tool
def add_video_transition(
    sequence_id: str,
    track_id: str,
    transition_type: str,
    cut_frame: int,
    duration_frames: int = 24,
    alignment: str = "CENTER_ON_CUT",
    direction: str = "LEFT_TO_RIGHT",
    parameters_json: str = "{}",
    crossfade_curve: str = "EQUAL_POWER"
) -> str:
    """Adds a non-destructive transition (DISSOLVE, FADE_TO_BLACK, FADE_FROM_BLACK, WIPE, PUSH, SLIDE, AUDIO_CROSSFADE)."""
    from video_studio.timeline_service import timeline_service
    from video_studio.transitions_service import transitions_service
    from video_studio.transitions_models import TransitionType, TransitionAlignment, TransitionDirection, CrossfadeCurve
    import json
    try:
        seq = timeline_service.get_sequence(sequence_id)
        if not seq:
            return json.dumps({"success": False, "error": f"Sequence '{sequence_id}' not found."})

        ttype = TransitionType(transition_type.upper())
        align = TransitionAlignment(alignment.upper())
        dir_enum = TransitionDirection(direction.upper())
        curve = CrossfadeCurve(crossfade_curve.upper())
        params = json.loads(parameters_json) if parameters_json else {}

        tr = transitions_service.add_transition(
            sequence=seq,
            track_id=track_id,
            transition_type=ttype,
            cut_frame=cut_frame,
            duration_frames=duration_frames,
            alignment=align,
            direction=dir_enum,
            parameters=params,
            crossfade_curve=curve,
        )
        return json.dumps({"success": True, "transition": tr.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def validate_transition_handles(
    sequence_id: str,
    track_id: str,
    outgoing_clip_id: str,
    incoming_clip_id: str,
    duration_frames: int = 24,
    alignment: str = "CENTER_ON_CUT"
) -> str:
    """Validates whether clips have sufficient head and tail source handles for a transition."""
    from video_studio.timeline_service import timeline_service
    from video_studio.transitions_service import transitions_service
    from video_studio.transitions_models import TransitionAlignment
    import json
    try:
        seq = timeline_service.get_sequence(sequence_id)
        if not seq:
            return json.dumps({"success": False, "error": f"Sequence '{sequence_id}' not found."})

        align = TransitionAlignment(alignment.upper())
        res = transitions_service.validate_source_handles(
            sequence=seq,
            track_id=track_id,
            outgoing_clip_id=outgoing_clip_id,
            incoming_clip_id=incoming_clip_id,
            duration_frames=duration_frames,
            alignment=align,
        )
        return json.dumps({"success": True, "validation": res.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def list_transition_presets() -> str:
    """Lists built-in transition presets and their parameters."""
    from video_studio.transitions_service import transitions_service
    import json
    presets = transitions_service.list_presets()
    return json.dumps({"success": True, "presets": presets}, indent=2)

# --- Video Studio Module 13: Captions & Subtitles Tools ---
@tool
def create_subtitle_track(
    project_id: str,
    name: str = "Subtitles",
    language: str = "en",
    format: str = "SRT",
    sequence_id: str = ""
) -> str:
    """Creates a new subtitle or caption document for a project or sequence."""
    from video_studio.captions_service import captions_service
    from video_studio.captions_models import SubtitleFormat
    import json
    try:
        fmt = SubtitleFormat(format.upper())
        doc = captions_service.create_subtitle_document(
            project_id=project_id,
            name=name,
            language=language,
            format=fmt,
            sequence_id=sequence_id or None,
        )
        return json.dumps({"success": True, "document": doc.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def add_subtitle_cue_item(
    document_id: str,
    start_seconds: float,
    end_seconds: float,
    text: str,
    speaker: str = ""
) -> str:
    """Adds a timed subtitle cue to a subtitle document."""
    from video_studio.captions_service import captions_service
    import json
    try:
        cue = captions_service.add_cue(
            document_id=document_id,
            start_time_seconds=start_seconds,
            end_time_seconds=end_seconds,
            text=text,
            speaker_name=speaker or None,
        )
        return json.dumps({"success": True, "cue": cue.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def import_subtitle_file(
    project_id: str,
    content: str,
    format: str = "SRT",
    sequence_id: str = ""
) -> str:
    """Parses and imports SRT or WebVTT content into a new subtitle document."""
    from video_studio.captions_service import captions_service
    from video_studio.captions_models import SubtitleFormat
    import json
    try:
        fmt = SubtitleFormat(format.upper())
        doc = captions_service.import_subtitles(
            project_id=project_id,
            content=content,
            format=fmt,
            sequence_id=sequence_id or None,
        )
        return json.dumps({"success": True, "document": doc.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def export_subtitle_file(document_id: str, format: str = "SRT") -> str:
    """Exports a subtitle document to standard SRT or WebVTT format."""
    from video_studio.captions_service import captions_service
    from video_studio.captions_models import SubtitleFormat
    import json
    try:
        fmt = SubtitleFormat(format.upper())
        out = captions_service.export_subtitles(document_id, format=fmt)
        return json.dumps({"success": True, "format": fmt.value, "content": out}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def search_transcript_text(transcript_id: str, query: str) -> str:
    """Searches transcript text and returns matching timed segments."""
    from video_studio.captions_service import captions_service
    import json
    try:
        results = captions_service.search_transcript(transcript_id, query)
        return json.dumps({"success": True, "results": results}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

# --- Video Studio Module 14: Motion Graphics & Titles Tools ---
@tool
def create_graphics_composition(
    project_id: str,
    name: str = "Title Composition",
    width: int = 1920,
    height: int = 1080,
    duration_frames: int = 120,
    sequence_id: str = "",
    timeline_start_frame: int = 0
) -> str:
    """Creates a new motion graphics and animated title composition."""
    from video_studio.motion_graphics_service import motion_graphics_service
    import json
    try:
        comp = motion_graphics_service.create_composition(
            project_id=project_id,
            name=name,
            width=width,
            height=height,
            duration_frames=duration_frames,
            sequence_id=sequence_id or None,
            timeline_start_frame=timeline_start_frame,
        )
        return json.dumps({"success": True, "composition": comp.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def add_graphics_layer(
    composition_id: str,
    name: str,
    layer_type: str,
    text_content: str = "",
    font_size: int = 48,
    fill_color: str = "#FFFFFF",
    pos_x: float = 0.0,
    pos_y: float = 0.0,
    width: float = 200.0,
    height: float = 100.0,
    corner_radius: float = 0.0,
    animation_preset: str = "NONE"
) -> str:
    """Adds a text, rectangle, ellipse, or line layer to a motion graphics composition."""
    from video_studio.motion_graphics_service import motion_graphics_service
    from video_studio.motion_graphics_models import GraphicLayerType, GraphicTransform, TypographyAnimationPreset
    import json
    try:
        l_type = GraphicLayerType(layer_type.upper())
        preset = TypographyAnimationPreset(animation_preset.upper())
        tf = GraphicTransform(x=pos_x, y=pos_y)
        layer = motion_graphics_service.add_layer(
            composition_id=composition_id,
            name=name,
            layer_type=l_type,
            transform=tf,
            text_content=text_content,
            font_size=font_size,
            fill_color=fill_color,
            width=width,
            height=height,
            corner_radius=corner_radius,
            animation_preset=preset,
        )
        return json.dumps({"success": True, "layer": layer.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def instantiate_graphics_template(
    project_id: str,
    template_id: str,
    placeholders_json: str = "{}",
    sequence_id: str = "",
    timeline_start_frame: int = 0
) -> str:
    """Instantiates a motion graphics template (e.g. Centered Title, Lower Third) with placeholder text."""
    from video_studio.motion_graphics_service import motion_graphics_service
    import json
    try:
        placeholders = json.loads(placeholders_json) if placeholders_json else {}
        comp = motion_graphics_service.instantiate_template(
            template_id=template_id,
            project_id=project_id,
            placeholders=placeholders,
            sequence_id=sequence_id or None,
            timeline_start_frame=timeline_start_frame,
        )
        return json.dumps({"success": True, "composition": comp.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def apply_clip_speed_remap(
    sequence_id: str,
    item_id: str,
    speed: float = 1.0,
    is_reverse: bool = False,
    ripple: bool = False,
    interpolation_mode: str = "DUPLICATION",
    audio_speed_mode: str = "RESAMPLE_PITCH"
) -> str:
    """Applies non-destructive constant or reverse speed remapping to a timeline clip."""
    from video_studio.speed_service import speed_service
    from video_studio.speed_models import FrameInterpolationMode, AudioSpeedMode
    import json
    try:
        interp = FrameInterpolationMode(interpolation_mode.upper())
        audio_m = AudioSpeedMode(audio_speed_mode.upper())
        ok, msg, doc = speed_service.apply_constant_speed(
            sequence_id=sequence_id,
            item_id=item_id,
            speed=speed,
            is_reverse=is_reverse,
            ripple=ripple,
            audio_mode=audio_m,
            interpolation_mode=interp,
        )
        return json.dumps({"success": ok, "message": msg, "remap": doc.to_dict() if doc else None}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def add_clip_freeze_frame(
    sequence_id: str,
    item_id: str,
    playhead_frame: int,
    duration_frames: int = 24
) -> str:
    """Freezes playback at a specific playhead frame for a specified duration."""
    from video_studio.speed_service import speed_service
    import json
    try:
        ok, msg, freeze = speed_service.add_freeze_frame(
            sequence_id=sequence_id,
            item_id=item_id,
            playhead_frame=playhead_frame,
            duration_frames=duration_frames,
        )
        return json.dumps({"success": ok, "message": msg, "freeze": freeze.to_dict() if freeze else None}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def apply_clip_color_grade(
    item_id: str,
    exposure: float = 0.0,
    contrast: float = 1.0,
    temperature: float = 0.0,
    tint: float = 0.0,
    saturation: float = 1.0,
    vibrance: float = 0.0
) -> str:
    """Applies primary color correction adjustments to a timeline clip."""
    from video_studio.color_service import color_service
    from video_studio.color_models import PrimaryGrade
    import json
    try:
        grade = color_service.get_clip_grade(item_id)
        grade.primary = PrimaryGrade(
            exposure=exposure,
            contrast=contrast,
            temperature=temperature,
            tint=tint,
            saturation=saturation,
            vibrance=vibrance,
        )
        updated = color_service.update_clip_grade(item_id, grade)
        return json.dumps({"success": True, "grade": updated.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def apply_cinematic_look(item_id: str, look_id: str) -> str:
    """Applies a curated creative Look preset (e.g. 'look_golden_hour', 'look_teal_orange', 'look_noir') to a clip."""
    from video_studio.color_service import color_service
    import json
    try:
        grade = color_service.apply_look_to_clip(look_id, item_id)
        if not grade:
            return json.dumps({"success": False, "error": f"Look '{look_id}' not found."}, indent=2)
        return json.dumps({"success": True, "grade": grade.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def export_video_sequence(
    project_id: str,
    sequence_id: str,
    output_path: str,
    preset_id: str = "preset_1080p_hq"
) -> str:
    """Renders and encodes a video studio sequence into a validated media file."""
    from video_studio.export_service import export_service
    import json
    try:
        ok, msg, job = export_service.create_render_job(
            project_id=project_id,
            sequence_id=sequence_id,
            output_path=output_path,
            preset_id=preset_id,
        )
        if not ok or not job:
            return json.dumps({"success": False, "error": msg}, indent=2)

        report = export_service.execute_job(job.job_id)
        return json.dumps({"success": report.is_valid, "job": job.to_dict(), "validation": report.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def list_graphics_templates() -> str:
    """Lists available built-in motion graphics and title templates."""
    from video_studio.motion_graphics_service import motion_graphics_service
    import json
    try:
        templates = motion_graphics_service.list_templates()
        return json.dumps({"success": True, "templates": templates}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def list_external_connectors() -> str:
    """Lists all registered external connectors and their operations."""
    from connectors.service import connector_gateway
    defs = connector_gateway.list_connectors()
    res = []
    for d in defs:
        res.append({
            "connector_id": d.connector_id,
            "provider_id": d.provider_id,
            "name": d.name,
            "version": d.version,
            "operations_count": len(d.operations),
            "operations": list(d.operations.keys()),
            "status": d.status.value
        })
    return json.dumps(res, indent=2)

@tool
def get_connector_definition(connector_id: str) -> str:
    """Retrieves full specification and operations for an external connector."""
    from connectors.service import connector_gateway
    d = connector_gateway.get_connector(connector_id)
    if not d:
        return json.dumps({"error": f"Connector '{connector_id}' not found."})
    return json.dumps({
        "connector_id": d.connector_id,
        "provider_id": d.provider_id,
        "name": d.name,
        "version": d.version,
        "description": d.description,
        "risk_profile": d.risk_profile,
        "operations": {
            op_id: {
                "name": op.name,
                "type": op.operation_type.value,
                "path": op.path,
                "method": op.method,
                "risk_level": op.risk_level,
                "idempotent": op.idempotent,
                "requires_approval": op.requires_approval
            }
            for op_id, op in d.operations.items()
        }
    }, indent=2)

@tool
def create_connector_instance(
    instance_id: str,
    connector_id: str,
    base_url: str,
    environment: str = "SANDBOX",
    credential_reference: str = ""
) -> str:
    """Creates a configured instance of an external connector."""
    from connectors.service import connector_gateway
    from connectors.models import Environment
    try:
        env_enum = Environment(environment.upper())
    except ValueError:
        env_enum = Environment.SANDBOX

    inst = connector_gateway.create_instance(
        instance_id=instance_id,
        connector_id=connector_id,
        base_url=base_url,
        environment=env_enum,
        credential_reference=credential_reference if credential_reference else None
    )
    return json.dumps({
        "success": True,
        "instance_id": inst.instance_id,
        "connector_id": inst.connector_id,
        "environment": inst.environment.value,
        "base_url": inst.base_url,
        "status": inst.status.value
    }, indent=2)

@tool
def execute_connector_operation(
    operation_id: str,
    instance_id: str,
    parameters_json: str = "{}",
    idempotency_key: str = ""
) -> str:
    """Executes a typed operation on an external connector instance within safety boundaries."""
    import asyncio
    from connectors.service import connector_gateway
    from connectors.models import ConnectorRequest, RequestContext
    try:
        params = json.loads(parameters_json) if parameters_json else {}
    except Exception as e:
        return json.dumps({"error": f"Invalid parameters JSON: {e}"})

    ctx = RequestContext(
        purpose="tool_execution",
        idempotency_key=idempotency_key if idempotency_key else None
    )
    req = ConnectorRequest(
        operation_id=operation_id,
        instance_id=instance_id,
        context=ctx,
        parameters=params
    )

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                resp = pool.submit(asyncio.run, connector_gateway.execute(req)).result()
        else:
            resp = loop.run_until_complete(connector_gateway.execute(req))
    except RuntimeError:
        resp = asyncio.run(connector_gateway.execute(req))
    except Exception as exc:
        return json.dumps({"error": f"Execution failed: {exc}"})

    return json.dumps({
        "request_id": resp.request_id,
        "operation_id": resp.operation_id,
        "status_code": resp.status_code,
        "verification_status": resp.verification_status.value,
        "body": resp.body,
        "error_type": resp.error_type,
        "error_message": resp.error_message,
        "latency_ms": round(resp.latency_ms, 2),
        "cached_idempotent": resp.cached_idempotent
    }, indent=2)

@tool
def check_connector_health(instance_id: str) -> str:
    """Checks operational health of a connector instance."""
    import asyncio
    from connectors.service import connector_gateway
    try:
        h = asyncio.run(connector_gateway.check_health(instance_id))
        return json.dumps({"instance_id": instance_id, "health": h.value}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

@tool
def reset_connector_circuit(connector_id: str) -> str:
    """Resets the circuit breaker for a connector back to CLOSED."""
    from connectors.circuit_breaker import circuit_breaker_registry
    breaker = circuit_breaker_registry.get_breaker(connector_id)
    breaker.reset()
    return json.dumps({"success": True, "connector_id": connector_id, "state": breaker.state.value})

@tool
def process_inbound_webhook(endpoint_path: str, headers_json: str, body_text: str) -> str:
    """Processes an inbound webhook with signature verification and replay defense."""
    import asyncio
    from connectors.webhooks import webhook_gateway
    try:
        headers = json.loads(headers_json) if headers_json else {}
    except Exception as e:
        return json.dumps({"error": f"Invalid headers JSON: {e}"})

    raw_body = body_text.encode("utf-8") if isinstance(body_text, str) else b""
    ok, evt, reason = asyncio.run(webhook_gateway.process_webhook(endpoint_path, headers, raw_body))
    return json.dumps({
        "success": ok,
        "reason": reason,
        "event_id": evt.event_id if evt else None,
        "provider_id": evt.provider_id if evt else None,
        "normalized_type": evt.normalized_type if evt else None
    }, indent=2)

@tool
def get_connector_telemetry() -> str:
    """Returns gateway aggregate telemetry metrics."""
    from connectors.service import connector_gateway
    t = connector_gateway.telemetry
    return json.dumps({
        "request_count": t.request_count,
        "success_count": t.success_count,
        "failure_count": t.failure_count,
        "uncertain_count": t.uncertain_count,
        "retry_count": t.retry_count,
        "rate_limit_count": t.rate_limit_count,
        "circuit_open_count": t.circuit_open_count,
        "webhook_count": t.webhooks.persistence is not None
    }, indent=2)


# --- Module 27: Data Ingestion & Knowledge Pipeline Tools ---
@tool
def ingest_external_data(
    source_id: str,
    payload: str,
    data_category: str = "GENERIC",
    source_type: str = "api",
    external_record_id: str = "",
    trust_boundary: str = "UNTRUSTED",
    content_type: str = "application/json"
) -> str:
    """Ingests raw external data into Omnia's normalized knowledge pipeline."""
    from ingestion.service import ingestion_service
    from ingestion.models import DataCategory, TrustBoundary, ContentType
    try:
        parsed_payload = json.loads(payload) if (payload.startswith("{") or payload.startswith("[")) else payload
        cat = DataCategory[data_category.upper()] if data_category.upper() in DataCategory.__members__ else DataCategory.GENERIC
        tb = TrustBoundary[trust_boundary.upper()] if trust_boundary.upper() in TrustBoundary.__members__ else TrustBoundary.UNTRUSTED
        ct = ContentType.JSON if "json" in content_type else ContentType.TEXT

        envelope = ingestion_service.ingest_raw(
            source_id=source_id,
            source_type=source_type,
            raw_payload=parsed_payload,
            category=cat,
            trust_boundary=tb,
            content_type=ct,
            external_record_id=external_record_id or None
        )
        return json.dumps(envelope.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def process_ingestion_pipeline(envelope_id: str) -> str:
    """Executes normalization, validation, deduplication and enrichment on an ingested envelope."""
    from ingestion.service import ingestion_service
    try:
        record = ingestion_service.process_pipeline(envelope_id)
        if not record:
            return json.dumps({"success": False, "error": f"Failed to process envelope {envelope_id} or rejected."})
        return json.dumps(record.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def get_data_provenance(record_id: str) -> str:
    """Retrieves full lineage and cryptographic provenance record for a normalized record."""
    from ingestion.service import ingestion_service
    try:
        prov = ingestion_service.get_provenance(record_id)
        if not prov:
            return json.dumps({"success": False, "error": f"Provenance not found for record {record_id}."})
        return json.dumps(prov.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def list_data_conflicts(status: str = "OPEN") -> str:
    """Lists detected data conflicts across normalized ingestion records."""
    from ingestion.service import ingestion_service
    try:
        conflicts = ingestion_service.list_conflicts(status=status)
        return json.dumps([c.to_dict() for c in conflicts], indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def resolve_data_conflict(conflict_id: str, strategy: str = "AUTHORITATIVE_SOURCE_WINS", winning_value: str = "") -> str:
    """Resolves an open data conflict using an authoritative policy or manual override."""
    from ingestion.service import ingestion_service
    from ingestion.models import ConflictResolutionStrategy
    try:
        strat = ConflictResolutionStrategy[strategy.upper()] if strategy.upper() in ConflictResolutionStrategy.__members__ else ConflictResolutionStrategy.AUTHORITATIVE_SOURCE_WINS
        val = json.loads(winning_value) if winning_value.startswith("{") or winning_value.startswith("[") else (winning_value or None)
        resolved = ingestion_service.resolve_conflict(conflict_id, strategy=strat, winning_value=val)
        if not resolved:
            return json.dumps({"success": False, "error": f"Conflict {conflict_id} not found."})
        return json.dumps(resolved.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def get_ingestion_telemetry() -> str:
    """Returns ingestion pipeline telemetry, throughput, quarantine, and error rates."""
    from ingestion.service import data_ingestion_service
    try:
        telem = data_ingestion_service.get_telemetry()
        return json.dumps(telem.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


# --- Module 28: Unified Search & Retrieval Engine Tools ---
@tool
def execute_unified_search(
    query_text: str,
    search_mode: str = "HYBRID",
    max_results: int = 10,
    exclude_stale: bool = False
) -> str:
    """Executes fused hybrid search across Omnia's normalized records, vector memory, tasks, and configs."""
    from retrieval.service import unified_search_service
    from retrieval.models import SearchMode, SearchFilter
    try:
        mode_enum = SearchMode[search_mode.upper()] if search_mode.upper() in SearchMode.__members__ else SearchMode.HYBRID
        filters = SearchFilter(exclude_stale=exclude_stale)
        res = unified_search_service.search(
            query_text=query_text,
            mode=mode_enum,
            filters=filters,
            limit=max_results
        )
        return json.dumps(res.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def get_retrieval_evidence(query_id: str) -> str:
    """Retrieves all persisted evidence items and confidence scores associated with a query."""
    from retrieval.service import unified_search_service
    try:
        items = unified_search_service.get_evidence(query_id)
        return json.dumps([item.to_dict() for item in items], indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def get_retrieval_telemetry() -> str:
    """Returns real-time search throughput, cache hit ratios, and latency distributions."""
    from retrieval.service import unified_search_service
    try:
        telem = unified_search_service.get_telemetry()
        return json.dumps(telem.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


# --- Module 29: Evidence & Decision Engine Tools ---
@tool
def evaluate_evidence_claims(
    subject_id: str,
    decision_type: str,
    claims_json: str,
    min_confidence: float = 0.70
) -> str:
    """Evaluates propositions against retrieved evidence to reach an authoritative, evidence-backed decision."""
    from decision.service import evidence_decision_service
    from decision.models import DecisionPolicy
    try:
        claims = json.loads(claims_json) if isinstance(claims_json, str) else claims_json
        if not isinstance(claims, list):
            claims = [str(claims)]
        policy = DecisionPolicy(min_confidence_to_accept=min_confidence)
        dec = evidence_decision_service.evaluate(
            subject_id=subject_id,
            decision_type=decision_type,
            claims_text=claims,
            policy=policy
        )
        return json.dumps(dec.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def get_decision_record(decision_id: str) -> str:
    """Retrieves full details, evidence links, conflicts, and state for a decision record."""
    from decision.service import evidence_decision_service
    try:
        dec = evidence_decision_service.get_decision(decision_id)
        if not dec:
            return json.dumps({"success": False, "error": f"Decision {decision_id} not found."})
        return json.dumps(dec.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


# --- Module 30: Knowledge Graph & Entity Resolution Engine Tools ---
@tool
def create_knowledge_entity(
    canonical_name: str,
    entity_type: str = "CONCEPT",
    aliases_json: str = "[]",
    attributes_json: str = "{}",
    confidence: float = 1.0,
    identities_json: str = "[]"
) -> str:
    """Creates or updates a persistent entity with aliases, attributes, and identities in the knowledge graph."""
    from knowledge.service import knowledge_graph_service
    try:
        aliases = json.loads(aliases_json) if isinstance(aliases_json, str) else aliases_json
        attrs = json.loads(attributes_json) if isinstance(attributes_json, str) else attributes_json
        idents = json.loads(identities_json) if isinstance(identities_json, str) else identities_json
        ent = knowledge_graph_service.create_entity(
            canonical_name=canonical_name,
            entity_type=entity_type,
            aliases=aliases,
            attributes=attrs,
            confidence=confidence,
            identities=idents,
        )
        return json.dumps(ent.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def assert_knowledge_relationship(
    source_id: str,
    predicate: str,
    target_id: str,
    confidence: float = 1.0,
    weight: float = 1.0,
    properties_json: str = "{}"
) -> str:
    """Asserts a typed directed relationship between two existing knowledge entities."""
    from knowledge.service import knowledge_graph_service
    try:
        props = json.loads(properties_json) if isinstance(properties_json, str) else properties_json
        rel = knowledge_graph_service.assert_relationship(
            source_id=source_id,
            predicate=predicate,
            target_id=target_id,
            confidence=confidence,
            weight=weight,
            properties=props,
        )
        return json.dumps(rel.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def query_knowledge_graph(
    center_entity_id: str,
    max_depth: int = 2,
    min_confidence: float = 0.0
) -> str:
    """Extracts a bounded k-hop neighborhood subgraph around a center entity in the knowledge graph."""
    from knowledge.service import knowledge_graph_service
    try:
        subgraph = knowledge_graph_service.query_neighborhood(
            center_entity_id=center_entity_id,
            max_depth=max_depth,
            min_confidence=min_confidence,
        )
        return json.dumps(subgraph.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def resolve_entity_candidates(auto_merge_threshold: float = 0.85) -> str:
    """Scans and resolves pending entity resolution candidates using non-destructive identity merging."""
    from knowledge.service import knowledge_graph_service
    try:
        actions = knowledge_graph_service.resolve_candidates(auto_merge_threshold=auto_merge_threshold)
        return json.dumps({"success": True, "resolved_count": len(actions), "actions": actions}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


# --- Module 31: Temporal Knowledge & Causal State Engine Tools ---
@tool
def record_temporal_entity_state(
    entity_id: str,
    state_payload_json: str,
    valid_from: str = "",
    valid_until: str = ""
) -> str:
    """Records a bi-temporal state snapshot for an entity with valid time and transaction time."""
    from temporal.service import temporal_causal_service
    from datetime import datetime
    try:
        payload = json.loads(state_payload_json) if isinstance(state_payload_json, str) else state_payload_json
        v_from = datetime.fromisoformat(valid_from) if valid_from else None
        v_until = datetime.fromisoformat(valid_until) if valid_until else None
        record = temporal_causal_service.record_state(
            entity_id=entity_id,
            state_payload=payload,
            valid_from=v_from,
            valid_until=v_until,
        )
        return json.dumps(record.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def reconstruct_temporal_state(
    entity_id: str,
    valid_time: str,
    transaction_time: str = ""
) -> str:
    """Reconstructs what was true for an entity at a specific point in time (as_of bi-temporal query)."""
    from temporal.service import temporal_causal_service
    from datetime import datetime
    try:
        vt = datetime.fromisoformat(valid_time)
        tt = datetime.fromisoformat(transaction_time) if transaction_time else None
        record = temporal_causal_service.reconstruct_state(
            entity_id=entity_id,
            valid_time=vt,
            transaction_time=tt,
        )
        if not record:
            return json.dumps({"found": False, "entity_id": entity_id, "state": None}, indent=2)
        return json.dumps({"found": True, "record": record.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def assert_causal_link(
    cause_entity_id: str,
    effect_entity_id: str,
    relation_type: str = "RESULTED_IN",
    confidence: float = 1.0,
    evidence_ids_json: str = "[]",
    mechanism_description: str = ""
) -> str:
    """Asserts a typed causal relationship between two entities or events backed by evidence."""
    from temporal.service import temporal_causal_service
    try:
        ev_ids = json.loads(evidence_ids_json) if isinstance(evidence_ids_json, str) else evidence_ids_json
        link = temporal_causal_service.assert_causal_link(
            cause_entity_id=cause_entity_id,
            effect_entity_id=effect_entity_id,
            relation_type=relation_type,
            confidence=confidence,
            evidence_ids=ev_ids,
            mechanism_description=mechanism_description or None,
        )
        return json.dumps(link.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def trace_causal_chain(
    entity_id: str,
    direction: str = "ROOT_CAUSE",
    max_depth: int = 5
) -> str:
    """Traces a causal graph either backward for root cause analysis or forward for consequence blast radius."""
    from temporal.service import temporal_causal_service
    try:
        chain = temporal_causal_service.trace_causal_chain(
            entity_id=entity_id,
            direction=direction,
            max_depth=max_depth,
        )
        return json.dumps(chain.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)



# --- Module 32: Predictive Intelligence & Risk Forecasting Engine Tools ---
@tool
def request_forecast(
    target_id: str,
    target_type: str = "TIME_SERIES",
    target_description: str = "",
    duration_sec: float = 3600.0,
    method_name: str = "",
    inputs_json: str = "[]",
    parameters_json: str = "{}"
) -> str:
    """Generates an evidence-backed baseline forecast with explicit uncertainty and intervals."""
    from prediction.service import predictive_service
    from prediction.models import ForecastRequest, ForecastTarget, ForecastHorizon, ForecastInput, ForecastType
    try:
        t_type = ForecastType(target_type.upper()) if target_type.upper() in ForecastType.__members__ else ForecastType.TIME_SERIES
        params = json.loads(parameters_json) if isinstance(parameters_json, str) else parameters_json
        raw_inputs = json.loads(inputs_json) if isinstance(inputs_json, str) else inputs_json

        parsed_inputs = []
        for item in raw_inputs:
            if isinstance(item, dict):
                parsed_inputs.append(ForecastInput(
                    input_id=item.get("input_id", f"inp_{uuid.uuid4().hex[:6]}"),
                    timestamp=float(item.get("timestamp", time.time())),
                    value=item.get("value"),
                    source=item.get("source", "tool_input"),
                    metadata=item.get("metadata", {})
                ))

        now = time.time()
        req = ForecastRequest(
            request_id=f"req-{uuid.uuid4().hex[:8]}",
            target=ForecastTarget(
                target_id=target_id,
                target_description=target_description or f"Forecast for {target_id}",
                target_type=t_type,
                observation_unit="units",
                outcome_definition="Observed historical metric or state",
            ),
            horizon=ForecastHorizon.from_duration(duration_sec, now),
            parameters=params,
            as_of_time=now,
        )

        fc = predictive_service.generate_forecast(
            request=req,
            inputs=parsed_inputs,
            method_name=method_name or None
        )
        return json.dumps(fc.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def assess_target_risk(
    target_id: str,
    critical_threshold: float = 80.0,
    impact_score: float = 3.0,
    horizon_sec: float = 3600.0,
    inputs_json: str = "[]"
) -> str:
    """Evaluates emerging risks by separating likelihood from impact with attributable risk factors."""
    from prediction.service import predictive_service
    from prediction.models import ForecastInput
    try:
        raw_inputs = json.loads(inputs_json) if isinstance(inputs_json, str) else inputs_json
        parsed_inputs = []
        for item in raw_inputs:
            if isinstance(item, dict):
                parsed_inputs.append(ForecastInput(
                    input_id=item.get("input_id", f"inp_{uuid.uuid4().hex[:6]}"),
                    timestamp=float(item.get("timestamp", time.time())),
                    value=item.get("value"),
                    source=item.get("source", "tool_input"),
                ))
        assessment = predictive_service.assess_risk(
            target_id=target_id,
            inputs=parsed_inputs,
            critical_threshold=critical_threshold,
            impact_score=impact_score,
            horizon_sec=horizon_sec,
        )
        return json.dumps(assessment.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def compare_forecast_scenarios(
    target_id: str,
    target_type: str = "TIME_SERIES",
    scenarios_json: str = "[]",
    duration_sec: float = 3600.0,
    method_name: str = "",
    inputs_json: str = "[]"
) -> str:
    """Compares explicit hypothetical what-if scenarios without asserting causal certainty."""
    from prediction.service import predictive_service
    from prediction.models import ForecastRequest, ForecastTarget, ForecastHorizon, ForecastInput, ForecastScenario, ForecastAssumption, ForecastType
    try:
        t_type = ForecastType(target_type.upper()) if target_type.upper() in ForecastType.__members__ else ForecastType.TIME_SERIES
        raw_inputs = json.loads(inputs_json) if isinstance(inputs_json, str) else inputs_json
        parsed_inputs = [
            ForecastInput(
                input_id=item.get("input_id", f"inp_{uuid.uuid4().hex[:6]}"),
                timestamp=float(item.get("timestamp", time.time())),
                value=item.get("value"),
                source=item.get("source", "tool_input")
            )
            for item in raw_inputs if isinstance(item, dict)
        ]

        raw_scenarios = json.loads(scenarios_json) if isinstance(scenarios_json, str) else scenarios_json
        scenarios = []
        for s in raw_scenarios:
            if isinstance(s, dict):
                assumptions = [
                    ForecastAssumption(
                        assumption_id=a.get("assumption_id", f"asm_{uuid.uuid4().hex[:4]}"),
                        description=a.get("description", "")
                    )
                    for a in s.get("assumptions", []) if isinstance(a, dict)
                ]
                scenarios.append(ForecastScenario(
                    scenario_id=s.get("scenario_id", f"scn_{uuid.uuid4().hex[:6]}"),
                    name=s.get("name", "Hypothetical Scenario"),
                    description=s.get("description", ""),
                    modified_variables=s.get("modified_variables", {}),
                    assumptions=assumptions,
                    is_hypothetical=True
                ))

        now = time.time()
        req = ForecastRequest(
            request_id=f"req-scn-{uuid.uuid4().hex[:8]}",
            target=ForecastTarget(
                target_id=target_id,
                target_description=f"Scenario comparison for {target_id}",
                target_type=t_type,
                observation_unit="units",
                outcome_definition="Scenario outcome",
            ),
            horizon=ForecastHorizon.from_duration(duration_sec, now),
            as_of_time=now,
        )

        res = predictive_service.compare_scenarios(
            base_request=req,
            scenarios=scenarios,
            inputs=parsed_inputs,
            method_name=method_name or None,
        )
        return json.dumps(res.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def record_forecast_outcome(
    forecast_id: str,
    observed_value: float = None,
    observed_class: str = "",
    source: str = "system",
    notes: str = ""
) -> str:
    """Records ground-truth outcome observation after forecast horizon elapses."""
    from prediction.service import predictive_service
    try:
        obs_val = float(observed_value) if observed_value is not None else None
        obs_cls = observed_class if observed_class else None
        outcome = predictive_service.record_outcome(
            forecast_id=forecast_id,
            observed_value=obs_val,
            observed_class=obs_cls,
            source=source,
            notes=notes or None,
        )
        return json.dumps(outcome.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def evaluate_forecast_accuracy(
    forecast_id: str,
    outcome_id: str = ""
) -> str:
    """Evaluates forecast accuracy against its recorded outcome without mutating the original forecast."""
    from prediction.service import predictive_service
    try:
        ev = predictive_service.evaluate_forecast(
            forecast_id=forecast_id,
            outcome_id=outcome_id or None,
        )
        if not ev:
            return json.dumps({"success": False, "error": f"No outcome found for forecast {forecast_id}."}, indent=2)
        return json.dumps(ev.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def check_model_drift(
    model_name: str,
    target_id: str,
    baseline_error: float = None
) -> str:
    """Assesses whether recent prediction errors indicate concept or model performance drift."""
    from prediction.service import predictive_service
    try:
        base_err = float(baseline_error) if baseline_error is not None else None
        assessment = predictive_service.detect_drift(
            model_name=model_name,
            target_id=target_id,
            baseline_error=base_err,
        )
        return json.dumps(assessment.to_dict(), indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

# --- Module 33: Adaptive Learning & Model Lifecycle Governance Tools ---
@tool
def record_learning_signal(
    signal_id: str,
    source_subsystem: str,
    signal_type: str,
    strategy_id: str,
    metric_name: str,
    metric_value: float,
    payload: Dict[str, Any],
    model_version_id: str = None,
    task_id: str = None,
    execution_id: str = None,
) -> str:
    """Records an empirical learning signal from task completions, forecasts, or user feedback."""
    from learning.service import adaptive_learning_service
    from learning.models import SignalType
    try:
        sig_type = SignalType(signal_type)
        val = float(metric_value)
        success, signal, msg = adaptive_learning_service.record_signal(
            signal_id=signal_id,
            source_subsystem=source_subsystem,
            signal_type=sig_type,
            strategy_id=strategy_id,
            metric_name=metric_name,
            metric_value=val,
            payload=payload,
            model_version_id=model_version_id or None,
            task_id=task_id or None,
            execution_id=execution_id or None,
        )
        return json.dumps({
            "success": success,
            "message": msg,
            "signal": signal.to_dict() if signal else None,
        }, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def build_learning_dataset(
    dataset_id: str,
    name: str,
    version: str,
    purpose: str,
    strategy_id: str = None,
    train_val_split_ratio: float = 0.8,
) -> str:
    """Builds a deterministic, reproducible dataset with anti-leakage temporal split from verified signals."""
    from learning.service import adaptive_learning_service
    from learning.models import DatasetPurpose
    try:
        purp = DatasetPurpose(purpose)
        ds = adaptive_learning_service.create_dataset(
            dataset_id=dataset_id,
            name=name,
            version=version,
            purpose=purp,
            strategy_id=strategy_id or None,
            train_val_split_ratio=float(train_val_split_ratio),
        )
        return json.dumps({
            "success": True,
            "dataset": ds.to_dict(),
        }, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def create_learning_experiment(
    experiment_id: str,
    name: str,
    experiment_type: str,
    baseline_version_id: str,
    candidate_version_id: str,
    primary_metric: str,
    traffic_allocation: float = 0.1,
    min_sample_size: int = 50,
) -> str:
    """Launches an offline benchmark, shadow, A/B test, or replay experiment between model/strategy versions."""
    from learning.service import adaptive_learning_service
    from learning.models import ExperimentType
    try:
        exp_type = ExperimentType(experiment_type)
        exp = adaptive_learning_service.create_experiment(
            experiment_id=experiment_id,
            name=name,
            experiment_type=exp_type,
            baseline_version_id=baseline_version_id,
            candidate_version_id=candidate_version_id,
            primary_metric=primary_metric,
            traffic_allocation=float(traffic_allocation),
            min_sample_size=int(min_sample_size),
        )
        return json.dumps({
            "success": True,
            "experiment": exp.to_dict(),
        }, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def evaluate_candidate_promotion(
    request_id: str,
    candidate_version_id: str,
    baseline_version_id: str,
    target_subsystem: str,
    justification: str,
    evaluation_metrics: Dict[str, float],
    baseline_metrics: Dict[str, float],
    regression_test_results: Dict[str, bool],
    policy_validation_passed: bool = True,
    security_audit_passed: bool = True,
    rollback_target_verified: bool = True,
    human_approval_signature: str = None,
) -> str:
    """Evaluates candidate model/strategy against non-bypassable promotion gates."""
    from learning.service import adaptive_learning_service
    try:
        req = adaptive_learning_service.evaluate_and_request_promotion(
            request_id=request_id,
            candidate_version_id=candidate_version_id,
            baseline_version_id=baseline_version_id,
            target_subsystem=target_subsystem,
            justification=justification,
            evaluation_metrics=evaluation_metrics,
            baseline_metrics=baseline_metrics,
            regression_test_results=regression_test_results,
            policy_validation_passed=bool(policy_validation_passed),
            security_audit_passed=bool(security_audit_passed),
            rollback_target_verified=bool(rollback_target_verified),
            human_approval_signature=human_approval_signature or None,
        )
        return json.dumps({
            "success": req.is_approved,
            "gates_passed": req.gates_passed,
            "promotion_request": req.to_dict(),
        }, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def execute_controlled_rollout(
    rollout_id: str,
    candidate_version_id: str,
    baseline_version_id: str,
    target_subsystem: str,
    initial_traffic_percent: float = 0.05,
) -> str:
    """Initiates a controlled staged canary deployment for an approved model or strategy version."""
    from learning.service import adaptive_learning_service
    try:
        rec = adaptive_learning_service.initiate_rollout(
            rollout_id=rollout_id,
            candidate_version_id=candidate_version_id,
            baseline_version_id=baseline_version_id,
            target_subsystem=target_subsystem,
            initial_traffic_percent=float(initial_traffic_percent),
        )
        return json.dumps({
            "success": True,
            "rollout": rec.to_dict(),
        }, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def execute_controlled_rollback(
    rollout_id: str,
    reason: str,
) -> str:
    """Immediately rolls back active traffic from a degraded candidate back to the stable baseline."""
    from learning.service import adaptive_learning_service
    try:
        success, msg = adaptive_learning_service.rollback_rollout(
            rollout_id=rollout_id,
            reason=reason,
        )
        return json.dumps({
            "success": success,
            "message": msg,
        }, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def assess_learning_drift(
    subsystem: str,
    metric_or_feature: str,
    drift_type: str,
    baseline_value_or_distribution: Any,
    current_value_or_distribution: Any,
    sample_size: int = 100,
) -> str:
    """Assesses feature drift or performance degradation across learning subsystems."""
    from learning.service import adaptive_learning_service
    try:
        if str(drift_type).lower() in ("feature", "feature_drift", "input"):
            rec = adaptive_learning_service.assess_feature_drift(
                subsystem=subsystem,
                feature_name=metric_or_feature,
                baseline_distribution=[float(x) for x in baseline_value_or_distribution],
                current_distribution=[float(x) for x in current_value_or_distribution],
            )
        else:
            rec = adaptive_learning_service.assess_performance_drift(
                subsystem=subsystem,
                metric_name=metric_or_feature,
                baseline_value=float(baseline_value_or_distribution),
                current_value=float(current_value_or_distribution),
                sample_size=int(sample_size),
            )
        return json.dumps({
            "success": True,
            "drift_record": rec.to_dict(),
        }, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

# --- Module 34: Autonomous Simulation, Digital Twin & Scenario Testing Tools ---
@tool
def create_simulation_environment(
    environment_id: str,
    name: str,
    env_type: str = "WORKFLOW",
    classification: str = "TEST",
) -> str:
    """Registers an isolated simulation sandbox environment."""
    from simulation.service import simulation_service
    from simulation.models import EnvironmentType, EnvironmentClassification
    try:
        e_type = EnvironmentType(env_type)
        e_class = EnvironmentClassification(classification)
        env = simulation_service.create_environment(
            environment_id=environment_id,
            name=name,
            env_type=e_type,
            classification=e_class,
        )
        return json.dumps({"success": True, "environment": env.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def register_digital_twin(
    twin_id: str,
    source_system_id: str,
    source_system_type: str,
    initial_observed_state: Dict[str, Any] = None,
    sync_mode: str = "STATIC",
) -> str:
    """Registers a versioned digital twin representation of a physical or logical system."""
    from simulation.service import simulation_service
    from simulation.models import TwinSyncMode
    try:
        s_mode = TwinSyncMode(sync_mode)
        twin = simulation_service.register_digital_twin(
            twin_id=twin_id,
            source_system_id=source_system_id,
            source_system_type=source_system_type,
            initial_observed_state=initial_observed_state or {},
            sync_mode=s_mode,
        )
        return json.dumps({"success": True, "twin": twin.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def capture_state_snapshot(
    snapshot_id: str,
    environment_id: str,
    raw_state: Dict[str, Any],
) -> str:
    """Captures an immutable, sanitized initial state snapshot with cryptographic integrity digest."""
    from simulation.service import simulation_service
    try:
        snap = simulation_service.capture_snapshot(
            snapshot_id=snapshot_id,
            environment_id=environment_id,
            raw_state=raw_state,
        )
        return json.dumps({"success": True, "snapshot": snap.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def register_simulation_scenario(
    scenario_id: str,
    name: str,
    scenario_type: str,
    environment_id: str,
    initial_snapshot_id: str,
    proposed_actions: List[Dict[str, Any]],
    preconditions: Dict[str, Any] = None,
    time_horizon_seconds: float = 60.0,
) -> str:
    """Compiles and registers an executable simulation scenario with precondition checks."""
    from simulation.service import simulation_service
    from simulation.models import ScenarioType
    try:
        scen_type = ScenarioType(scenario_type)
        scen = simulation_service.register_scenario(
            scenario_id=scenario_id,
            name=name,
            scenario_type=scen_type,
            environment_id=environment_id,
            initial_snapshot_id=initial_snapshot_id,
            proposed_actions=proposed_actions,
            preconditions=preconditions or {},
            time_horizon_seconds=float(time_horizon_seconds),
        )
        return json.dumps({"success": True, "scenario": scen.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def execute_simulation(
    simulation_id: str,
    scenario_id: str,
    twin_id: str = None,
) -> str:
    """Executes deterministic simulation on isolated state strictly without touching production."""
    from simulation.service import simulation_service
    try:
        rec = simulation_service.run_simulation(
            simulation_id=simulation_id,
            scenario_id=scenario_id,
            twin_id=twin_id or None,
        )
        return json.dumps({"success": True, "execution": rec.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def explore_simulation_alternatives(
    initial_state: Dict[str, Any],
    candidate_action_sequences: List[List[Dict[str, Any]]],
    strategy: str = "RELIABILITY_OPTIMIZED",
) -> str:
    """Explores alternative execution branches within bounded resource limits."""
    from simulation.service import simulation_service
    from simulation.models import AlternativeSearchStrategy
    try:
        strat = AlternativeSearchStrategy(strategy)
        res = simulation_service.explore_alternatives(
            initial_state=initial_state,
            candidate_action_sequences=candidate_action_sequences,
            strategy=strat,
        )
        return json.dumps({"success": True, "exploration": res}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def inject_simulation_fault(
    fault_id: str,
    simulation_id: str,
    fault_type: str,
    target_component: str,
    activation_step: int = 1,
    duration_steps: int = 1,
) -> str:
    """Injects synthetic node crashes, network partitions, or timeouts inside isolated simulation."""
    from simulation.service import simulation_service
    from simulation.models import FaultType
    try:
        f_type = FaultType(fault_type)
        fault = simulation_service.inject_fault(
            fault_id=fault_id,
            simulation_id=simulation_id,
            fault_type=f_type,
            target_component=target_component,
            activation_step=int(activation_step),
            duration_steps=int(duration_steps),
        )
        return json.dumps({"success": True, "fault": fault.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)





# --- Module 35: Autonomous Cybersecurity, Threat Intelligence & Runtime Defense Tools ---
@tool
def ingest_security_telemetry(
    source_component: str,
    action_category: str,
    outcome: str,
    severity: str = "INFO",
    source_identity: str = "",
    node_identity: str = "",
    resource_reference: str = "",
    details: str = "{}"
) -> str:
    """Ingests, normalizes, and correlates runtime security telemetry with zero-leakage redaction."""
    from defense.service import cyber_defense_service
    from defense.models import SecuritySeverity
    import json
    try:
        sev = SecuritySeverity(severity.upper())
        dt = json.loads(details) if isinstance(details, str) else details
        evt, alerts, incs = cyber_defense_service.ingest_security_event(
            raw_event=dt,
            source_component=source_component,
            action_category=action_category,
            outcome=outcome,
            severity=sev,
            source_identity=source_identity or None,
            node_identity=node_identity or None,
            resource_reference=resource_reference or None,
        )
        return json.dumps({
            "success": True,
            "event_id": evt.event_id,
            "alerts_generated": [a.to_dict() for a in alerts],
            "incidents_created": [i.to_dict() for i in incs],
        }, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def register_threat_intelligence_indicator(
    indicator_id: str,
    indicator_type: str,
    indicator_value: str,
    source: str = "cisa_known_exploited",
    confidence: float = 0.85,
    threat_classification: str = "ANOMALOUS_BEHAVIOR"
) -> str:
    """Registers and validates a defensive threat intelligence indicator with anti-poisoning checks."""
    from defense.service import cyber_defense_service
    from defense.models import IndicatorType, ThreatClassification
    import json
    try:
        itype = IndicatorType(indicator_type.upper())
        tclass = ThreatClassification(threat_classification.upper())
        ind = cyber_defense_service.register_threat_indicator(
            indicator_id=indicator_id,
            indicator_type=itype,
            indicator_value=indicator_value,
            source=source,
            confidence=float(confidence),
            threat_classification=tclass,
        )
        return json.dumps({"success": True, "indicator": ind.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def assess_security_posture() -> str:
    """Evaluates comprehensive system defensive posture, active incidents, and telemetry coverage."""
    from defense.service import cyber_defense_service
    import json
    try:
        assessment = cyber_defense_service.assess_security_posture()
        return json.dumps({"success": True, "assessment": assessment.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def request_defensive_containment(
    incident_id: str,
    action_type: str,
    target_resource: str,
    scope: str = "LOCAL",
    reason: str = "Automated threat response",
    is_reversible: bool = True
) -> str:
    """Plans a narrowly scoped defensive containment action adhering to response autonomy levels."""
    from defense.service import cyber_defense_service
    import json
    try:
        action = cyber_defense_service.request_containment(
            incident_id=incident_id,
            action_type=action_type,
            target_resource=target_resource,
            scope=scope,
            reason=reason,
            is_reversible=bool(is_reversible),
        )
        return json.dumps({"success": True, "containment_action": action.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def authorize_and_execute_containment(
    action_id: str,
    approval_token: str
) -> str:
    """Binds an authorized approval token and executes verified defensive containment."""
    from defense.service import cyber_defense_service
    import json
    try:
        ok, evidence = cyber_defense_service.authorize_and_execute_containment(action_id, approval_token)
        return json.dumps({"success": ok, "verification_evidence": evidence}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def preserve_incident_forensics(
    incident_id: str,
    artifact_type: str,
    source_identifier: str,
    raw_payload_json: str
) -> str:
    """Preserves immutable forensic evidence with SHA-256 integrity digest and chain-of-custody."""
    from defense.service import cyber_defense_service
    import json
    try:
        payload = json.loads(raw_payload_json) if isinstance(raw_payload_json, str) else raw_payload_json
        evid = cyber_defense_service.forensics_manager.preserve_evidence(
            incident_id=incident_id,
            artifact_type=artifact_type,
            source_identifier=source_identifier,
            raw_payload=payload,
        )
        cyber_defense_service.repo.save_evidence_record(evid)
        return json.dumps({"success": True, "evidence": evid.to_dict()}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)

@tool
def resolve_security_incident(
    incident_id: str,
    actor: str,
    resolution_summary: str
) -> str:
    """Safely transitions an incident through verified recovery to RESOLVED status."""
    from defense.service import cyber_defense_service
    import json
    try:
        ok = cyber_defense_service.resolve_incident(
            incident_id=incident_id,
            actor=actor,
            resolution_summary=resolution_summary,
        )
        return json.dumps({"success": ok, "incident_id": incident_id, "resolved": ok}, indent=2)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


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
    get_coordination_status,
    list_cluster_members,
    claim_task_ownership,
    start_cluster_election,
    get_replication_status,
    list_replication_namespaces,
    trigger_state_reconciliation,
    get_config_status,
    get_config_value,
    propose_config_change,
    rollout_config_version,
    rollback_config_version,
    detect_config_drift,
    diff_config_versions,
    get_secret_metadata,
    acquire_secret_lease,
    release_secret_lease,
    rotate_secret,
    revoke_secret,
    mark_secret_compromised,
    get_secrets_telemetry,
    redact_sensitive_text,
    list_external_connectors,
    get_connector_definition,
    create_connector_instance,
    execute_connector_operation,
    check_connector_health,
    reset_connector_circuit,
    process_inbound_webhook,
    get_connector_telemetry,
    get_video_studio_status,
    list_video_studio_capabilities,
    check_video_studio_capability,
    import_media_asset,
    get_media_asset,
    list_media_assets,
    create_media_bin,
    search_media_assets,
    analyze_media_asset,
    get_asset_thumbnail,
    get_asset_waveform,
    generate_contact_sheet,
    create_video_sequence,
    get_video_sequence,
    add_timeline_clip,
    add_timeline_marker,
    query_timeline_items,
    trim_timeline_item,
    split_timeline_clip,
    move_timeline_clip,
    set_timeline_clip_enabled,
    link_timeline_items,
    undo_timeline_edit,
    redo_timeline_edit,
    ripple_trim_timeline_item,
    rolling_edit_timeline,
    slip_edit_timeline_clip,
    slide_edit_timeline_clip,
    ripple_delete_timeline_clips,
    manage_timeline_gaps,
    create_playback_session,
    control_playback_session,
    get_playback_metrics,
    add_property_keyframe,
    evaluate_animated_property,
    query_property_keyframes,
    render_timeline_audio_slice,
    configure_audio_bus,
    get_audio_meters,
    list_audio_devices,
    add_video_effect,
    configure_clip_compositing,
    list_available_video_effects,
    add_video_transition,
    validate_transition_handles,
    list_transition_presets,
    create_subtitle_track,
    add_subtitle_cue_item,
    import_subtitle_file,
    export_subtitle_file,
    search_transcript_text,
    create_graphics_composition,
    add_graphics_layer,
    instantiate_graphics_template,
    list_graphics_templates,
    apply_clip_speed_remap,
    apply_clip_color_grade,
    export_video_sequence,
    apply_cinematic_look,
    add_clip_freeze_frame,
    ingest_external_data,
    process_ingestion_pipeline,
    get_data_provenance,
    list_data_conflicts,
    resolve_data_conflict,
    get_ingestion_telemetry,
    execute_unified_search,
    get_retrieval_evidence,
    get_retrieval_telemetry,
    evaluate_evidence_claims,
    get_decision_record,
    create_knowledge_entity,
    assert_knowledge_relationship,
    query_knowledge_graph,
    resolve_entity_candidates,
    record_temporal_entity_state,
    reconstruct_temporal_state,
    assert_causal_link,
    trace_causal_chain,
    request_forecast,
    assess_target_risk,
    compare_forecast_scenarios,
    record_forecast_outcome,
    evaluate_forecast_accuracy,
    check_model_drift,
    record_learning_signal,
    build_learning_dataset,
    create_learning_experiment,
    evaluate_candidate_promotion,
    execute_controlled_rollout,
    execute_controlled_rollback,
    assess_learning_drift,
    create_simulation_environment,
    register_digital_twin,
    capture_state_snapshot,
    register_simulation_scenario,
    execute_simulation,
    explore_simulation_alternatives,
    inject_simulation_fault,
    ingest_security_telemetry,
    register_threat_intelligence_indicator,
    assess_security_posture,
    request_defensive_containment,
    authorize_and_execute_containment,
    preserve_incident_forensics,
    resolve_security_incident,
]

# Backward compatibility alias
OMNIA_HARDWARE_TOOLS = OMNIA_ALL_TOOLS

if __name__ == "__main__":
    print(f"Omnia Tools registered successfully: {[t.__name__ for t in OMNIA_ALL_TOOLS]}")



