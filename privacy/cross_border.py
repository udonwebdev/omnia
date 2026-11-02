"""
privacy/cross_border.py
Cross-Border Data Transfer Governor:
Validates international data transfers against territorial adequacy decisions,
standard contractual clauses (SCCs), and binding corporate rules (BCRs),
flagging unapproved or high-risk transfers.
"""

import uuid
import time
import logging
from typing import List, Dict, Any, Optional, Tuple, Set

from privacy.models import CrossBorderTransfer, TransferMechanism
from privacy.persistence import PrivacyRepository

logger = logging.getLogger("omnia.privacy.cross_border")


class CrossBorderTransferGovernor:
    # Recognized jurisdictions with European Commission adequacy decisions
    ADEQUATE_COUNTRIES: Set[str] = {
        "EEA", "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
        "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI",
        "ES", "SE", "IS", "LI", "NO", "CH", "GB", "UK", "CA", "JP", "NZ", "KR", "IL"
    }

    def __init__(self, repo: PrivacyRepository):
        self.repo = repo

    def register_transfer(
        self,
        source_country: str,
        dest_country: str,
        recipient: str,
        purpose: str,
        transfer_mechanism: str = "STANDARD_CONTRACTUAL_CLAUSES",
        is_approved: bool = False,
        transfer_id: Optional[str] = None
    ) -> CrossBorderTransfer:
        """Registers a cross-border data transfer channel."""
        tid = transfer_id or f"cbt_{uuid.uuid4().hex[:12]}"
        now = time.time()

        mech = TransferMechanism(transfer_mechanism.upper()) if transfer_mechanism.upper() in TransferMechanism._value2member_map_ else TransferMechanism.STANDARD_CONTRACTUAL_CLAUSES

        # Auto-approve if both countries are within adequate jurisdictions
        src = source_country.upper()
        dst = dest_country.upper()
        if src in self.ADEQUATE_COUNTRIES and dst in self.ADEQUATE_COUNTRIES:
            is_approved = True
            mech = TransferMechanism.ADEQUACY_DECISION

        transfer = CrossBorderTransfer(
            transfer_id=tid,
            source_country=src,
            dest_country=dst,
            recipient=recipient,
            purpose=purpose,
            transfer_mechanism=mech,
            is_approved=is_approved,
            reviewed_at=now
        )
        saved = self.repo.save_cross_border_transfer(transfer)
        self.repo.log_audit("CROSS_BORDER_TRANSFER_REGISTERED", "compliance", {
            "transfer_id": tid,
            "source": src,
            "dest": dst,
            "mechanism": mech.value,
            "approved": is_approved
        })
        logger.info(f"Cross-border transfer registered: {tid} ({src} -> {dst}, approved={is_approved})")
        return saved

    def validate_transfer(
        self,
        source_country: str,
        dest_country: str,
        transfer_mechanism: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Validates whether a proposed cross-border transfer complies with transfer safeguards."""
        src = source_country.upper()
        dst = dest_country.upper()

        if src == dst:
            return True, "Domestic transfer; no cross-border mechanism required."

        if src in self.ADEQUATE_COUNTRIES and dst in self.ADEQUATE_COUNTRIES:
            return True, f"Adequacy decision applies between {src} and {dst}."

        mech = transfer_mechanism.upper() if transfer_mechanism else ""
        if mech in ("STANDARD_CONTRACTUAL_CLAUSES", "BINDING_CORPORATE_RULES"):
            return True, f"Valid transfer safeguard ({mech}) established."

        return False, f"TRANSFER_RESTRICTED: Transfer from {src} to {dst} lacks an adequacy decision or valid SCC/BCR mechanism."
