import time
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

from supervisor.models import StallClassification

logger = logging.getLogger("Omnia.Supervisor.Heartbeat")

@dataclass
class HeartbeatRecord:
    mission_id: str
    task_id: Optional[str] = None
    last_heartbeat_ts: float = field(default_factory=time.time)
    last_progress_ts: float = field(default_factory=time.time)
    last_state_change_ts: float = field(default_factory=time.time)
    current_node_id: Optional[str] = None
    current_activity: str = "INITIALIZING"
    recent_progress_signals: deque = field(default_factory=lambda: deque(maxlen=20))
    recent_observations: deque = field(default_factory=lambda: deque(maxlen=10))
    recent_nodes: deque = field(default_factory=lambda: deque(maxlen=10))

class HeartbeatMonitor:
    """Monitors mission and task heartbeats, detecting stalls, deadlocks, and execution loops."""

    def __init__(self):
        self._records: Dict[str, HeartbeatRecord] = {}

    def register_mission(self, mission_id: str, task_id: Optional[str] = None):
        """Initializes heartbeat monitoring for a mission."""
        now = time.time()
        self._records[mission_id] = HeartbeatRecord(
            mission_id=mission_id,
            task_id=task_id,
            last_heartbeat_ts=now,
            last_progress_ts=now,
            last_state_change_ts=now
        )

    def record_heartbeat(self, mission_id: str, activity: str = "", current_node_id: Optional[str] = None):
        """Records a process liveness tick."""
        now = time.time()
        rec = self._records.get(mission_id)
        if not rec:
            self.register_mission(mission_id)
            rec = self._records[mission_id]

        rec.last_heartbeat_ts = now
        if activity:
            rec.current_activity = activity
        if current_node_id:
            rec.current_node_id = current_node_id
            rec.recent_nodes.append(current_node_id)

    def record_progress(self, mission_id: str, signal_name: str, details: Optional[Dict[str, Any]] = None):
        """Records a verified meaningful progress event (e.g. node completed, verified state change)."""
        now = time.time()
        rec = self._records.get(mission_id)
        if not rec:
            self.register_mission(mission_id)
            rec = self._records[mission_id]

        rec.last_progress_ts = now
        rec.recent_progress_signals.append((now, signal_name, details or {}))
        logger.debug(f"Progress recorded for mission '{mission_id}': {signal_name}")

    def record_observation(self, mission_id: str, observation_hash: str):
        """Records an observation identifier for loop and oscillation detection."""
        rec = self._records.get(mission_id)
        if rec:
            rec.recent_observations.append(observation_hash)

    def check_loop_or_oscillation(self, mission_id: str) -> Tuple[bool, str]:
        """Detects repeated identical observations or oscillating node transitions (A -> B -> A -> B)."""
        rec = self._records.get(mission_id)
        if not rec:
            return False, ""

        # 1. Repeated Identical Observations (e.g. stuck on same visual screen 4 times)
        if len(rec.recent_observations) >= 4:
            last_4 = list(rec.recent_observations)[-4:]
            if len(set(last_4)) == 1:
                return True, f"Identical observation repeated {len(last_4)} times consecutively: {last_4[0]}"

        # 2. Oscillating node transitions (A -> B -> A -> B)
        if len(rec.recent_nodes) >= 4:
            nodes = list(rec.recent_nodes)[-4:]
            if nodes[0] == nodes[2] and nodes[1] == nodes[3] and nodes[0] != nodes[1]:
                return True, f"Oscillating node execution loop detected: {nodes[0]} <-> {nodes[1]}"

        return False, ""

    def assess_stall(
        self,
        mission_id: str,
        expected_interval_sec: float = 30.0,
        warning_threshold_sec: float = 60.0,
        hard_timeout_sec: float = 180.0
    ) -> Tuple[StallClassification, str, float]:
        """Classifies the liveness and progress state of a mission.
        
        Returns:
            (classification, reason, time_since_last_progress_sec)
        """
        rec = self._records.get(mission_id)
        if not rec:
            return StallClassification.ALIVE, "No heartbeat record yet", 0.0

        now = time.time()
        time_since_hb = now - rec.last_heartbeat_ts
        time_since_progress = now - rec.last_progress_ts

        # Check for loop/oscillation first
        is_loop, loop_reason = self.check_loop_or_oscillation(mission_id)
        if is_loop:
            return StallClassification.LOOP, loop_reason, time_since_progress

        # Check heartbeat liveness (heartbeat timeout: 30s)
        if time_since_hb > 30.0:
            return StallClassification.STALLED, f"Heartbeat missed for {time_since_hb:.1f}s (process unresponsive)", time_since_progress

        # Heartbeat is alive. Now assess meaningful progress:
        if time_since_progress > hard_timeout_sec:
            return StallClassification.NO_PROGRESS, f"Hard timeout exceeded: No progress for {time_since_progress:.1f}s (limit {hard_timeout_sec}s)", time_since_progress

        if time_since_progress > warning_threshold_sec:
            return StallClassification.STALLED, f"Stall warning: No meaningful progress for {time_since_progress:.1f}s (threshold {warning_threshold_sec}s)", time_since_progress

        if time_since_progress > expected_interval_sec:
            return StallClassification.DEGRADED, f"Progress delayed: {time_since_progress:.1f}s since last event", time_since_progress

        return StallClassification.ACTIVE, "Mission is actively progressing", time_since_progress

    def cleanup(self, mission_id: str):
        """Removes tracking record when mission reaches terminal state."""
        self._records.pop(mission_id, None)

heartbeat_monitor = HeartbeatMonitor()
