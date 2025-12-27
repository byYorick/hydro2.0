"""
Schema validation and variable resolution for E2E tests.
"""

from .validation import SchemaValidator
from .variables import VariableResolver

__all__ = ['SchemaValidator', 'VariableResolver']
