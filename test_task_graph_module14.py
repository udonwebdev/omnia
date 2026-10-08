import asyncio
import time
import logging
from task_graph import (
    task_executor,
    TaskGraph,
    TaskNode,
    TaskState,
    NodeState,
    FailureCategory,
    RecoveryStrategy,
    IdempotencyLevel,
    ExecutionContext,
    resource_manager,
    recovery_engine
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

async def run_module14_test_suite():
    print("=" * 65)
    print("      OMNIA MODULE 14: DYNAMIC TASK GRAPH TEST SUITE      ")
    print("=" * 65)

    # 1. Sequential Execution & Dependency Ordering
    print("\n[TEST 1] Task Graph Node Dependencies & Execution Ordering...")
    tg = TaskGraph(goal="Sequential Data Processing Pipeline")
    execution_order = []

    async def step_a(ctx):
        execution_order.append("A")
        return {"records": 100}

    async def step_b(ctx):
        execution_order.append("B")
        return {"filtered": 80}

    async def step_c(ctx):
        execution_order.append("C")
        return "Complete"

    tg.add_node(TaskNode(node_id="A", name="Extract", description="Extract records", action=step_a))
    tg.add_node(TaskNode(node_id="B", name="Transform", description="Filter records", action=step_b, dependencies=["A"]))
    tg.add_node(TaskNode(node_id="C", name="Load", description="Commit records", action=step_c, dependencies=["B"]))

    res = await task_executor.execute_task(tg)
    assert res["state"] == "COMPLETED"
    assert execution_order == ["A", "B", "C"]
    print(f" -> Execution order verified: {execution_order} (Progress: {res['progress_percentage']}%)")
    print(" -> Dependency Graph: PASS")

    # 2. State Verification (Pass vs Failure Detection)
    print("\n[TEST 2] Verification Step (Distinguishing API Return vs Verified State)...")
    tg_ver = TaskGraph(goal="Verification Failure Test")
    
    async def deceitful_action(ctx):
        # Action API returns without exception, but expected condition is not met
        return "unrelated_payload"

    async def strict_verifier(ctx, result):
        # Verifies if expected key is present
        return result == "desired_state_token"

    tg_ver.add_node(TaskNode(
        node_id="v1",
        name="Strict Verification Step",
        description="Must match token",
        action=deceitful_action,
        expected_state="desired_state_token",
        verifier=strict_verifier
    ))

    res_ver = await task_executor.execute_task(tg_ver)
    assert res_ver["state"] == "FAILED"
    print(f" -> Verification engine rejected invalid state: PASS (Task State: {res_ver['state']})")

    # 3. Controlled Retries & Exponential Backoff
    print("\n[TEST 3] Bounded Retries & Backoff...")
    tg_retry = TaskGraph(goal="Retry Test")
    retry_count = 0

    async def flaky_service(ctx):
        nonlocal retry_count
        retry_count += 1
        if retry_count < 3:
            raise TimeoutError("Simulated socket timeout")
        return "recovered_on_attempt_3"

    node_retry = TaskNode(
        node_id="r1",
        name="Flaky Service",
        description="Recovers on 3rd try",
        action=flaky_service
    )
    node_retry.retry_policy.base_delay_sec = 0.05
    node_retry.retry_policy.max_delay_sec = 0.2
    tg_retry.add_node(node_retry)

    res_retry = await task_executor.execute_task(tg_retry)
    assert res_retry["state"] == "COMPLETED"
    assert retry_count == 3
    print(f" -> Retried {retry_count} times with exponential backoff: PASS")

    # 4. Resource Locking & Mutual Exclusion
    print("\n[TEST 4] Resource Locking & Concurrency Protection...")
    acquired_1 = await resource_manager.acquire_locks("task_x", ["desktop:keyboard"], timeout_sec=0.5)
    assert acquired_1 is True
    
    # Task Y attempting to acquire the same resource must be blocked
    acquired_2 = await resource_manager.acquire_locks("task_y", ["desktop:keyboard"], timeout_sec=0.2)
    assert acquired_2 is False
    print(" -> Mutual exclusion on shared resource: PASS")

    await resource_manager.release_locks("task_x")
    acquired_2_retry = await resource_manager.acquire_locks("task_y", ["desktop:keyboard"], timeout_sec=0.5)
    assert acquired_2_retry is True
    await resource_manager.release_locks("task_y")
    print(" -> Resource release and re-acquisition: PASS")

    # 5. Loop Detection
    print("\n[TEST 5] Loop Detection & Infinite Failure Prevention...")
    tg_loop = TaskGraph(goal="Infinite Loop Trapping")
    
    async def permanent_failure(ctx):
        raise RuntimeError("Permanent system fault")

    node_loop = TaskNode(node_id="loop_node", name="Permanent Fault", description="Always fails", action=permanent_failure)
    node_loop.retry_policy.max_attempts = 10
    node_loop.retry_policy.base_delay_sec = 0.01
    tg_loop.add_node(node_loop)

    res_loop = await task_executor.execute_task(tg_loop)
    assert res_loop["state"] == "FAILED"
    print(f" -> Loop halted safely without hanging: PASS (State: {res_loop['state']})")

    # 6. Dynamic Replanning
    print("\n[TEST 6] Dynamic Replanning on Failure...")
    tg_replan = TaskGraph(goal="Dynamic Replan Test")

    async def failing_button_click(ctx):
        raise RuntimeError("VISION_TARGET_NOT_FOUND: Could not click button via DOM")

    node_click = TaskNode(
        node_id="click_submit",
        name="Click Submit Button",
        description="Clicks via selector",
        action=failing_button_click,
        metadata={"allow_replan": True, "target_label": "Submit"}
    )
    node_click.retry_policy.max_attempts = 1
    tg_replan.add_node(node_click)

    # Test that replanner introduces fallback node
    res_replan = await task_executor.execute_task(tg_replan)
    # The visual fallback was dynamically generated and attempted
    assert tg_replan.replan_count > 0
    print(f" -> Dynamic replanning engaged (Replans: {tg_replan.replan_count}): PASS")

    # 7. Task Cancellation & Graceful Teardown
    print("\n[TEST 7] Task Cancellation Propagation...")
    tg_cancel = TaskGraph(goal="Cancellation Test")

    async def long_running_task(ctx):
        await asyncio.sleep(5.0)
        return "Done"

    tg_cancel.add_node(TaskNode(node_id="long_1", name="Sleep Step", description="Sleeps 5s", action=long_running_task))

    task_coro = asyncio.create_task(task_executor.execute_task(tg_cancel))
    await asyncio.sleep(0.1) # Let task start
    task_executor.cancel_task(tg_cancel.task_id)

    res_cancel = await task_coro
    assert res_cancel["state"] == "CANCELLED"
    print(f" -> Task cancellation propagated: PASS (State: {res_cancel['state']})")

    # 8. Pause & Resume Lifecycle
    print("\n[TEST 8] Task Pause & Resume Lifecycle...")
    tg_pause = TaskGraph(goal="Pause and Resume Test")
    paused_step_executed = False

    async def step_pre(ctx):
        await asyncio.sleep(0.3)
        return "Pre-done"

    async def pause_step(ctx):
        nonlocal paused_step_executed
        paused_step_executed = True
        return "Resumed"

    tg_pause.add_node(TaskNode(node_id="p1", name="Long Step", description="Gives window to pause", action=step_pre))
    tg_pause.add_node(TaskNode(node_id="p2", name="Pause Step", description="Executes after resume", action=pause_step, dependencies=["p1"]))

    run_coro = asyncio.create_task(task_executor.execute_task(tg_pause))
    await asyncio.sleep(0.05)
    task_executor.pause_task(tg_pause.task_id)
    print(" -> Pausing task...")
    await asyncio.sleep(0.4) # Wait for p1 to finish and hit the pause loop
    assert tg_pause.state == TaskState.PAUSED, f"Expected state PAUSED, got {tg_pause.state.value}"
    print(" -> Task verified in PAUSED state.")
    task_executor.resume_task(tg_pause.task_id)
    res_pause = await run_coro
    assert res_pause["state"] == "COMPLETED"
    assert paused_step_executed is True
    print(" -> Task resumed and completed: PASS")

    print("\n" + "=" * 65)
    print("    ALL MODULE 14 TASK GRAPH TESTS COMPLETED SUCCESSFULLY!    ")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(run_module14_test_suite())
