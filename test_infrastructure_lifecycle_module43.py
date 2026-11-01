"""
OMNIA Module 43: Autonomous Infrastructure Provisioning & Environment Lifecycle Management
Unit Test Suite - test_infrastructure_lifecycle_module43.py
"""

import os
import unittest
import sqlite3
from typing import Dict, Any

from persistence.migrations import MIGRATION_V28
from infrastructure_lifecycle.models import (
    ProviderType,
    ProviderCapability,
    EnvironmentType,
    EnvironmentLifecycleState,
    DeploymentStrategy,
    DeploymentState,
    DriftType,
)
from infrastructure_lifecycle.persistence import InfrastructureRepository
from infrastructure_lifecycle.providers import (
    InfrastructureProviderRegistry,
    LocalSandboxProviderAdapter,
)
from infrastructure_lifecycle.blueprints import InfrastructureBlueprintEngine
from infrastructure_lifecycle.environments import EnvironmentLifecycleManager
from infrastructure_lifecycle.provisioning import ProvisioningEngine
from infrastructure_lifecycle.deployment import DeploymentOrchestrator
from infrastructure_lifecycle.validator import DeploymentValidator
from infrastructure_lifecycle.rollback import RollbackController
from infrastructure_lifecycle.reconciliation import InfrastructureReconciler
from infrastructure_lifecycle.cleanup import DecommissionEngine


