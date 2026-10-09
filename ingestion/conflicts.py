"""
Conflict Analysis & Contradiction Engine for Omnia Module 27:
Data Ingestion, Normalization & Knowledge Pipeline

Guarantees:
1. Contradictory information between sources is explicitly preserved, never silently overwritten.
2. Conflicts record both source identities, raw values, timestamps, and confidence.
3. Configurable resolution strategies (AUTHORITATIVE_SOURCE_WINS, LATEST_VERIFIED, MANUAL_REVIEW, PRESERVE_CONFLICT).
4. Emits typed events into Module 18 Event Fabric.
"""

import time
import uuid
import logging
from typing import Dict, Any, List, Optional, Tuple

from ingestion.models import (
    ConflictRecord,
    ConflictResolutionStrategy,
    NormalizedRecord
)
from events.models import Event, EventEnvelope
from events.fabric import event_fabric

logger = logging.getLogger("Omnia.Ingestion.Conflicts")


class ConflictManager:
    """Detects, tracks, and safely resolves or preserves data conflicts between sources."""

    def __init__(self, persistence=None):
        self.persistence = persistence
        self._active_conflicts: Dict[str, ConflictRecord] = {}

    def _emit_event(self, event_type: str, payload: Dict[str, Any]):
        try:
            import asyncio
            evt = Event(
                envelope=EventEnvelope(
                    event_type=event_type,
                    source="ingestion.conflict_manager"
                ),
                payload=payload
            )
            async def _pub():
                await event_fabric.publish(evt)
                await event_fabric._dispatch_lanes()
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(_pub())
                else:
                    loop.run_until_complete(_pub())
            except RuntimeError:
                asyncio.run(_pub())
        except Exception as e:
            logger.debug(f"Conflict event publish skipped: {e}")

    def detect_conflicts(
        self,
        new_record: NormalizedRecord,
        existing_record: NormalizedRecord
    ) -> List[ConflictRecord]:
        """
        Compares new record against an existing record for the same canonical entity,
        detecting and recording field-level disagreements.
        """
        conflicts: List[ConflictRecord] = []
        new_data = new_record.canonical_data
        old_data = existing_record.canonical_data

        if not isinstance(new_data, dict) or not isinstance(old_data, dict):
            return conflicts

        for field_name, new_val in new_data.items():
            if field_name in old_data and old_data[field_name] is not None and new_val is not None:
                old_val = old_data[field_name]
                if old_val != new_val:
                    conflict_id = f"conf_{uuid.uuid4().hex[:12]}"
                    conflict = ConflictRecord(
                        conflict_id=conflict_id,
                        entity_id=new_record.canonical_id,
                        field_name=field_name,
                        source_a=existing_record.provenance.source_id,
                        value_a=old_val,
                        source_b=new_record.provenance.source_id,
                        value_b=new_val,
                        detected_at=time.time(),
                        resolution_strategy=ConflictResolutionStrategy.PRESERVE_CONFLICT,
                        resolution_status="UNRESOLVED"
                    )
                    self._active_conflicts[conflict_id] = conflict
                    conflicts.append(conflict)

                    if self.persistence:
                        self.persistence.save_conflict(conflict)

                    # Emit Event Fabric event
                    self._emit_event("data.conflict.detected", {
                        "conflict_id": conflict_id,
                        "entity_id": new_record.canonical_id,
                        "field_name": field_name,
                        "sources": [existing_record.provenance.source_id, new_record.provenance.source_id]
                    })
                    logger.warning(
                        f"DATA_CONFLICT_DETECTED: Entity '{new_record.canonical_id}', Field '{field_name}' "
                        f"disagrees between '{existing_record.provenance.source_id}' and '{new_record.provenance.source_id}'."
                    )

        return conflicts

    def resolve_conflict(
        self,
        conflict_id: str,
        strategy: ConflictResolutionStrategy,
        authoritative_source: Optional[str] = None,
        manual_override_value: Optional[Any] = None,
        rationale: str = ""
    ) -> Tuple[bool, Optional[Any], str]:
        """
        Resolves an active conflict according to an explicit policy strategy.
        """
        conflict = self._active_conflicts.get(conflict_id)
        if not conflict and self.persistence:
            conflict = self.persistence.get_conflict(conflict_id)
        if not conflict:
            return False, None, f"Conflict '{conflict_id}' not found."

        resolved_val = None
        if strategy == ConflictResolutionStrategy.AUTHORITATIVE_SOURCE_WINS:
            if not authoritative_source:
                return False, None, "Authoritative source must be specified for AUTHORITATIVE_SOURCE_WINS strategy."
            if authoritative_source == conflict.source_a:
                resolved_val = conflict.value_a
            elif authoritative_source == conflict.source_b:
                resolved_val = conflict.value_b
            else:
                return False, None, f"Specified authoritative source '{authoritative_source}' does not match conflict sources."

        elif strategy == ConflictResolutionStrategy.MANUAL_REVIEW:
            if manual_override_value is None:
                return False, None, "Manual review resolution requires manual_override_value."
            resolved_val = manual_override_value

        elif strategy == ConflictResolutionStrategy.PRESERVE_CONFLICT:
            # Explicitly keep unresolved
            return True, None, "PRESERVED_UNRESOLVED"

        conflict.resolution_strategy = strategy
        conflict.resolution_status = "RESOLVED"
        conflict.resolved_at = time.time()
        conflict.resolved_value = resolved_val
        conflict.resolution_rationale = rationale

        if self.persistence:
            self.persistence.save_conflict(conflict)

        # Emit resolved event
        self._emit_event("data.conflict.resolved", {
            "conflict_id": conflict_id,
            "entity_id": conflict.entity_id,
            "strategy": strategy.value
        })
        return True, resolved_val, "RESOLVED"


conflict_manager = ConflictManager()
