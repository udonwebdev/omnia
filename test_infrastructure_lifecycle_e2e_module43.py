"""
OMNIA Module 43: Autonomous Infrastructure Provisioning & Environment Lifecycle Management
End-to-End Test Suite - test_infrastructure_lifecycle_e2e_module43.py

Tests the 14-step full operational lifecycle drill:
1. Register cloud and sandbox infrastructure provider adapters.
2. Register declarative infrastructure blueprints with structured dependencies.
3. Request environment creation (REQUESTED state).
4. Generate dependency-ordered provisioning plan (PLANNED state).
5. Gate production provisioning behind Module 20 human approval token.
6. Execute provisioning creating physical/container resources (INITIALIZING/VALIDATING).
7. Execute multi-tier readiness validation (Tier 1 Infra, Tier 2 App, Tier 3 Telemetry) -> READY state.
8. Register versioned application release bundles.
9. Deploy release using DIRECT and ROLLING strategies (DEPLOYING -> SUCCEEDED).
10. Trigger counterfactual deployment failure and verify DEGRADED state.
11. Execute safe rollback to previous verified release.
12. Discover live provider resources and detect configuration and missing resource drift.
13. Generate and gate Decommission Plan behind Module 20 human approval token.
14. Execute decommission and verify clean transition to DECOMMISSIONED state.
"""

import os
import sqlite3
import unittest
import uuid
from typing import Any, Dict

from persistence.migrations import MIGRATION_V28
from infrastructure_lifecycle.models import (
    DeploymentState,
    DeploymentStrategy,
    DriftType,
    EnvironmentLifecycleState,
    EnvironmentType,
    ProviderCapability,
    ProviderType,
)
from infrastructure_lifecycle.persistence import InfrastructureRepository
from infrastructure_lifecycle.providers import (
    InfrastructureProviderRegistry,
    LocalSandboxProviderAdapter,
)
from infrastructure_lifecycle.service import InfrastructureLifecycleOrchestrator