class TestInfrastructureLifecycleModule43(unittest.TestCase):
    def setUp(self):
        import uuid
        self.test_db = f"test_infra_{uuid.uuid4().hex[:8]}.db"

        # Fast init using direct V28 migration script
        conn = sqlite3.connect(self.test_db)
        conn.executescript(MIGRATION_V28)
        conn.close()

        self.repo = InfrastructureRepository(self.test_db)
        self.registry = InfrastructureProviderRegistry(self.repo)
        self.adapter = LocalSandboxProviderAdapter("sandbox_main")
        self.registry.register_adapter(self.adapter)
        self.repo.save_provider(self.adapter.get_record())

        self.blueprints = InfrastructureBlueprintEngine(self.repo)
        self.environments = EnvironmentLifecycleManager(self.repo)
        self.provisioning = ProvisioningEngine(self.repo, self.registry, self.environments)
        self.deployment = DeploymentOrchestrator(self.repo)
        self.validator = DeploymentValidator(self.repo, self.registry)
        self.rollback = RollbackController(self.repo)
        self.reconciler = InfrastructureReconciler(self.repo, self.registry)
        self.cleanup = DecommissionEngine(self.repo, self.registry)

    def tearDown(self):
        try:
            if hasattr(self, "test_db") and os.path.exists(self.test_db):
                os.remove(self.test_db)
        except Exception:
            pass

    def test_provider_registration_and_capabilities(self):
        """Test provider adapter registration and capability checks."""
        adapter = self.registry.get_adapter("sandbox_main")
        self.assertIsNotNone(adapter)
        self.assertTrue(adapter.supports(ProviderCapability.PROVISION))
        self.assertTrue(adapter.supports(ProviderCapability.DECOMMISSION))

        # Check unsupported capability enforcement
        limited_adapter = LocalSandboxProviderAdapter(
            "read_only_prov",
            capabilities=[ProviderCapability.DISCOVERY, ProviderCapability.INSPECT],
        )
        self.assertFalse(limited_adapter.supports(ProviderCapability.PROVISION))
        with self.assertRaises(PermissionError):
            limited_adapter.provision_resource("test", "compute", {})

    def test_blueprint_validation_and_dependencies(self):
        """Test blueprint registration and structural validation."""
        bp = self.blueprints.register_blueprint(
            blueprint_id="bp_web",
            name="Web Service Blueprint",
            version="1.0.0",
            environment_type=EnvironmentType.STAGING,
            resource_definitions=[
                {"name": "db", "type": "DATABASE"},
                {"name": "api", "type": "PROCESS"},
            ],
            dependencies=["db"],
        )
        self.assertEqual(bp.blueprint_id, "bp_web")
        self.assertEqual(len(bp.resource_definitions), 2)

        # Duplicate resource names should be rejected
        with self.assertRaises(ValueError):
            self.blueprints.register_blueprint(
                blueprint_id="bp_broken",
                name="Broken",
                version="1.0.0",
                environment_type=EnvironmentType.STAGING,
                resource_definitions=[
                    {"name": "api", "type": "PROCESS"},
                    {"name": "api", "type": "PROCESS"},
                ],
            )

    def test_environment_state_machine_and_transitions(self):
        """Test environment lifecycle state machine and strict transition validation."""
        bp = self.blueprints.register_blueprint(
            blueprint_id="bp_env_test",
            name="Env Test BP",
            version="1.0.0",
            environment_type=EnvironmentType.STAGING,
            resource_definitions=[{"name": "svc", "type": "PROCESS"}],
        )
        env = self.environments.create_environment(
            name="Staging Env",
            environment_type=EnvironmentType.STAGING,
            provider_id="sandbox_main",
            blueprint_id="bp_env_test",
        )
        self.assertEqual(env.current_state, EnvironmentLifecycleState.REQUESTED)

        # Valid transition: REQUESTED -> PLANNED
        self.environments.transition_state(env.environment_id, EnvironmentLifecycleState.PLANNED)
        env = self.repo.get_environment(env.environment_id)
        self.assertEqual(env.current_state, EnvironmentLifecycleState.PLANNED)

        # Invalid transition: PLANNED -> READY (must undergo provisioning & validation)
        with self.assertRaises(ValueError):
            self.environments.transition_state(env.environment_id, EnvironmentLifecycleState.READY)

    def test_provisioning_execution_and_approval_gate(self):
        """Test provisioning planning, execution, and Module 20 approval gate for production."""
        bp = self.blueprints.register_blueprint(
            blueprint_id="bp_prod",
            name="Prod Architecture",
            version="1.0.0",
            environment_type=EnvironmentType.PRODUCTION,
            resource_definitions=[
                {"name": "db_cluster", "type": "DATABASE"},
                {"name": "app_server", "type": "PROCESS"},
            ],
            dependencies=["db_cluster"],
        )
        prod_env = self.environments.create_environment(
            name="Production Cluster",
            environment_type=EnvironmentType.PRODUCTION,
            provider_id="sandbox_main",
            blueprint_id="bp_prod",
        )
        plan = self.provisioning.create_provisioning_plan(prod_env.environment_id)
        self.assertTrue(plan.requires_approval)

        # Invariant: Unapproved production provisioning must fail closed
        with self.assertRaises(PermissionError):
            self.provisioning.execute_provisioning(plan.plan_id)

        # Approve with valid Module 20 human approval token
        exec_rec = self.provisioning.execute_provisioning(
            plan.plan_id,
            approval_token="OMNIA_M20_APPROVAL_PROD_123",
        )
        self.assertEqual(exec_rec.status, "SUCCESS")
        self.assertEqual(len(exec_rec.executed_actions), 2)

    def test_deployment_orchestration_and_multi_tier_validation(self):
        """Test rollout deployment and multi-tier independent proof before READY."""
        bp = self.blueprints.register_blueprint(
            blueprint_id="bp_qa",
            name="QA BP",
            version="1.0.0",
            environment_type=EnvironmentType.TESTING,
            resource_definitions=[{"name": "qa_worker", "type": "PROCESS"}],
        )
        env = self.environments.create_environment(
            name="QA Env",
            environment_type=EnvironmentType.TESTING,
            provider_id="sandbox_main",
            blueprint_id="bp_qa",
        )
        plan = self.provisioning.create_provisioning_plan(env.environment_id)
        self.provisioning.execute_provisioning(plan.plan_id)

        # Environment transitions to INITIALIZING/VALIDATING then READY
        self.environments.transition_state(env.environment_id, EnvironmentLifecycleState.READY)

        # Register release
        rel = self.deployment.register_release(
            application_name="core-service",
            version="1.0.0",
            artifact_uri="s3://artifacts/bundle.tar.gz",
        )
        dep = self.deployment.start_deployment(
            environment_id=env.environment_id,
            release_id=rel.release_id,
            strategy=DeploymentStrategy.DIRECT,
        )
        self.deployment.complete_deployment(
            deployment_id=dep.deployment_id,
            success=True,
        )

        # Verify deployment (passes independent 3 tiers)
        ver = self.validator.verify_deployment(dep.deployment_id)
        self.assertTrue(ver.is_fully_verified)
        refreshed_env = self.repo.get_environment(env.environment_id)
        self.assertEqual(refreshed_env.current_state, EnvironmentLifecycleState.READY)
        self.assertEqual(refreshed_env.active_release_version, rel.release_id)

    def test_deployment_verification_failure_and_rollback(self):
        """Test deployment verification failure triggering automated rollback."""
        bp = self.blueprints.register_blueprint(
            blueprint_id="bp_dev",
            name="Dev BP",
            version="1.0.0",
            environment_type=EnvironmentType.DEVELOPMENT,
            resource_definitions=[{"name": "dev_worker", "type": "PROCESS"}],
        )
        env = self.environments.create_environment(
            name="Dev Env",
            environment_type=EnvironmentType.DEVELOPMENT,
            provider_id="sandbox_main",
            blueprint_id="bp_dev",
        )
        plan = self.provisioning.create_provisioning_plan(env.environment_id)
        self.provisioning.execute_provisioning(plan.plan_id)
        self.environments.transition_state(env.environment_id, EnvironmentLifecycleState.READY)

        # Good deployment v1
        rel1 = self.deployment.register_release("app", "1.0.0", "uri1")
        dep1 = self.deployment.start_deployment(env.environment_id, rel1.release_id)
        self.deployment.complete_deployment(dep1.deployment_id, True)
        self.validator.verify_deployment(dep1.deployment_id)

        # Flawed deployment v2
        rel2 = self.deployment.register_release("app", "2.0.0", "uri2")
        dep2 = self.deployment.start_deployment(env.environment_id, rel2.release_id)
        self.deployment.complete_deployment(dep2.deployment_id, True)
        ver2 = self.validator.verify_deployment(
            dep2.deployment_id,
            override_failure_reason="Endpoint 500 CrashLoopBackOff",
        )
        self.assertFalse(ver2.is_fully_verified)

        # Rollback to v1
        rb = self.rollback.execute_rollback(
            environment_id=env.environment_id,
            failed_deployment_id=dep2.deployment_id,
            target_release_id=rel1.release_id,
        )
        self.assertEqual(rb.status, "SUCCESS")
        refreshed_env = self.repo.get_environment(env.environment_id)
        self.assertEqual(refreshed_env.current_state, EnvironmentLifecycleState.READY)
        self.assertEqual(refreshed_env.active_release_version, rel1.release_id)

    def test_drift_detection_and_decommissioning(self):
        """Test drift detection against blueprint and gated environment decommissioning."""
        bp = self.blueprints.register_blueprint(
            blueprint_id="bp_drift",
            name="Drift Blueprint",
            version="1.0.0",
            environment_type=EnvironmentType.STAGING,
            resource_definitions=[
                {"name": "web", "type": "PROCESS"},
                {"name": "cache", "type": "DATABASE"},
            ],
        )
        env = self.environments.create_environment(
            name="Drift Test Env",
            environment_type=EnvironmentType.STAGING,
            provider_id="sandbox_main",
            blueprint_id="bp_drift",
        )
        plan = self.provisioning.create_provisioning_plan(env.environment_id)
        self.provisioning.execute_provisioning(plan.plan_id)

        # Discover drift (resources exist from execute_provisioning)
        findings = self.reconciler.reconcile_environment(env.environment_id)
        self.assertEqual(len(findings), 0)

        # Decommission environment
        decom_plan = self.cleanup.create_decommission_plan(env.environment_id)
        decom_res = self.cleanup.execute_decommission(decom_plan.decommission_id)
        self.assertEqual(decom_res.status, "EXECUTED")

        refreshed_env = self.repo.get_environment(env.environment_id)
        self.assertEqual(refreshed_env.current_state, EnvironmentLifecycleState.DECOMMISSIONED)


if __name__ == "__main__":
    unittest.main()
