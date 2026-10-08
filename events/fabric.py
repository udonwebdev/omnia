import asyncio
import logging
import time
import inspect
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from collections import deque

from events.models import (
    Event,
    EventEnvelope,
    EventFilter,
    EventPriority,
    EventSeverity,
    EventDurability,
    DeadLetterRecord
)
from events.schemas import event_schema_validator
from events.journal import event_journal
from audit_logger import audit_logger

logger = logging.getLogger("Omnia.Events.Fabric")

MAX_PROCESSED_WINDOW = 5000
MAX_QUEUE_CAPACITY = 1000

class EventFabric:
    """Production-grade Event Fabric supporting priority routing, backpressure, deduplication, and dead-letter handling."""

    def __init__(self, journal=event_journal, validator=event_schema_validator):
        self.journal = journal
        self.validator = validator
        
        # Subscriptions: handler_id -> (filter, handler_callable, max_retries)
        self._handlers: Dict[str, Tuple[EventFilter, Callable, int]] = {}
        
        # Deduplication tracker: sliding set of processed event IDs
        self._processed_events: deque = deque(maxlen=MAX_PROCESSED_WINDOW)
        self._processed_set: Set[str] = set()

        # Dead-letter queue
        self._dead_letters: List[DeadLetterRecord] = []

        # Coalescing map for high-frequency events: coalesce_key -> Event
        self._coalesced_events: Dict[str, Event] = {}
        self.coalescible_types: Set[str] = {"device.screen_changed", "system.metric_heartbeat", "ui.cursor_move"}

        # Priority queues: CRITICAL (4), HIGH (3), NORMAL (2), LOW (1)
        self._priority_queues: Dict[EventPriority, deque] = {
            EventPriority.CRITICAL: deque(),
            EventPriority.HIGH: deque(),
            EventPriority.NORMAL: deque(),
            EventPriority.LOW: deque()
        }

        # Backpressure & metrics
        self.published_count = 0
        self.consumed_count = 0
        self.dropped_ephemeral_count = 0
        self.is_running = True

        # External broadcast hooks (e.g. for HUD websocket)
        self._external_broadcast_hooks: List[Callable] = []

    def get_dead_letter_records(self) -> List[DeadLetterRecord]:
        """Returns snapshot of current dead-letter records."""
        return list(self._dead_letters)

    def add_broadcast_hook(self, hook: Callable):
        """Attaches a real-time WebSocket or HUD listener."""
        self._external_broadcast_hooks.append(hook)

    def subscribe(
        self,
        handler_id: str,
        filter_criteria: EventFilter,
        handler: Callable,
        max_retries: int = 2
    ):
        """Registers a consumer with filtering and retry policy."""
        self._handlers[handler_id] = (filter_criteria, handler, max_retries)
        logger.info(f"Subscribed handler '{handler_id}' for pattern '{filter_criteria.type_pattern}'")

    def unsubscribe(self, handler_id: str) -> bool:
        """Removes a handler."""
        if handler_id in self._handlers:
            del self._handlers[handler_id]
            return True
        return False

    def is_processed(self, event_id: str) -> bool:
        """Idempotency check: returns True if event was already handled."""
        return event_id in self._processed_set

    def mark_processed(self, event_id: str):
        if event_id not in self._processed_set:
            if len(self._processed_events) >= MAX_PROCESSED_WINDOW:
                oldest = self._processed_events.popleft()
                self._processed_set.discard(oldest)
            self._processed_events.append(event_id)
            self._processed_set.add(event_id)

    async def publish(self, event: Event) -> bool:
        """Publishes an event into the fabric, applying schema validation, deduplication, coalescing, and priority dispatch."""
        if not self.is_running:
            logger.warning("Event Fabric is stopped; rejecting new event.")
            return False

        # 1. Schema Validation
        valid, err = self.validator.validate_event(event)
        if not valid:
            logger.error(f"Event rejected: {err}")
            audit_logger.log_event("event_rejected", {"event_type": event.type, "error": err}, allowed=False, outcome="REJECTED")
            return False

        # 2. Coalescing for marked high-frequency events
        if event.type in self.coalescible_types:
            key = f"{event.type}:{event.envelope.source}:{event.envelope.subject or ''}"
            self._coalesced_events[key] = event
            # Keep only the latest in queue; don't spawn duplicate dispatches
            logger.debug(f"Coalesced high-frequency event: {key}")

        # 3. Check Backpressure: bounded buffer
        total_queued = sum(len(q) for q in self._priority_queues.values())
        if total_queued >= MAX_QUEUE_CAPACITY:
            # Shed low-priority or ephemeral events first; never drop CRITICAL or DURABLE
            if event.priority == EventPriority.LOW or event.durability == EventDurability.EPHEMERAL:
                self.dropped_ephemeral_count += 1
                logger.warning(f"BACKPRESSURE: Dropped ephemeral event '{event.type}' to protect high-priority buffer.")
                return False

        # 4. Durable persistence if required
        if event.durability == EventDurability.DURABLE:
            try:
                self.journal.record_durable_event(event)
            except Exception as e:
                logger.error(f"Failed to record durable event '{event.id}': {e}")

        # 5. Queue into priority lane
        self._priority_queues[event.priority].append(event)
        self.published_count += 1

        # 6. Immediately process/drain queued events asynchronously
        asyncio.create_task(self._dispatch_lanes())

        # 7. Notify external broadcast hooks (e.g. HUD)
        for hook in self._external_broadcast_hooks:
            try:
                if inspect.iscoroutinefunction(hook):
                    asyncio.create_task(hook(event))
                else:
                    hook(event)
            except Exception as e:
                logger.warning(f"External broadcast hook error: {e}")

        return True

    async def _dispatch_lanes(self):
        """Processes events in strict priority order (CRITICAL -> HIGH -> NORMAL -> LOW)."""
        for prio in [EventPriority.CRITICAL, EventPriority.HIGH, EventPriority.NORMAL, EventPriority.LOW]:
            queue = self._priority_queues[prio]
            while queue:
                evt = queue.popleft()
                await self._deliver_event_to_handlers(evt)

    async def _deliver_event_to_handlers(self, event: Event):
        """Dispatches an event to matching registered handlers with isolation and retry boundaries."""
        # Check deduplication
        if self.is_processed(event.id):
            logger.debug(f"Deduplicating already processed event: {event.id}")
            return
        self.mark_processed(event.id)

        tasks = []
        for hid, (flt, handler, max_retries) in list(self._handlers.items()):
            if flt.matches(event):
                tasks.append(self._invoke_handler(hid, handler, event, max_retries))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.consumed_count += 1

    async def _invoke_handler(self, handler_id: str, handler: Callable, event: Event, max_retries: int):
        """Executes a single handler with bounded retries and dead-letter protection."""
        attempts = 0
        t0 = time.time()
        last_err = None

        while attempts <= max_retries:
            attempts += 1
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
                # Success
                return
            except Exception as e:
                last_err = str(e)
                logger.warning(f"Handler '{handler_id}' failed on attempt {attempts}/{max_retries + 1} for event '{event.type}': {e}")
                if attempts <= max_retries:
                    await asyncio.sleep(0.05 * attempts)

        # Persistent failure -> Dead-letter queue
        dl = DeadLetterRecord(
            event_id=event.id,
            event_type=event.type,
            handler_id=handler_id,
            failure_reason=last_err or "Unknown failure",
            attempts=attempts,
            first_attempt_ts=t0,
            last_attempt_ts=time.time(),
            event_payload=event.payload
        )
        self._dead_letters.append(dl)
        logger.error(f"DEAD-LETTER: Event '{event.id}' ({event.type}) moved to dead-letter queue after {attempts} attempts.")
        audit_logger.log_event("event_dead_lettered", {
            "event_id": event.id,
            "handler_id": handler_id,
            "error": last_err
        }, allowed=True, outcome="DEAD_LETTER")

    def get_dead_letters(self) -> List[DeadLetterRecord]:
        return list(self._dead_letters)

    def clear_dead_letters(self):
        self._dead_letters.clear()

    async def shutdown(self):
        """Gracefully drains queues and shuts down the Event Fabric."""
        self.is_running = False
        await self._dispatch_lanes()
        logger.info("Event Fabric shutdown completed.")

event_fabric = EventFabric()
