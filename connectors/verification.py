"""
Response Verification & Business Validation Engine for Omnia Module 26:
External Integration & Connector Gateway

Invariants:
1. HTTP 200 != Business Success.
2. Verification validates status code, response schema, and provider-specific business states.
3. Network timeouts or lost responses during write operations are categorized as UNCERTAIN.
"""

import logging
from typing import Dict, Any, Optional, Tuple

from connectors.models import VerificationStatus, ConnectorOperation, OperationType

logger = logging.getLogger("Omnia.Connectors.Verification")


class ResponseVerifier:
    """Evaluates whether an external response represents true business success."""

    @staticmethod
    def verify_response(
        operation: ConnectorOperation,
        status_code: int,
        response_body: Any,
        timed_out: bool = False
    ) -> Tuple[VerificationStatus, Dict[str, Any], Optional[str]]:
        """
        Validates response, returning (VerificationStatus, details_dict, error_message).
        """
        details: Dict[str, Any] = {
            "status_code": status_code,
            "operation_id": operation.operation_id
        }

        # 1. Timeout during write operation creates UNCERTAIN state
        if timed_out:
            if operation.operation_type in (OperationType.WRITE, OperationType.ACTION):
                details["reason"] = "WRITE_TIMEOUT_EXTERNAL_STATE_UNCERTAIN"
                return VerificationStatus.UNCERTAIN, details, "Operation timed out during write; external state is UNCERTAIN."
            else:
                details["reason"] = "READ_TIMEOUT"
                return VerificationStatus.FAILED, details, "Read operation timed out."

        # 2. HTTP Status Code validation
        if not (200 <= status_code < 300):
            details["reason"] = f"HTTP_ERROR_STATUS_{status_code}"
            return VerificationStatus.FAILED, details, f"External server returned error status {status_code}."

        # 3. Provider Business Logic Inspection (GraphQL errors, Slack ok: false, Stripe error)
        if isinstance(response_body, dict):
            # Slack-style: {"ok": false, "error": "channel_not_found"}
            if response_body.get("ok") is False:
                err = response_body.get("error", "Unknown provider error")
                details["provider_error"] = err
                return VerificationStatus.FAILED, details, f"Provider reported business failure: {err}"

            # GraphQL-style: {"errors": [...]}
            if "errors" in response_body and isinstance(response_body["errors"], list) and len(response_body["errors"]) > 0:
                first_err = response_body["errors"][0]
                err_msg = first_err.get("message", "GraphQL error") if isinstance(first_err, dict) else str(first_err)
                details["graphql_errors"] = response_body["errors"]
                return VerificationStatus.FAILED, details, f"GraphQL query failed with errors: {err_msg}"

            # Stripe/Generic payment style: {"status": "failed" / "requires_payment_method"}
            if "status" in response_body:
                b_status = str(response_body["status"]).lower()
                if b_status in ("failed", "canceled", "rejected", "declined"):
                    details["business_status"] = b_status
                    return VerificationStatus.FAILED, details, f"Resource status indicates failure: {b_status}"

        # 4. Schema Requirement Verification
        output_schema = operation.output_schema
        if output_schema and isinstance(output_schema, dict) and isinstance(response_body, dict):
            req_fields = output_schema.get("required", [])
            missing = [f for f in req_fields if f not in response_body]
            if missing:
                details["missing_schema_fields"] = missing
                return VerificationStatus.FAILED, details, f"Response missing required schema fields: {missing}"

        # Success verified
        details["verified"] = True
        return VerificationStatus.VERIFIED, details, None

    def verify(
        self,
        provider_id: str,
        http_status: int,
        headers: Dict[str, str],
        parsed_body: Any,
        is_write_op: bool = False,
        timed_out: bool = False
    ) -> Tuple[VerificationStatus, str]:
        """Convenience method for diagnostic checks and quick evaluation."""
        from connectors.models import ConnectorOperation, OperationType
        op_type = OperationType.WRITE if is_write_op else OperationType.READ
        op = ConnectorOperation(
            operation_id=f"{provider_id}.check",
            name="Verification Check",
            operation_type=op_type,
            path="/"
        )
        status, details, err = self.verify_response(op, http_status, parsed_body, timed_out=timed_out)
        reason = err or details.get("reason", "OK")
        return status, reason


response_verifier = ResponseVerifier()
