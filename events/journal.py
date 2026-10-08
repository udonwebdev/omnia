import time
import json
import logging
from typing import List, Optional, Dict, Any

from events.models import Event, EventEnvelope, EventPriority, EventSeverity, EventDurability
from persistence.store import persistence_store

logger = logging.getLogger("Omnia.Events.Journal")

class EventJournal:
    """Manages ordered durable recording and safe read-only event replay."""

    def __init__(self, store=persistence_store):
        self.store = store

    def record_durable_event(self, event: Event) -> int:
        """Persists a durable event into the persistent task journal."""
        task_id = event.task_id or event.correlation_id or "global"
        payload_record = {
            "event_id": event.id,
            "correlation_id": event.correlation_id,
            "source": event.envelope.source,
            "severity": event.severity.value,
            "priority": event.priority.name,
            "payload": event.payload,
            "metadata": event.metadata
        }
        seq = self.store.append_event(
            task_id=task_id,
            event_type=event.type,
            payload=payload_record
        )
        return seq

    def get_trace(self, correlation_id: str) -> List[Dict[str, Any]]:
        """Retrieves ordered events matching a specific correlation or task ID."""
        events = self.store.get_task_events(correlation_id)
        trace = []
        for e in events:
            trace.append({
                "sequence": e.sequence_number,
                "event_id": e.event_id,
                "timestamp": e.timestamp,
                "event_type": e.event_type,
                "payload": e.payload
            })
        return trace

    def replay_trace(self, correlation_id: str) -> List[str]:
        """Performs a safe, read-only analytical reconstruction of an event sequence.
        CRITICAL: Never executes side effects or commands during replay.
        """
        trace = self.get_trace(correlation_id)
        summary_log = []
        for item in trace:
            summary_log.append(f"[{item['sequence']}] {item['event_type']} @ {time.strftime('%H:%M:%S', time.localtime(item['timestamp']))}")
        return summary_log

event_journal = EventJournal()
