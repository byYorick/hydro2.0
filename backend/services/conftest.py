"""
Test collection guard for non-module collectors.

Some directories (e.g., with dashes in the name) are collected as generic
collectors without `.obj`, while pytest-asyncio expects this attribute.
We ensure it exists to avoid internal collection errors.
"""
import pytest
from _pytest.python import Package
from pathlib import Path
import sys
import importlib

# Ensure backend/services is on sys.path for all tests (shared common package).
BASE_DIR = Path(__file__).resolve().parent
base_str = str(BASE_DIR)
if base_str not in sys.path:
    sys.path.insert(0, base_str)
# Preload common package to avoid resolving to non-package modules.
importlib.import_module("common")


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_collectstart(collector):
    if "obj" not in collector.__dict__:
        try:
            object.__setattr__(collector, "obj", None)
        except Exception:
            pass
    yield

# Ensure Package collectors always have an 'obj' attribute to avoid plugin crashes.
if not hasattr(Package, "obj"):
    Package.obj = None
