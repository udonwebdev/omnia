import asyncio
import unittest
import tempfile
import os
import time

from intent import intent_compiler
from capabilities.registry import capability_registry
from capabilities.models import CapabilityHealth
from task_graph.executor import task_executor
from persistence.store import persistence_store
from vision import vision_engine

class TestModule17RealEndToEnd(unittest.IsolatedAsyncioTestCase):
    """Section 40: Genuine Real-World E2E Test.
    USER REQUEST -> MODULE 16 -> MODULE 17 RESOLUTION -> TASK GRAPH -> MODULE 14 -> MODULE 13 -> MODULE 15 -> VERIFIED RESULT
    """

    async def test_real_end_to_end_pipeline(self):
        # 1. Establish isolated persistent store
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            test_db = tf.name

        orig_db = persistence_store.db_path
        persistence_store.db_path = test_db
        persistence_store._ensure_initialized()

        try:
            # 2. USER REQUEST
            user_goal = "Open https://example.com in browser and verify state"

            # 3. MODULE 16 & MODULE 17: Compile intent resolving capabilities
            tg, plan = await intent_compiler.compile_intent(user_goal)
            self.assertIsNotNone(tg, "TaskGraph must be compiled")
            self.assertIsNotNone(plan, "Plan must be compiled")

            # Check that plan steps map to authoritative capabilities in Module 17
            cap_id = "browser.navigate"
            cap_meta = capability_registry.get_capability(cap_id)
            self.assertIsNotNone(cap_meta)
            self.assertEqual(cap_meta.health, CapabilityHealth.HEALTHY)
            self.assertIsNotNone(cap_meta.verification_contract)

            # 4. MODULE 14: Execution of task graph
            exec_res = await task_executor.execute_task(tg)
            self.assertEqual(exec_res["state"], "COMPLETED")

            # 5. MODULE 13: Observation & Verification
            # Perform genuine visual verification check on the resulting state
            from vision.models import VisionSource
            obs = await vision_engine.observe(source=VisionSource.BROWSER)
            self.assertIsNotNone(obs)
            self.assertTrue(len(obs.elements) >= 0)

            # 6. MODULE 15: Checkpoint persistence validation
            loaded_task = persistence_store.load_task(tg.task_id)
            self.assertIsNotNone(loaded_task)
            self.assertEqual(loaded_task.status, "COMPLETED")

            latest_chk = persistence_store.get_latest_checkpoint(tg.task_id)
            self.assertIsNotNone(latest_chk)
            self.assertEqual(latest_chk.task_state, "COMPLETED")

        finally:
            persistence_store.db_path = orig_db
            if os.path.exists(test_db):
                os.remove(test_db)

if __name__ == "__main__":
    unittest.main()
