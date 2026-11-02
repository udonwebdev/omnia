"""
privacy/vendor_governance.py
Third-Party Vendor & Subprocessor Governance Manager:
Tracks Data Processing Agreements (DPAs), subprocessor trees, vendor residency,
and evaluates third-party supply chain privacy compliance.
"""

import uuid
import time
import logging
from typing import List, Dict, Any, Optional

from privacy.models import VendorProcessor
from privacy.persistence import PrivacyRepository

logger = logging.getLogger("omnia.privacy.vendor_governance")


class VendorGovernanceManager:
    def __init__(self, repo: PrivacyRepository):
        self.repo = repo

    def register_vendor(
        self,
        name: str,
        service_type: str,
        dpa_status: str = "SIGNED",
        residency: str = "US",
        subprocessors: Optional[List[str]] = None,
        assessment_status: str = "APPROVED",
        vendor_id: Optional[str] = None
    ) -> VendorProcessor:
        """Registers a third-party processor or cloud vendor."""
        vid = vendor_id or f"vnd_{uuid.uuid4().hex[:12]}"
        now = time.time()

        vendor = VendorProcessor(
            vendor_id=vid,
            name=name,
            service_type=service_type,
            dpa_status=dpa_status.upper(),
            residency=residency.upper(),
            subprocessors=subprocessors or [],
            assessment_status=assessment_status.upper(),
            updated_at=now
        )
        saved = self.repo.save_vendor(vendor)
        self.repo.log_audit("VENDOR_REGISTERED", "procurement", {
            "vendor_id": vid,
            "name": name,
            "dpa_status": dpa_status
        })
        logger.info(f"Vendor registered: {vid} ({name}, dpa={dpa_status})")
        return saved

    def update_dpa_status(self, vendor_id: str, dpa_status: str) -> Optional[VendorProcessor]:
        """Updates DPA status (SIGNED, PENDING, EXPIRED, NONE)."""
        vendor = self.repo.get_vendor(vendor_id)
        if not vendor:
            return None
        vendor.dpa_status = dpa_status.upper()
        vendor.updated_at = time.time()
        saved = self.repo.save_vendor(vendor)
        self.repo.log_audit("VENDOR_DPA_UPDATED", "compliance", {"vendor_id": vendor_id, "dpa_status": dpa_status})
        return saved

    def evaluate_vendor_compliance(self, vendor_id: str) -> Dict[str, Any]:
        """Evaluates whether data transfer to a vendor is legally compliant."""
        vendor = self.repo.get_vendor(vendor_id)
        if not vendor:
            return {"compliant": False, "reason": "VENDOR_NOT_FOUND"}

        is_dpa_valid = vendor.dpa_status == "SIGNED"
        is_assessed = vendor.assessment_status in ("APPROVED", "ASSESSED")

        findings = []
        if not is_dpa_valid:
            findings.append(f"DPA is '{vendor.dpa_status}'; must be 'SIGNED' before processing personal data.")
        if not is_assessed:
            findings.append(f"Vendor assessment is '{vendor.assessment_status}'; requires approval.")

        return {
            "vendor_id": vendor.vendor_id,
            "name": vendor.name,
            "compliant": is_dpa_valid and is_assessed,
            "dpa_status": vendor.dpa_status,
            "residency": vendor.residency,
            "subprocessors_count": len(vendor.subprocessors),
            "findings": findings
        }
