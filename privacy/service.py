"""
privacy/service.py
PrivacyEngineeringOrchestrator:
Central unified facade for OMNIA Module 51 exposing cohesive end-to-end methods
for asset inventory, sensitive data discovery, classification, lineage tracking,
RoPA registry, consent management, verified deletion & legal holds, DSR fulfillment,
PIA/DPIA assessments, vendor/cross-border governance, and sealed reporting.
Singleton instance `privacy_service` provided.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

from privacy.models import (
    DataAsset, DataClassification, DiscoveryScan, LineageRecord,
    ProcessingActivity, ConsentRecord, RetentionPolicy, DeletionRequest,
    DSRRequest, PrivacyAssessment, AccessDisclosureLog, VendorProcessor,
    CrossBorderTransfer, PrivacyIncident, AIGovernanceConfig, PrivacyPostureReport
)
from privacy.persistence import PrivacyRepository
from privacy.inventory import EnterpriseDataInventory
from privacy.classifier import DataClassificationEngine
from privacy.discovery import SensitiveDataDiscoveryEngine
from privacy.lineage import DataLineageTracker
from privacy.processing_registry import ProcessingActivityRegistry
from privacy.consent import ConsentManager
from privacy.minimization import DataMinimizationEngine
from privacy.retention import RetentionLifecycleManager
from privacy.dsr_manager import DataSubjectRequestManager
from privacy.assessment import PrivacyAssessmentEngine
from privacy.access_governance import AccessGovernanceEngine
from privacy.vendor_governance import VendorGovernanceManager
from privacy.cross_border import CrossBorderTransferGovernor
from privacy.transformations import PrivacyTransformationEngine
from privacy.incident_manager import PrivacyIncidentManager
from privacy.ai_governance import AIPrivacyGovernor
from privacy.reporting import PrivacyReportingEngine

logger = logging.getLogger("omnia.privacy.service")


class PrivacyEngineeringOrchestrator:
    def __init__(self, db_path: str = "omnia.db"):
        self.repo = PrivacyRepository(db_path=db_path)
        self.inventory = EnterpriseDataInventory(self.repo)
        self.classifier = DataClassificationEngine(self.repo)
        self.discovery = SensitiveDataDiscoveryEngine(self.repo, self.classifier)
        self.lineage = DataLineageTracker(self.repo)
        self.processing_registry = ProcessingActivityRegistry(self.repo)
        self.consent = ConsentManager(self.repo)
        self.minimization = DataMinimizationEngine()
        self.retention = RetentionLifecycleManager(self.repo, self.lineage)
        self.dsr = DataSubjectRequestManager(self.repo, self.retention, self.inventory)
        self.assessment = PrivacyAssessmentEngine(self.repo)
        self.access = AccessGovernanceEngine(self.repo)
        self.vendor = VendorGovernanceManager(self.repo)
        self.cross_border = CrossBorderTransferGovernor(self.repo)
        self.transformer = PrivacyTransformationEngine()
        self.incident = PrivacyIncidentManager(self.repo)
        self.ai_governance = AIPrivacyGovernor(self.repo, self.transformer)
        self.reporting = PrivacyReportingEngine(self.repo)

    # --- Tool 1 Facade: Inventory & Classify ---
    def inventory_and_classify_asset(
        self,
        name: str,
        asset_type: str,
        storage_location: str,
        owner: str,
        residency_country: str = "US",
        fields: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[DataAsset, List[DataClassification]]:
        """Registers a data asset and classifies its schema fields, rolling up the asset's overall sensitivity tier."""
        asset = self.inventory.register_asset(
            name=name,
            asset_type=asset_type,
            storage_location=storage_location,
            owner=owner,
            residency_country=residency_country,
            metadata=metadata
        )

        classifications = []
        if fields:
            classifications = self.classifier.classify_schema(asset_id=asset.asset_id, fields=fields)
            self.inventory.recalculate_asset_sensitivity(asset.asset_id)
            asset = self.inventory.get_asset(asset.asset_id) or asset

        return asset, classifications

    # --- Tool 2 Facade: Sensitive Data Discovery ---
    def execute_discovery(
        self,
        target_scope: str,
        scanner_identity: str = "omnia_privacy_scanner",
        field_names: Optional[List[str]] = None,
        sample_payload: Optional[Dict[str, Any]] = None,
        asset_id: Optional[str] = None
    ) -> DiscoveryScan:
        """Executes authorized read-only sensitive data discovery without storing raw values."""
        return self.discovery.run_discovery_scan(
            target_scope=target_scope,
            scanner_identity=scanner_identity,
            field_names=field_names,
            sample_payload=sample_payload,
            asset_id=asset_id
        )

    # --- Tool 3 Facade: Processing & Consent ---
    def record_processing_and_consent(
        self,
        activity_name: str,
        purpose: str,
        lawful_basis: str,
        owner: str,
        data_categories: List[str],
        retention_schedule: str = "P3Y",
        is_approved: bool = True,
        subject_id: Optional[str] = None,
        consent_status: Optional[str] = None,
        policy_version: str = "1.0"
    ) -> Tuple[ProcessingActivity, Optional[ConsentRecord]]:
        """Registers a processing activity in RoPA and optionally records data subject consent."""
        activity = self.processing_registry.register_activity(
            name=activity_name,
            purpose=purpose,
            lawful_basis=lawful_basis,
            owner=owner,
            data_categories=data_categories,
            retention_schedule=retention_schedule,
            is_approved=is_approved
        )

        consent_rec = None
        if subject_id:
            c_status = (consent_status or "GRANTED").upper()
            if c_status == "WITHDRAWN":
                consent_rec = self.consent.withdraw_consent(subject_id=subject_id, purpose=purpose)
            else:
                consent_rec = self.consent.grant_consent(
                    subject_id=subject_id,
                    purpose=purpose,
                    policy_version=policy_version
                )

        return activity, consent_rec

    # --- Tool 4 Facade: Retention & Deletion ---
    def evaluate_retention_and_delete(
        self,
        asset_id: str,
        purpose: str,
        target_selector: str,
        requested_by: str,
        reason: str,
        approval_token: Optional[str] = None
    ) -> DeletionRequest:
        """Evaluates legal holds and orchestrates verified cascading deletion across stores."""
        return self.retention.orchestrate_deletion(
            asset_id=asset_id,
            target_selector=target_selector,
            reason=reason,
            requested_by=requested_by,
            approval_token=approval_token
        )

    # --- Tool 5 Facade: DSR Management ---
    def manage_dsr(
        self,
        subject_id: str,
        request_type: str,
        requester_email: str,
        action: str = "SUBMIT",
        verification_token: Optional[str] = None,
        approval_token: Optional[str] = None,
        dsr_id: Optional[str] = None
    ) -> DSRRequest:
        """Handles end-to-end data subject request lifecycle."""
        act = action.upper().strip()
        if act == "SUBMIT":
            return self.dsr.submit_request(
                subject_id=subject_id,
                request_type=request_type,
                requester_email=requester_email,
                verification_token=verification_token
            )
        elif act == "VERIFY":
            if not dsr_id:
                raise ValueError("dsr_id required for VERIFY action.")
            req = self.dsr.verify_requester(dsr_id=dsr_id, token=verification_token or "")
            if not req:
                raise ValueError("Verification failed: invalid token or dsr_id.")
            return req
        elif act in ("FULFILL", "EXECUTE"):
            if not dsr_id:
                raise ValueError("dsr_id required for FULFILL action.")
            return self.dsr.fulfill_request(
                dsr_id=dsr_id,
                approver=requester_email or "omnia_privacy_officer",
                approval_token=approval_token
            )
        else:
            raise ValueError(f"Unknown DSR action: {action}")

    # --- Tool 6 Facade: Report Generation ---
    def generate_posture_report(self, actor: str = "omnia_privacy_officer") -> PrivacyPostureReport:
        """Produces a cryptographically sealed privacy posture intelligence report."""
        return self.reporting.generate_posture_report(generated_by=actor)


# Global singleton instance
privacy_service = PrivacyEngineeringOrchestrator()
