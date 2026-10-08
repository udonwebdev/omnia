import re
import logging
from typing import Dict, Any, List, Tuple, Optional
from config.models import ConfigSchema, ConfigType, RuntimeMutability

logger = logging.getLogger("Omnia.Config.Validation")

SECRET_REF_PATTERN = re.compile(r"^secret://[a-zA-Z0-9_\-\.]+(/[a-zA-Z0-9_\-\.]+)+$")

class ConfigValidator:
    """Validates configuration keys, values, secret references, and cross-key dependencies."""

    @staticmethod
    def validate_value(schema: ConfigSchema, value: Any) -> Tuple[bool, Optional[str]]:
        """Validates a single configuration value against its schema definition."""
        if value is None:
            return False, f"Value for '{schema.key}' cannot be None."

        # 0. Disallow raw secrets in non-secret ref keys
        if not schema.is_secret and schema.data_type != ConfigType.SECRET_REF:
            if isinstance(value, str) and (value.startswith("sk-") or value.startswith("ghp_") or "password" in schema.key.lower()):
                return False, f"Raw sensitive secret detected in non-secret config key '{schema.key}'. Use secret:// reference."

        # 1. Type validation
        if schema.data_type == ConfigType.STRING:
            if not isinstance(value, str):
                return False, f"Expected STRING for '{schema.key}', got {type(value).__name__}."

        elif schema.data_type == ConfigType.INTEGER:
            if not isinstance(value, int) or isinstance(value, bool):
                return False, f"Expected INTEGER for '{schema.key}', got {type(value).__name__}."

        elif schema.data_type == ConfigType.FLOAT:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return False, f"Expected FLOAT/NUMBER for '{schema.key}', got {type(value).__name__}."

        elif schema.data_type == ConfigType.BOOLEAN:
            if not isinstance(value, bool):
                return False, f"Expected BOOLEAN for '{schema.key}', got {type(value).__name__}."

        elif schema.data_type == ConfigType.ENUM:
            if not isinstance(value, str):
                return False, f"Expected string ENUM for '{schema.key}', got {type(value).__name__}."
            if schema.allowed_values and value not in schema.allowed_values:
                return False, f"Value '{value}' for '{schema.key}' not in allowed values: {schema.allowed_values}."

        elif schema.data_type == ConfigType.SECRET_REF:
            if not isinstance(value, str):
                return False, f"Expected string URI for secret reference '{schema.key}'."
            if not SECRET_REF_PATTERN.match(value):
                return False, (
                    f"Invalid secret reference format for '{schema.key}'. "
                    f"Must match 'secret://<provider>/<key>' (e.g. 'secret://vault/api_key')."
                )

        elif schema.data_type == ConfigType.DURATION:
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                return False, f"Expected non-negative numeric duration for '{schema.key}'."

        elif schema.data_type == ConfigType.PERCENTAGE:
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not (0.0 <= value <= 100.0 or 0.0 <= value <= 1.0):
                return False, f"Expected percentage [0.0 - 100.0] or [0.0 - 1.0] for '{schema.key}'."

        elif schema.data_type == ConfigType.LIST:
            if not isinstance(value, list):
                return False, f"Expected LIST for '{schema.key}', got {type(value).__name__}."

        elif schema.data_type == ConfigType.JSON:
            if not isinstance(value, (dict, list)):
                return False, f"Expected JSON structure for '{schema.key}'."

        # 2. Numerical bounds check
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if schema.min_value is not None and value < schema.min_value:
                return False, f"Value {value} for '{schema.key}' is below minimum {schema.min_value}."
            if schema.max_value is not None and value > schema.max_value:
                return False, f"Value {value} for '{schema.key}' exceeds maximum {schema.max_value}."

        # 3. Disallow raw secrets in non-secret ref keys
        if not schema.is_secret and schema.data_type != ConfigType.SECRET_REF:
            if isinstance(value, str) and (value.startswith("sk-") or value.startswith("ghp_") or "password" in schema.key.lower()):
                return False, f"Raw sensitive secret detected in non-secret config key '{schema.key}'. Use secret:// reference."

        return True, None

    @classmethod
    def validate_configuration(
        cls,
        values: Dict[str, Any],
        schemas: Dict[str, ConfigSchema],
        allow_unknown_keys: bool = False
    ) -> Tuple[bool, List[str]]:
        """Validates an entire configuration set against registered schemas and cross-key dependencies."""
        errors: List[str] = []

        # Validate individual values
        for key, val in values.items():
            if key not in schemas:
                if not allow_unknown_keys:
                    errors.append(f"UNKNOWN_KEY: Configuration key '{key}' is not defined in schema registry.")
                continue

            schema = schemas[key]
            ok, err = cls.validate_value(schema, val)
            if not ok and err:
                errors.append(err)

        # Cross-key dependency and relational rules
        if "coordination.heartbeat_period_sec" in values and "coordination.lease_ttl_sec" in values:
            hb = values["coordination.heartbeat_period_sec"]
            ttl = values["coordination.lease_ttl_sec"]
            if hb >= ttl:
                errors.append(
                    f"DEPENDENCY_ERROR: 'coordination.heartbeat_period_sec' ({hb}s) "
                    f"must be strictly less than 'coordination.lease_ttl_sec' ({ttl}s)."
                )

        if "browser.viewport_width" in values and "browser.viewport_height" in values:
            w = values["browser.viewport_width"]
            h = values["browser.viewport_height"]
            if w <= 0 or h <= 0:
                errors.append("DEPENDENCY_ERROR: Browser viewport dimensions must be positive integers.")

        return (len(errors) == 0), errors

    @classmethod
    def check_node_compatibility(
        cls,
        values: Dict[str, Any],
        schemas: Dict[str, ConfigSchema],
        node_capabilities: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """Verifies whether target node capabilities satisfy the proposed configuration."""
        incompatibilities: List[str] = []

        # Example: if browser.headless is False, node must have GUI display capability
        if values.get("browser.headless") is False:
            has_display = node_capabilities.get("has_display", True)
            if not has_display:
                incompatibilities.append(
                    "NODE_INCOMPATIBLE: 'browser.headless' is False, but node has no graphical display capability."
                )

        # High capture FPS requires sufficient CPU / vision acceleration
        fps = values.get("vision.capture_fps")
        if fps and fps > 30:
            low_power = node_capabilities.get("low_power_device", False)
            if low_power:
                incompatibilities.append(
                    f"NODE_INCOMPATIBLE: vision.capture_fps={fps} exceeds recommended limits for low-power device."
                )

        return (len(incompatibilities) == 0), incompatibilities
