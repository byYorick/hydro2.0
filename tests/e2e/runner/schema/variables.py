"""
Variable resolution and expression evaluation for E2E tests.
"""

import re
import logging
import os
from typing import Dict, Any, Optional, List, Set
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class VariableResolver:
    """Resolves variables and expressions in YAML scenarios."""

    def __init__(self, context: Optional[Dict[str, Any]] = None):
        self.context = context or {}

    def resolve_variables(self, value: Any, required_vars: Optional[List[str]] = None) -> Any:
        """
        Resolve variables in value using Jinja2-like syntax.

        Supports:
        - ${variable_name}
        - ${variable_name.subfield}
        - ${variable_name[index]}
        - Nested structures

        Args:
            value: Value to resolve variables in
            required_vars: List of variable names that must be present

        Returns:
            Value with resolved variables
        """
        if isinstance(value, str):
            return self._resolve_string_variables(value, required_vars)
        elif isinstance(value, dict):
            resolved = {}
            for k, v in value.items():
                resolved[k] = self.resolve_variables(v, required_vars)
            logger.info(f"VariableResolver: resolved dict {value} -> {resolved}, context has zone_id: {'zone_id' in self.context}, node_id: {'node_id' in self.context}")
            return resolved
        elif isinstance(value, list):
            return [self.resolve_variables(item, required_vars) for item in value]
        else:
            return value

    def _resolve_string_variables(self, text: str, required_vars: Optional[List[str]] = None) -> Any:
        """Resolve variables in a string value."""
        # Pattern for ${variable} or ${variable.subfield} or ${variable[index]}
        pattern = r'\$\{([^}]+)\}'

        def replace_var(match):
            var_expr = match.group(1)
            try:
                value = self._resolve_variable_expression(var_expr)
                logger.info(f"VariableResolver: resolving '{var_expr}' -> {value}, context has it: {var_expr in self.context}")
                if required_vars and var_expr in required_vars and value is None:
                    raise ValueError(f"Required variable '{var_expr}' is not set")
                return str(value) if value is not None else ""
            except Exception as e:
                logger.error(f"Failed to resolve variable '{var_expr}': {e}")
                raise

        # Replace all variable references
        result = re.sub(pattern, replace_var, text)

        # Try to convert to appropriate type if it looks like a number or boolean
        return self._convert_string_value(result)

    def _resolve_variable_expression(self, expr: str) -> Any:
        """Resolve a variable expression like 'zone_id' or 'response.data[0].id'."""
        parts = expr.split('.')

        # Start with the first part as variable name
        current = self.context.get(parts[0])
        logger.info(f"VariableResolver: looking for '{expr}', parts[0]='{parts[0]}', found in context: {current is not None}, context keys: {list(self.context.keys())[:10]}")
        if current is None:
            # Try to find in context with different naming
            current = self._find_variable_fallback(parts[0])
        if current is None:
            env_value = os.getenv(parts[0])
            if env_value is not None:
                current = env_value
        if current is None:
            return None

        # Navigate through the path
        for part in parts[1:]:
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
        elif hasattr(obj, '__getitem__') and isinstance(obj, (list, tuple)):
            try:
                index = int(key)
                return obj[index] if 0 <= index < len(obj) else None
            except (ValueError, TypeError):
                pass
        return None

    def _find_variable_fallback(self, var_name: str) -> Any:
        """Fallback variable resolution for common patterns."""
        # Try different naming conventions
        candidates = [
            var_name,
            var_name.replace('_', '-'),
            var_name.replace('-', '_'),
            f"test_{var_name}",
            f"{var_name}_id",
        ]

        for candidate in candidates:
            if candidate in self.context:
                return self.context[candidate]

        return None

    def _convert_string_value(self, value: str) -> Any:
        """Convert string to appropriate type if possible."""
        # Don't convert if it still contains variable references
        if '${' in value:
            return value

        # Try boolean
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'

        # Try integer
        try:
            return int(value)
        except ValueError:
            pass

        # Try float
        try:
            return float(value)
        except ValueError:
            pass

        return value

    def validate_critical_params(self, params: Dict[str, Any]):
        """
        Validate that critical parameters don't contain dangerous values.

        Args:
            params: Parameters to validate

        Raises:
            ValueError: If dangerous parameters found
        """
        dangerous_patterns = [
            r';\s*DROP',  # SQL injection
            r';\s*DELETE',
            r';\s*UPDATE',
            r';\s*INSERT',
            r'union\s+select',  # SQL injection
            r'--',  # SQL comments
            r'/\*.*\*/',  # SQL comments
        ]

        def check_value(value: Any, path: str = ""):
            if isinstance(value, str):
                for pattern in dangerous_patterns:
                    if re.search(pattern, value, re.IGNORECASE):
                        raise ValueError(f"Dangerous SQL pattern detected in {path}: {pattern}")
            elif isinstance(value, dict):
                for k, v in value.items():
                    check_value(v, f"{path}.{k}" if path else k)
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    check_value(item, f"{path}[{i}]")

        check_value(params)
