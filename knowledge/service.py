"""
Omnia Module 30: Knowledge Graph & Entity Resolution Service
Orchestrates entity lifecycle, relationship assertion, resolution, graph queries,
and integration with the Event Fabric, Capability Registry, and Replication.
"""

import uuid
import time
import logging
from typing import Dict, Any, List, Optional

from knowledge.models import (
    GraphEntity,
    GraphRelationship,
    EntityIdentity,
    ResolutionCandidate,
    EntityType,
    EntityStatus,
    RelationshipStatus,
    IdentifierType,
    ResolutionStatus,
    Subgraph,
    GraphTraversalPath,
)
from knowledge.persistence import KnowledgePersistence
from knowledge.resolver import EntityResolver
from knowledge.traversal import GraphTraversalEngine
from events.fabric import event_fabric, EventFabric
from events.models import Event
from capabilities.registry import capability_registry, CapabilityRegistry

logger = logging.getLogger("Omnia.Knowledge.Service")


class KnowledgeGraphService:
    def __init__(
        self,
        persistence: Optional[KnowledgePersistence] = None,
        event_bus: Optional[EventFabric] = None,
        registry: Optional[CapabilityRegistry] = None,
    ):
        self.persistence = persistence or KnowledgePersistence()
        self.event_bus = event_bus or event_fabric
        self.registry = registry or capability_registry
        self.resolver = EntityResolver(self.persistence)
        self.traversal = GraphTraversalEngine(self.persistence)

        self._register_capabilities()

    def _register_capabilities(self) -> None:
        try:
            from capabilities.models import (
                Capability, CapabilityCategory, CapabilityProvider,
                CapabilityHealth, RiskLevel, SideEffectType, IdempotencyType
            )
            cap = Capability(
                capability_id="knowledge.graph_operations",
                name="Knowledge Graph & Entity Resolution Engine",
                category=CapabilityCategory.MEMORY,
                provider=CapabilityProvider(
                    provider_id="provider.knowledge.local",
                    name="Knowledge Graph Engine",
                    node_id="local",
                    is_local=True
                ),
                version="1.0.0",
                health=CapabilityHealth.HEALTHY,
                risk_level=RiskLevel.LOW,
                side_effect_type=SideEffectType.READ,
                idempotency=IdempotencyType.STRICTLY_IDEMPOTENT
            )
            self.registry.register_capability(cap)
            logger.info("Registered knowledge.graph_operations capability into registry.")
        except Exception as e:
            logger.debug(f"Knowledge capability registration bypassed: {e}")

    def _emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        if self.event_bus:
            try:
                import asyncio
                from events.models import EventEnvelope
                envelope = EventEnvelope(
                    event_id=f"evt_{uuid.uuid4().hex[:12]}",
                    event_type=event_type,
                    source="knowledge_graph_service"
                )
                ev = Event(
                    envelope=envelope,
                    payload=payload,
                )
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self.event_bus.publish(ev))
                    else:
                        loop.run_until_complete(self.event_bus.publish(ev))
                except RuntimeError:
                    asyncio.run(self.event_bus.publish(ev))
            except Exception as e:
                logger.debug(f"Knowledge event emission bypassed: {e}")

    # --- ENTITY OPERATIONS ---

    def create_entity(
        self,
        canonical_name: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        aliases: Optional[List[str]] = None,
        attributes: Optional[Dict[str, Any]] = None,
        confidence: float = 1.0,
        provenance_ids: Optional[List[str]] = None,
        identities: Optional[List[Dict[str, Any]]] = None,
    ) -> GraphEntity:
        eid = entity_id or f"ent-{uuid.uuid4().hex[:12]}"
        e_type = EntityType(entity_type.upper()) if entity_type.upper() in EntityType.__members__ else EntityType.CUSTOM

        entity = GraphEntity(
            entity_id=eid,
            canonical_name=canonical_name,
            entity_type=e_type,
            aliases=aliases or [],
            attributes=attributes or {},
            confidence=confidence,
            provenance_ids=provenance_ids or [],
            valid_from=time.time(),
            created_at=time.time(),
            updated_at=time.time(),
        )
        self.persistence.upsert_entity(entity)

        # Store explicit identities if provided
        if identities:
            for item in identities:
                itype_str = item.get("identifier_type", "CUSTOM").upper()
                itype = IdentifierType(itype_str) if itype_str in IdentifierType.__members__ else IdentifierType.CUSTOM
                ident = EntityIdentity(
                    identity_id=f"ident-{uuid.uuid4().hex[:10]}",
                    entity_id=eid,
                    identifier_type=itype,
                    identifier_value=str(item.get("identifier_value", "")),
                    confidence=float(item.get("confidence", 1.0)),
                )
                self.persistence.add_identity(ident)

        # Evaluate similarity against peers
        candidates = self.resolver.evaluate_candidates(entity, min_threshold=0.6)

        # Publish event
        self._emit(
            "entity.created",
            {
                "entity_id": eid,
                "entity_type": e_type.value,
                "canonical_name": canonical_name,
                "candidate_count": len(candidates),
            },
        )
        return entity

    def get_entity(self, entity_id: str) -> Optional[GraphEntity]:
        return self.persistence.get_entity(entity_id)

    # --- RELATIONSHIP OPERATIONS ---

    def assert_relationship(
        self,
        source_id: str,
        predicate: str,
        target_id: str,
        properties: Optional[Dict[str, Any]] = None,
        confidence: float = 1.0,
        weight: float = 1.0,
        directed: bool = True,
        provenance_ids: Optional[List[str]] = None,
    ) -> GraphRelationship:
        # Verify source and target entities exist
        src = self.persistence.get_entity(source_id)
        tgt = self.persistence.get_entity(target_id)
        if not src:
            raise ValueError(f"Source entity {source_id} does not exist in knowledge graph.")
        if not tgt:
            raise ValueError(f"Target entity {target_id} does not exist in knowledge graph.")

        rel_id = f"rel-{uuid.uuid4().hex[:12]}"
        rel = GraphRelationship(
            relationship_id=rel_id,
            source_id=source_id,
            predicate=predicate.upper(),
            target_id=target_id,
            properties=properties or {},
            confidence=confidence,
            weight=weight,
            directed=directed,
            provenance_ids=provenance_ids or [],
            valid_from=time.time(),
            created_at=time.time(),
            updated_at=time.time(),
        )
        self.persistence.upsert_relationship(rel)

        # Emit event
        self._emit(
            "relationship.asserted",
            {
                "relationship_id": rel_id,
                "source_id": source_id,
                "predicate": predicate.upper(),
                "target_id": target_id,
            },
        )
        return rel

    # --- GRAPH TRAVERSAL & QUERY ---

    def query_neighborhood(
        self,
        center_entity_id: str,
        max_depth: int = 2,
        min_confidence: float = 0.0,
        allowed_predicates: Optional[List[str]] = None,
    ) -> Subgraph:
        return self.traversal.extract_subgraph(
            center_entity_id=center_entity_id,
            max_depth=max_depth,
            min_confidence=min_confidence,
            allowed_predicates=allowed_predicates,
        )

    def find_path(
        self,
        start_entity_id: str,
        target_entity_id: str,
        max_depth: int = 5,
        min_confidence: float = 0.0,
    ) -> Optional[GraphTraversalPath]:
        return self.traversal.find_shortest_path(
            start_entity_id=start_entity_id,
            target_entity_id=target_entity_id,
            max_depth=max_depth,
            min_confidence=min_confidence,
        )

    # --- RESOLUTION & SPLIT ---

    def resolve_candidates(self, auto_merge_threshold: float = 0.85) -> List[Dict[str, Any]]:
        actions = self.resolver.auto_resolve(auto_merge_threshold=auto_merge_threshold)
        for act in actions:
            self._emit(
                "entity.resolved",
                {
                    "resolved_entity_id": act["primary_id"],
                    "merged_entity_id": act["merged_id"],
                    "canonical_name": self.persistence.get_entity(act["primary_id"]).canonical_name if self.persistence.get_entity(act["primary_id"]) else "",
                    "candidate_count": len(actions),
                },
            )
        return actions

    def split_entity(self, merged_id: str, reason: str = "") -> bool:
        success = self.persistence.split_entity(merged_id, reason=reason)
        if success:
            self._emit(
                "entity.split",
                {
                    "original_entity_id": merged_id,
                    "split_entity_ids": [merged_id],
                    "reason": reason,
                },
            )
        return success


# Default global instance
knowledge_graph_service = KnowledgeGraphService()
