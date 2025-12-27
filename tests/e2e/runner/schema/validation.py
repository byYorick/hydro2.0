"""
YAML schema validation and assertion processing for E2E tests.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class SchemaValidator:
    """Validates YAML scenarios and processes assertions."""

    def __init__(self, context: Optional[Dict[str, Any]] = None):
        self.context = context or {}

    def extract_json_path(self, obj: Any, path: Optional[str]) -> Any:
        """
        Extract value from nested object using dot notation.

        Args:
            obj: Object to extract from
            path: Path like "data.items[0].name"

        Returns:
            Extracted value or None
        """
        if path is None or obj is None:
            return obj

        parts = path.split('.')
        current = obj

        for part in parts:
            if current is None:
                return None

            # Handle array indexing [index]
            if '[' in part and ']' in part:
                base_part, index_part = part.split('[', 1)
                index_str = index_part.rstrip(']')

                # Navigate to base part first
                if base_part:
                    current = self._get_attr_or_key(current, base_part)

                # Then get array element
                if current is not None and isinstance(current, list):
                    try:
                        index = int(index_str)
                        current = current[index] if 0 <= index < len(current) else None
                    except (ValueError, IndexError):
                        return None
                else:
                    return None
            else:
                current = self._get_attr_or_key(current, part)

        return current

    def _get_attr_or_key(self, obj: Any, key: str) -> Any:
        """Get attribute or dict key from object."""
        if isinstance(obj, dict):
            return obj.get(key)
        elif hasattr(obj, key):
            return getattr(obj, key)
        return None

    def assert_row_expected(self, row: Dict[str, Any], expected_rules: List[Dict[str, Any]]):
        """
        Assert that database row matches expected rules.

        Args:
            row: Database row to check
            expected_rules: List of assertion rules

        Raises:
            AssertionError: If any rule fails
        """
        for rule in expected_rules:
            field = rule.get("field")
            operator = rule.get("operator")
            expected_value = rule.get("value")
            optional = rule.get("optional", False)

            if field == "length":
                actual = len(row) if row is not None else 0
            else:
                actual = row.get(field) if isinstance(row, dict) and field else None

            try:
                self._check_operator(actual, operator, expected_value, field)
            except AssertionError:
                if not optional:
                    raise

    def _check_operator(self, actual: Any, operator: str, expected: Any, field: Optional[str]):
        """Check assertion operator."""
        field_desc = f"field '{field}'" if field else "value"

        if operator == "equals":
            if str(actual) != str(expected):
                raise AssertionError(f"Expected {field_desc} = {expected}, got {actual}")
        elif operator == "is_not_null":
            if actual is None:
                raise AssertionError(f"Expected {field_desc} to be not null")
        elif operator == "greater_than":
            if not (float(actual) > float(expected)):
                raise AssertionError(f"Expected {field_desc} > {expected}, got {actual}")
        elif operator == "greater_than_or_equal":
            if not (float(actual) >= float(expected)):
                raise AssertionError(f"Expected {field_desc} >= {expected}, got {actual}")
        elif operator == "less_than":
            if not (float(actual) < float(expected)):
                raise AssertionError(f"Expected {field_desc} < {expected}, got {actual}")
        elif operator == "in":
            if actual not in expected:
                raise AssertionError(f"Expected {field_desc} in {expected}, got {actual}")
        elif operator == "is_null":
            if actual is not None:
                raise AssertionError(f"Expected {field_desc} to be null, got {actual}")
        else:
            raise AssertionError(f"Unsupported operator: {operator}")

    def auto_extract_ids_from_api_response(self, path: str, response: Any) -> Dict[str, Any]:
        """
        Auto-extract common IDs from API responses and set them in context.

        Args:
            path: Response path (e.g., "zones/1", "nodes/test-node")
            response: API response data

        Returns:
            Dict of extracted IDs
        """
        extracted = {}

        # Extract from response data
        if isinstance(response, dict) and "data" in response:
            data = response["data"]

            # Single object response
            if isinstance(data, dict):
                if "id" in data:
                    resource_type = path.split('/')[0].rstrip('s')  # zones -> zone
                    extracted[f"{resource_type}_id"] = data["id"]
                    extracted["id"] = data["id"]  # Also set generic id

                    # Special cases
                    if resource_type == "node" and "zone_id" in data:
                        extracted["zone_id"] = data["zone_id"]
                    if resource_type == "zone" and "greenhouse_id" in data:
                        extracted["greenhouse_id"] = data["greenhouse_id"]

            # List response - take first item
            elif isinstance(data, list) and len(data) > 0:
                first_item = data[0]
                if isinstance(first_item, dict) and "id" in first_item:
                    resource_type = path.split('/')[0].rstrip('s')
                    extracted[f"{resource_type}_id"] = first_item["id"]
                    extracted["id"] = first_item["id"]

        return extracted

    def validate_ws_channel_name(self, channel: str):
        """
        Validate WebSocket channel name format.

        Args:
            channel: Channel name to validate

        Raises:
            ValueError: If channel name is invalid
        """
        if not channel:
            raise ValueError("Channel name cannot be empty")

        # Basic validation - should start with known prefixes
        valid_prefixes = [
            "private-hydro.",
            "presence-hydro.",
            "public-hydro.",
            "private-App.",
        ]

        if not any(channel.startswith(prefix) for prefix in valid_prefixes):
            logger.warning(f"Channel '{channel}' doesn't start with known prefix")

        # Check for basic format
        if ".." in channel or channel.startswith(".") or channel.endswith("."):
            raise ValueError(f"Invalid channel name format: {channel}")