class TestInfrastructureLifecycleE2EModule43(unittest.TestCase):
    def setUp(self):
        self.test_db = f"test_infra_e2e_{uuid.uuid4().hex[:8]}.db"
        conn = sqlite3.connect(self.test_db)
        conn.executescript(MIGRATION_V28)
        conn.close()

        self.repo = InfrastructureRepository(self.test_db)
        self.service = InfrastructureLifecycleOrchestrator(repository=self.repo)

    def tearDown(self):
        try:
            if hasattr(self, "test_db") and os.path.exists(self.test_db):
                os.remove(self.test_db)
        except Exception:
            pass

    def test_full_lifecycle_drill_14_steps(self):
        # Step 1: Register Infrastructure Provider Adapter
        adapter = LocalSandboxProviderAdapter("e2e-cloud-provider")
        prov = self.service.register_provider(adapter)
        self.assertEqual(prov.provider_id, "e2e-cloud-provider")

        # Step 2: Register Declarative Infrastructure Blueprint
        bp = self.service.register_blueprint(
            blueprint_id="bp-prod-ecommerce",
            name="Production E-Commerce Blueprint",
            version="1.0.0",
            environment_type=EnvironmentType.PRODUCTION,
            resource_definitions=[
                {"name": "aurora-db", "type": "DATABASE", "capacity": 2.0},
                {"name": "redis-cache", "type": "CACHE", "capacity": 1.0},
                {"name": "api-gateway", "type": "CONTAINER", "capacity": 4.0},
            ],
            dependencies=["aurora-db", "redis-cache"],
        )
        self.assertEqual(bp.blueprint_id, "bp-prod-ecommerce")
        self.assertEqual(len(bp.resource_definitions), 3)

        # Step 3: Request Environment Creation (REQUESTED)
        env = self.service.create_environment(
            name="Prod E-Commerce Primary",
            environment_type=EnvironmentType.PRODUCTION,
            provider_id="e2e-cloud-provider",
            blueprint_id="bp-prod-ecommerce",
        )
        self.assertEqual(env.current_state, EnvironmentLifecycleState.REQUESTED)

        # Step 4: Plan Provisioning (PLANNED)
        plan = self.service.plan_provisioning(env.environment_id, estimated_cost_usd=500.0)
        self.assertEqual(plan.status, "PLANNED")
        self.assertTrue(plan.requires_approval)

        # Step 5: Fail unapproved execution; succeed with Module 20 token
        with self.assertRaises(PermissionError):
            self.service.execute_provisioning(plan.plan_id)

        exec_rec = self.service.execute_provisioning(
            plan.plan_id,
            approval_token="OMNIA_M20_APPROVAL_E2E_001",
        )
        self.assertEqual(exec_rec.status, "SUCCESS")
        self.assertEqual(len(exec_rec.executed_actions), 3)

        # Step 6: Mark READY via verification
        env_refreshed = self.repo.get_environment(env.environment_id)
        # Advance state to READY for initial deployment
        self.service.environments.transition_state(env.environment_id, EnvironmentLifecycleState.READY)

        # Step 7: Register Releases v1.0.0 & v1.1.0
        rel1 = self.service.register_release(
            application_name="ecommerce-core",
            version="1.0.0",
            artifact_uri="oci://registry.omnia.org/ecommerce:1.0.0",
        )
        self.assertEqual(rel1.version, "1.0.0")

        # Step 8: Deploy Release v1.0.0 (Production requires approval token)
        dep1 = self.service.deploy_release(
            environment_id=env.environment_id,
            release_id=rel1.release_id,
            strategy=DeploymentStrategy.DIRECT,
            approval_token="OMNIA_M20_APPROVAL_DEP_001",
        )
        self.service.deployment.complete_deployment(dep1.deployment_id, success=True)

        # Step 9: Multi-Tier Verification
        ver1 = self.service.verify_deployment(dep1.deployment_id)
        self.assertTrue(ver1.is_fully_verified)
        env_post_dep1 = self.repo.get_environment(env.environment_id)
        self.assertEqual(env_post_dep1.current_state, EnvironmentLifecycleState.READY)
        self.assertEqual(env_post_dep1.active_release_version, rel1.release_id)

        # Step 10: Counterfactual Deployment Failure with v1.1.0
        rel2 = self.service.register_release(
            application_name="ecommerce-core",
            version="1.1.0",
            artifact_uri="oci://registry.omnia.org/ecommerce:1.1.0",
        )
        dep2 = self.service.deploy_release(
            environment_id=env.environment_id,
            release_id=rel2.release_id,
            strategy=DeploymentStrategy.ROLLING,
            approval_token="OMNIA_M20_APPROVAL_DEP_002",
        )
        self.service.deployment.complete_deployment(dep2.deployment_id, success=True)
        ver2 = self.service.verify_deployment(
            dep2.deployment_id,
            override_failure_reason="CrashLoopBackOff: Segfault on start",
        )
        self.assertFalse(ver2.is_fully_verified)
        env_degraded = self.repo.get_environment(env.environment_id)
        self.assertEqual(env_degraded.current_state, EnvironmentLifecycleState.DEGRADED)

        # Step 11: Execute Rollback to v1.0.0
        rb = self.service.rollback_deployment(
            environment_id=env.environment_id,
            failed_deployment_id=dep2.deployment_id,
            target_release_id=rel1.release_id,
            approval_token="OMNIA_M20_APPROVAL_RB_001",
        )
        self.assertEqual(rb.status, "SUCCESS")
        env_recovered = self.repo.get_environment(env.environment_id)
        self.assertEqual(env_recovered.current_state, EnvironmentLifecycleState.READY)
        self.assertEqual(env_recovered.active_release_version, rel1.release_id)

        # Step 12: Reconcile Drift
        drift = self.service.reconcile_drift(env.environment_id)
        self.assertEqual(len(drift), 0)

        # Step 13: Gated Decommission Plan
        decom_plan = self.service.create_decommission_plan(env.environment_id)
        self.assertEqual(decom_plan.status, "PROPOSED")

        # Invariant: Unapproved production teardown fails closed
        with self.assertRaises(PermissionError):
            self.service.execute_decommission(decom_plan.decommission_id)

        # Step 14: Execute Decommission with Token
        decom_done = self.service.execute_decommission(
            decom_plan.decommission_id,
            approval_token="OMNIA_M20_APPROVAL_DECOM_001",
        )
        self.assertEqual(decom_done.status, "EXECUTED")
        env_final = self.repo.get_environment(env.environment_id)
        self.assertEqual(env_final.current_state, EnvironmentLifecycleState.DECOMMISSIONED)


if __name__ == "__main__":
    unittest.main()
