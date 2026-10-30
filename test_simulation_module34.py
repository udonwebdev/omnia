"""
Unit & Adversarial Tests for Omnia Module 34:
Autonomous Simulation, Digital Twin & Scenario Testing Engine.
"""

import os
import unittest
import time

from simulation.models import (
    AlternativeSearchStrategy,
    EnvironmentClassification,
    EnvironmentType,
    FaultType,
    ScenarioType,
    SimulationStatus,
    StateFidelity,
    TwinSyncMode,
)
from simulation.service import SimulationService
from simulation.persistence import SimulationRepository


class TestModule34SimulationEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = "test_module34_sim.db"
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass
        cls.repo = SimulationRepository(db_path=cls.db_path)
        cls.service = SimulationService(repository=cls.repo)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.db_path):
            try:
                os.remove(cls.db_path)
            except Exception:
                pass

    def test_01_environment_registration(self):
        """Test creating and retrieving an isolated simulation environment."""
        env = self.service.create_environment(
            environment_id="env-test-01",
            name="Workflow Test Bed",
            env_type=EnvironmentType.WORKFLOW,
            classification=EnvironmentClassification.TEST,
            supported_action_types=["task.complete", "node.failover", "resource.allocate", "api.request", "dangerous.real_world.format_disk"],
        )
        self.assertEqual(env.environment_id, "env-test-01")
        self.assertEqual(env.classification, EnvironmentClassification.TEST)

        fetched = self.repo.get_environment("env-test-01")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "Workflow Test Bed")

    def test_02_snapshot_capture_and_secret_sanitization(self):
        """Snapshots must redact sensitive credentials and compute SHA-256 integrity digest."""
        raw_state = {
            "cluster_id": "c-001",
            "api_key": "sk-secret-token-12345",
            "nodes": {"node_1": {"status": "ACTIVE"}},
            "token": "eyBearerSecretJwtTokenVal",
        }
        snap = self.service.capture_snapshot(
            snapshot_id="snap-01",
            environment_id="env-test-01",
            raw_state=raw_state,
        )
        self.assertEqual(snap.snapshot_id, "snap-01")
        self.assertEqual(snap.state_payload["api_key"], "[REDACTED_SECRET]")
        self.assertIn("api_key", snap.excluded_components)
        self.assertTrue(len(snap.integrity_digest) == 64)

        # Integrity verification
        valid, msg = self.service.snapshot_manager.verify_snapshot_integrity(snap)
        self.assertTrue(valid)

    def test_03_digital_twin_creation_and_synchronization(self):
        """Digital twins must track observed state and distinguish simulated modifications."""
        twin = self.service.register_digital_twin(
            twin_id="twin-node-01",
            source_system_id="physical_server_01",
            source_system_type="node",
            initial_observed_state={"cpu_cores": 16, "memory_gb": 64},
            sync_mode=TwinSyncMode.STATIC,
        )
        self.assertEqual(twin.twin_id, "twin-node-01")
        self.assertIn("cpu_cores", twin.observed_state)
        self.assertEqual(twin.simulated_state, {})

        # Synchronize new observations
        self.service.twin_manager.synchronize_twin(twin, {"cpu_usage_pct": 45.0})
        self.assertEqual(twin.observed_state["cpu_usage_pct"], 45.0)

        # Simulated transition must not overwrite observed facts
        self.service.twin_manager.record_simulated_transition(twin, {"simulated_load": 99.0})
        self.assertEqual(twin.simulated_state["simulated_load"], 99.0)
        self.assertNotIn("simulated_load", twin.observed_state)

    def test_04_scenario_compiler_precondition_validation(self):
        """Scenario compiler must reject contradictory or unsatisfied preconditions."""
        # 1. Contradictory precondition
        actions = [{"action_type": "task.complete", "task_id": "t1"}]
        with self.assertRaises(ValueError):
            self.service.register_scenario(
                scenario_id="scen-bad-precondition",
                name="Bad Precondition Scenario",
                scenario_type=ScenarioType.NORMAL_OPERATION,
                environment_id="env-test-01",
                initial_snapshot_id="snap-01",
                proposed_actions=actions,
                preconditions={"cluster_id": "non_existent_cluster"},
            )

        # 2. Valid precondition
        scen = self.service.register_scenario(
            scenario_id="scen-valid",
            name="Valid Scenario",
            scenario_type=ScenarioType.NORMAL_OPERATION,
            environment_id="env-test-01",
            initial_snapshot_id="snap-01",
            proposed_actions=actions,
            preconditions={"cluster_id": "c-001"},
        )
        self.assertEqual(scen.scenario_id, "scen-valid")

    def test_05_strict_non_execution_invariant_on_unsupported_actions(self):
        """Unsupported actions must fail closed without invoking production adapters."""
        snap = self.service.capture_snapshot(
            snapshot_id="snap-unsupported-test",
            environment_id="env-test-01",
            raw_state={"data": "test"},
        )
        scen = self.service.register_scenario(
            scenario_id="scen-unsupported",
            name="Unsupported Action Scenario",
            scenario_type=ScenarioType.NORMAL_OPERATION,
            environment_id="env-test-01",
            initial_snapshot_id="snap-unsupported-test",
            proposed_actions=[{"action_type": "dangerous.real_world.format_disk"}],
        )
        exec_rec = self.service.run_simulation(
            simulation_id="sim-unsupported-run",
            scenario_id="scen-unsupported",
        )
        self.assertEqual(exec_rec.status, SimulationStatus.FAILED)
        self.assertIn("UNSUPPORTED_SIMULATION_ACTION", exec_rec.error_message)

    def test_06_deterministic_simulation_execution(self):
        """Deterministic simulation must execute step-by-step and record state transitions."""
        snap = self.service.capture_snapshot(
            snapshot_id="snap-det-01",
            environment_id="env-test-01",
            raw_state={"tasks": {}, "resources": {"cpu": 0.0}},
        )
        actions = [
            {"action_type": "resource.allocate", "resource": "cpu", "amount": 2.0},
            {"action_type": "task.complete", "task_id": "task_1", "duration": 1.5},
            {"action_type": "task.complete", "task_id": "task_2", "duration": 2.0},
        ]
        scen = self.service.register_scenario(
            scenario_id="scen-det-01",
            name="Deterministic Pipeline",
            scenario_type=ScenarioType.NORMAL_OPERATION,
            environment_id="env-test-01",
            initial_snapshot_id="snap-det-01",
            proposed_actions=actions,
        )
        rec = self.service.run_simulation(
            simulation_id="sim-det-01",
            scenario_id="scen-det-01",
        )
        self.assertEqual(rec.status, SimulationStatus.COMPLETED)
        self.assertEqual(rec.current_step, 3)
        final_state = rec.result_summary["final_state"]
        self.assertEqual(final_state["resources"]["cpu"], 2.0)
        self.assertEqual(final_state["tasks"]["task_1"]["status"], "COMPLETED")
        self.assertEqual(final_state["tasks"]["task_2"]["status"], "COMPLETED")

    def test_07_fault_injection_and_interruption(self):
        """Injected faults must halt simulation at specified activation step."""
        snap = self.service.capture_snapshot(
            snapshot_id="snap-fault-01",
            environment_id="env-test-01",
            raw_state={"tasks": {}},
        )
        actions = [
            {"action_type": "task.complete", "task_id": "task_1"},
            {"action_type": "task.complete", "task_id": "task_2", "target": "worker_b"},
            {"action_type": "task.complete", "task_id": "task_3"},
        ]
        scen = self.service.register_scenario(
            scenario_id="scen-fault-01",
            name="Fault Scenario",
            scenario_type=ScenarioType.FAILURE_INJECTION,
            environment_id="env-test-01",
            initial_snapshot_id="snap-fault-01",
            proposed_actions=actions,
        )
        fault = self.service.inject_fault(
            fault_id="fault-crash-01",
            simulation_id="sim-fault-01",
            fault_type=FaultType.WORKER_CRASH,
            target_component="worker_b",
            activation_step=2,
        )
        rec = self.service.run_simulation(
            simulation_id="sim-fault-01",
            scenario_id="scen-fault-01",
            fault_specs=[fault],
        )
        self.assertEqual(rec.status, SimulationStatus.FAILED)
        self.assertEqual(rec.current_step, 2)
        self.assertIn("Action halted by injected fault: WORKER_CRASH on worker_b", rec.error_message)

    def test_08_alternative_path_exploration_and_tradeoff_ranking(self):
        """Alternative explorer must rank candidate sequences by reliability and duration trade-offs."""
        init_state = {"tasks": {}, "resources": {"cpu": 0.0}}
        seq_fast_risky = [
            {"action_type": "task.complete", "task_id": "t1", "duration": 0.5},
            {"action_type": "dangerous.unknown.action", "task_id": "t2"},
        ]
        seq_safe_reliable = [
            {"action_type": "task.complete", "task_id": "t1", "duration": 1.0},
            {"action_type": "task.complete", "task_id": "t2", "duration": 1.2},
        ]
        res = self.service.explore_alternatives(
            initial_state=init_state,
            candidate_action_sequences=[seq_fast_risky, seq_safe_reliable],
            strategy=AlternativeSearchStrategy.RELIABILITY_OPTIMIZED,
        )
        self.assertEqual(res["total_candidates_evaluated"], 2)
        rec = res["recommended_candidate"]
        self.assertIsNotNone(rec)
        self.assertTrue(rec["success"])
        self.assertEqual(rec["candidate_index"], 1)

    def test_09_fidelity_assessment_and_reality_comparison(self):
        """Comparing simulation predictions to real observations assesses model accuracy."""
        sim_metrics = {"latency_ms": 110.0, "success_rate": 0.95}
        real_metrics = {"latency_ms": 115.0, "success_rate": 0.94}

        assessment = self.service.compare_with_reality(
            simulation_id="sim-det-01",
            twin_id="twin-node-01",
            simulated_metrics=sim_metrics,
            observed_real_metrics=real_metrics,
            reality_observation_id="real-obs-99",
        )
        self.assertEqual(assessment.fidelity_level, StateFidelity.HIGH)
        self.assertFalse(assessment.recommended_learning_signal)

        divergent_real = {"latency_ms": 250.0, "success_rate": 0.60}
        bad_assessment = self.service.compare_with_reality(
            simulation_id="sim-det-01",
            twin_id="twin-node-01",
            simulated_metrics=sim_metrics,
            observed_real_metrics=divergent_real,
        )
        self.assertEqual(bad_assessment.fidelity_level, StateFidelity.LOW)
        self.assertTrue(bad_assessment.recommended_learning_signal)


if __name__ == "__main__":
    unittest.main()
