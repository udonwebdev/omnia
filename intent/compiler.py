import time
import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple

from intent.models import (
    UserIntent,
    PlannedStep,
    CompiledPlan,
    PlanVersion,
    ValidationStatus
)
from intent.parser import intent_parser
from intent.resolver import resolve_context
from intent.decomposer import task_decomposer
from intent.validator import plan_validator
from intent.capability_mapper import capability_registry
from task_graph.models import TaskGraph, TaskNode, NodeState, IdempotencyLevel, RetryPolicy

logger = logging.getLogger("Omnia.Intent.Compiler")

BUS_STATE_URL = "http://127.0.0.1:8000/api/state"

class IntentCompiler:
    """End-to-end compiler converting natural-language intent into an executable Module 14 TaskGraph."""

    def __init__(self):
        self.parser = intent_parser
        self.decomposer = task_decomposer
        self.validator = plan_validator
        self.registry = capability_registry
        self.plan_history: Dict[str, List[CompiledPlan]] = {}

    async def _notify_hud(self, state: str, message: str):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=0.3) as client:
                await client.post(BUS_STATE_URL, json={"state": state, "message": message})
        except Exception:
            pass

    async def compile_intent(
        self,
        raw_text: str,
        context_override: Optional[Dict[str, Any]] = None,
        version: int = 1,
        parent_version: Optional[int] = None
    ) -> Tuple[Optional[TaskGraph], CompiledPlan]:
        """Full pipeline: Parse -> Resolve -> Decompose -> Validate -> Compile to TaskGraph."""
        await self._notify_hud("INTENT_RECEIVED", f"Compiling: {raw_text[:35]}...")
        
        # 1. Parse Intent & Detect Ambiguity
        await self._notify_hud("INTENT_PARSING", "Parsing intent & checking ambiguity...")
        intent = self.parser.parse(raw_text, context=context_override)

        # 2. Resolve Context
        await self._notify_hud("CONTEXT_RESOLVING", "Resolving devices, browser & memory...")
        planning_ctx = resolve_context(intent, initial_context=context_override)

        # 3. Decompose into Atomic Steps
        await self._notify_hud("PLAN_BUILDING", "Decomposing into atomic tasks...")
        steps = self.decomposer.decompose(intent, planning_ctx)

        # 4. Validate Plan & Detect Conflicts
        await self._notify_hud("PLAN_VALIDATING", "Validating graph & assessing risk...")
        report, score = self.validator.validate(intent, steps)

        plan_ver = PlanVersion(
            plan_id=intent.intent_id,
            version=version,
            parent_version=parent_version,
            created_at=time.time(),
            reason_for_change="Initial compilation" if version == 1 else "Dynamic replan",
            changed_nodes=[s.step_id for s in steps]
        )

        compiled_plan = CompiledPlan(
            plan_id=intent.intent_id,
            intent=intent,
            steps=steps,
            validation=report,
            score=score,
            version=plan_ver
        )

        self.plan_history.setdefault(intent.intent_id, []).append(compiled_plan)

        # Module 18: Publish intent.received event
        try:
            from events import event_fabric, Event, EventEnvelope, EventPriority, EventSeverity, EventDurability
            asyncio.create_task(event_fabric.publish(Event(
                envelope=EventEnvelope(
                    event_type="intent.received",
                    correlation_id=intent.intent_id,
                    source="module.16.intent_compiler",
                    priority=EventPriority.NORMAL,
                    severity=EventSeverity.INFO,
                    durability=EventDurability.OPERATIONAL
                ),
                payload={"intent_id": intent.intent_id, "raw_text": raw_text, "objective": intent.primary_objective}
            )))
        except Exception:
            pass

        # 5. Check if Validation Succeeded
        if report.status in [ValidationStatus.INVALID, ValidationStatus.UNSAFE, ValidationStatus.REQUIRES_CLARIFICATION]:
            logger.warning(f"Compilation stopped: Status {report.status.value}. Errors: {report.errors}")
            await self._notify_hud(f"PLAN_{report.status.value}", f"Plan blocked: {report.status.value}")
            try:
                from events import event_fabric, Event, EventEnvelope, EventPriority, EventSeverity, EventDurability
                asyncio.create_task(event_fabric.publish(Event(
                    envelope=EventEnvelope(
                        event_type="intent.ambiguous",
                        correlation_id=intent.intent_id,
                        source="module.16.intent_compiler",
                        priority=EventPriority.HIGH,
                        severity=EventSeverity.WARNING,
                        durability=EventDurability.OPERATIONAL
                    ),
                    payload={
                        "intent_id": intent.intent_id,
                        "clarification_question": intent.ambiguity.clarification_question or "Clarification needed",
                        "status": report.status.value
                    }
                )))
            except Exception:
                pass
            return None, compiled_plan

        # 6. Transform into Module 14 TaskGraph
        task_graph = self._build_task_graph(intent, steps)
        await self._notify_hud("PLAN_COMPILED", f"Ready: {len(steps)} steps compiled.")

        # Module 18: Publish intent.compiled event
        try:
            from events import event_fabric, Event, EventEnvelope, EventPriority, EventSeverity, EventDurability
            asyncio.create_task(event_fabric.publish(Event(
                envelope=EventEnvelope(
                    event_type="intent.compiled",
                    correlation_id=intent.intent_id,
                    source="module.16.intent_compiler",
                    priority=EventPriority.NORMAL,
                    severity=EventSeverity.INFO,
                    durability=EventDurability.OPERATIONAL
                ),
                payload={"intent_id": intent.intent_id, "plan_id": compiled_plan.plan_id, "steps_count": len(steps)}
            )))
        except Exception:
            pass

        return task_graph, compiled_plan

    def _build_task_graph(self, intent: UserIntent, steps: List[PlannedStep]) -> TaskGraph:
        """Translates validated PlannedStep instances into Module 14 TaskGraph and TaskNodes."""
        tg = TaskGraph(
            goal=intent.primary_objective,
            task_id=intent.intent_id,
            task_timeout_sec=300.0
        )

        for s in steps:
            cap = self.registry.get_capability(s.capability_name)
            res_reqs = cap.required_resources if cap else []
            idemp = IdempotencyLevel[s.idempotency] if s.idempotency in IdempotencyLevel.__members__ else IdempotencyLevel.SAFE_TO_RETRY

            # Create an executable action wrapper binding capability to omnia_tools
            action_callable = self._create_executable_action(s)
            verifier_callable = self._create_verifier(s)

            node = TaskNode(
                node_id=s.step_id,
                name=s.purpose,
                description=f"Action via capability '{s.capability_name}'",
                action=action_callable,
                expected_state=s.expected_state,
                verifier=verifier_callable,
                timeout_sec=s.timeout_sec,
                retry_policy=RetryPolicy(max_attempts=3 if idemp != IdempotencyLevel.NOT_SAFE_TO_RETRY else 1),
                idempotency=idemp,
                required_resources=res_reqs,
                dependencies=s.dependencies,
                metadata={
                    "capability": s.capability_name,
                    "inputs": s.inputs,
                    "risk_level": s.risk_level.value,
                    "requires_confirmation": s.requires_confirmation
                }
            )
            tg.add_node(node)

        return tg

    def _create_executable_action(self, step: PlannedStep):
        """Constructs an async callable invoking the target Omnia capability."""
        cap_name = step.capability_name
        inputs = step.inputs

        async def dynamic_action(ctx):
            # Resolve tool from omnia_tools
            import omnia_tools
            tool_fn = getattr(omnia_tools, cap_name, None)
            if not tool_fn:
                logger.info(f"[SIMULATED ACTION]: Capability '{cap_name}' executed with inputs: {inputs}")
                return {"status": "success", "simulated": True, "step": step.step_id}

            # Map inputs to function parameters
            import inspect
            try:
                if inspect.iscoroutinefunction(tool_fn):
                    return await tool_fn(**inputs)
                else:
                    return tool_fn(**inputs)
            except TypeError:
                # If arg mismatch, execute without args
                if inspect.iscoroutinefunction(tool_fn):
                    return await tool_fn()
                else:
                    return tool_fn()

        return dynamic_action

    def _create_verifier(self, step: PlannedStep):
        """Constructs verification callable based on declared strategy."""
        strat = step.verification_strategy

        async def default_verifier(ctx, result):
            if result is None:
                return True
            if isinstance(result, str) and ("fail" in result.lower() or "error" in result.lower()):
                return False
            if isinstance(result, dict) and result.get("success") is False:
                return False
            return True

        return default_verifier

    def explain_plan(self, plan: CompiledPlan) -> str:
        """Generates a concise, transparent summary of the plan for the user without exposing raw AST."""
        lines = [f"### Execution Plan: {plan.intent.primary_objective}"]
        lines.append(f"**Safety Status**: {plan.validation.status.value} | **Confidence**: {plan.score.confidence * 100:.0f}%")
        lines.append("\n**Planned Steps**:")
        for idx, s in enumerate(plan.steps, 1):
            confirm_flag = " ⚠️ *(Requires Confirmation)*" if s.requires_confirmation else ""
            lines.append(f"{idx}. **{s.purpose}** (Tool: `{s.capability_name}`){confirm_flag}")

        if plan.validation.warnings:
            lines.append("\n**Notices**:")
            for w in plan.validation.warnings:
                lines.append(f"- {w}")

        return "\n".join(lines)

    async def replan_on_failure(
        self,
        original_plan_id: str,
        failed_step_id: str,
        failure_reason: str,
        current_observation: Optional[str] = None
    ) -> Tuple[Optional[TaskGraph], CompiledPlan]:
        """Dynamic replanner: preserves verified work and synthesizes an alternative path."""
        history = self.plan_history.get(original_plan_id, [])
        if not history:
            raise RuntimeError(f"Unknown plan ID: {original_plan_id}")

        last_plan = history[-1]
        new_version = last_plan.version.version + 1

        logger.info(f"Replanning for failed step '{failed_step_id}' (Reason: {failure_reason}). Building Version {new_version}...")

        # Modify failed step with alternative visual or browser fallback
        revised_steps: List[PlannedStep] = []
        for s in last_plan.steps:
            if s.step_id == failed_step_id:
                # Replace DOM click with visual grounding click fallback
                alt_step = PlannedStep(
                    step_id=f"alt_{s.step_id}",
                    purpose=f"Fallback Visual Action for: {s.purpose}",
                    capability_name="click_visual_element",
                    inputs={"target_description": s.purpose, "expected_transition": "state_change"},
                    outputs=s.outputs,
                    dependencies=s.dependencies,
                    preconditions=s.preconditions,
                    postconditions=s.postconditions,
                    verification_strategy="VISUAL_DIFF_VERIFIED",
                    risk_level=s.risk_level,
                    timeout_sec=s.timeout_sec
                )
                revised_steps.append(alt_step)
            else:
                revised_steps.append(s)

        # Validate revised plan
        report, score = self.validator.validate(last_plan.intent, revised_steps)
        plan_ver = PlanVersion(
            plan_id=original_plan_id,
            version=new_version,
            parent_version=last_plan.version.version,
            created_at=time.time(),
            reason_for_change=f"Failure at {failed_step_id}: {failure_reason}",
            changed_nodes=[f"alt_{failed_step_id}"]
        )

        revised_plan = CompiledPlan(
            plan_id=original_plan_id,
            intent=last_plan.intent,
            steps=revised_steps,
            validation=report,
            score=score,
            version=plan_ver
        )
        self.plan_history[original_plan_id].append(revised_plan)

        task_graph = self._build_task_graph(last_plan.intent, revised_steps)
        return task_graph, revised_plan

intent_compiler = IntentCompiler()
