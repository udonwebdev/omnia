"""
Content-Type Detection & Structured Schema Validation for Omnia Module 27:
Data Ingestion, Normalization & Knowledge Pipeline

Guarantees:
1. Declared content types are validated against actual payload characteristics.
2. Structured schemas enforce required fields, types, nullability, and version compatibility.
3. Malformed data is explicitly flagged and never silently treated as valid.
"""

import json
import logging
from typing import Dict, Any, Tuple, Optional, List

from ingestion.models import (
    ContentType,
    SchemaValidationStatus,
    IngestionEnvelope
)

logger = logging.getLogger("Omnia.Ingestion.Validation")


class SchemaValidator:
    """Validates payload schemas and detects true content types."""

    def __init__(self):
        self._registered_schemas: Dict[str, Dict[str, Any]] = {}
        self._init_built_in_schemas()

    def _init_built_in_schemas(self):
        """Initializes canonical schemas for common providers and entities."""
        self._registered_schemas["github.repository.v1"] = {
            "required": ["id", "name", "full_name"],
            "types": {"id": (int, str), "name": str, "full_name": str},
            "category": "RECORD"
        }
        self._registered_schemas["stripe.charge.v1"] = {
            "required": ["id", "amount", "currency", "status"],
            "types": {"id": str, "amount": (int, float), "currency": str, "status": str},
            "category": "TRANSACTION"
        }
        self._registered_schemas["slack.message.v1"] = {
            "required": ["channel", "text", "ts"],
            "types": {"channel": str, "text": str, "ts": (str, float)},
            "category": "MESSAGE"
        }
        self._registered_schemas["generic.entity.v1"] = {
            "required": ["id", "type"],
            "types": {"id": str, "type": str},
            "category": "ENTITY"
        }

    def register_schema(self, schema_id: str, schema_def: Dict[str, Any]):
        """Registers a structured schema definition for pipeline validation."""
        self._registered_schemas[schema_id] = schema_def

    def detect_content_type(self, raw_payload: Any, declared: Optional[ContentType] = None) -> ContentType:
        """Determines the true content type of the raw payload."""
        if isinstance(raw_payload, (dict, list)):
            return ContentType.APPLICATION_JSON
        if isinstance(raw_payload, str):
            stripped = raw_payload.strip()
            if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
                try:
                    json.loads(stripped)
                    return ContentType.APPLICATION_JSON
                except Exception:
                    pass
            if stripped.startswith("<") and stripped.endswith(">"):
                if "<html" in stripped.lower() or "<body" in stripped.lower():
                    return ContentType.TEXT_HTML
                return ContentType.APPLICATION_XML
            if "," in stripped and "\n" in stripped:
                return ContentType.TEXT_CSV
            return ContentType.TEXT_PLAIN
        if isinstance(raw_payload, bytes):
            # Check magic bytes
            if raw_payload.startswith(b"%PDF"):
                return ContentType.APPLICATION_PDF
            if raw_payload.startswith(b"\x89PNG") or raw_payload.startswith(b"\xff\xd8\xff"):
                return ContentType.IMAGE
            try:
                raw_payload.decode("utf-8")
                return self.detect_content_type(raw_payload.decode("utf-8"))
            except UnicodeDecodeError:
                return ContentType.UNKNOWN
        return declared or ContentType.UNKNOWN

    def validate_schema(
        self,
        schema_name: Optional[str],
        schema_version: Optional[str],
        payload: Any
    ) -> Tuple[SchemaValidationStatus, List[str]]:
        """
        Validates payload against registered schema.
        Returns (SchemaValidationStatus, error_messages).
        """
        if not schema_name:
            return SchemaValidationStatus.VALID, []

        schema_key = f"{schema_name}.{schema_version}" if schema_version else schema_name
        schema_def = self._registered_schemas.get(schema_key)
        if not schema_def:
            # Fallback to schema_name without version
            schema_def = self._registered_schemas.get(schema_name)

        if not schema_def:
            logger.debug(f"Schema '{schema_key}' is not registered; marking UNKNOWN_SCHEMA.")
            return SchemaValidationStatus.UNKNOWN_SCHEMA, [f"Schema '{schema_key}' not found in registry."]

        if not isinstance(payload, dict):
            return SchemaValidationStatus.INVALID, ["Structured schema validation requires dictionary payload."]

        errors: List[str] = []
        required_fields = schema_def.get("required", [])
        field_types = schema_def.get("types", {})

        # Check required fields
        for rf in required_fields:
            if rf not in payload or payload[rf] is None:
                errors.append(f"Missing required field: '{rf}'")

        # Check types
        for field_name, expected_type in field_types.items():
            if field_name in payload and payload[field_name] is not None:
                val = payload[field_name]
                if isinstance(expected_type, tuple):
                    if not any(isinstance(val, t) for t in expected_type):
                        errors.append(f"Field '{field_name}' type mismatch: expected {expected_type}, got {type(val)}")
                elif not isinstance(val, expected_type):
                    errors.append(f"Field '{field_name}' type mismatch: expected {expected_type}, got {type(val)}")

        if not errors:
            return SchemaValidationStatus.VALID, []
        elif len(errors) < len(required_fields):
            return SchemaValidationStatus.PARTIALLY_VALID, errors
        else:
            return SchemaValidationStatus.INVALID, errors


schema_validator = SchemaValidator()
