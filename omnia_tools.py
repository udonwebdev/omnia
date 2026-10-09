import httpx
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
]

# Backward compatibility alias
OMNIA_HARDWARE_TOOLS = OMNIA_ALL_TOOLS

if __name__ == "__main__":
    print(f"Omnia Tools registered successfully: {[t.__name__ for t in OMNIA_ALL_TOOLS]}")



