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

# Module name collisions across services (main/models/utils/app/telemetry_processing).
AMBIGUOUS_MODULES = {
    "main",
    "models",
    "app",
    "utils",
    "telemetry_processing",
    "command_routes",
    "command_service",
    "ingest_routes",
    "system_routes",
    "calibration",
}
SERVICE_MODULES: dict[str, dict[str, object]] = {}


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _get_service_root(path: Path) -> Path | None:
    try:
        rel = path.resolve().relative_to(BASE_DIR)
    except ValueError:
        return None
    if not rel.parts:
        return None
    return BASE_DIR / rel.parts[0]


def _ensure_service_path(service_root: Path) -> None:
    service_str = str(service_root)
    if sys.path[:1] != [service_str]:
        if service_str in sys.path:
            sys.path.remove(service_str)
        sys.path.insert(0, service_str)


def _clear_conflicting_modules(service_root: Path) -> None:
    for name, module in list(sys.modules.items()):
        if name.split(".")[0] not in AMBIGUOUS_MODULES:
            continue
        module_file = getattr(module, "__file__", None)
        if not module_file:
            continue
        module_path = Path(module_file)
        if not _is_under(module_path, BASE_DIR):
            continue
        if _is_under(module_path, service_root):
            continue
        sys.modules.pop(name, None)


def _module_exists(service_root: Path, module_name: str) -> bool:
    if (service_root / f"{module_name}.py").exists():
        return True
    package_init = service_root / module_name / "__init__.py"
    return package_init.exists()


def _prime_service_modules(service_root: Path) -> None:
    service_key = str(service_root)
    if service_key in SERVICE_MODULES:
        return
    SERVICE_MODULES[service_key] = {}
    for module_name in AMBIGUOUS_MODULES:
        if not _module_exists(service_root, module_name):
            continue
        try:
            SERVICE_MODULES[service_key][module_name] = importlib.import_module(module_name)
        except Exception:
            # If import fails here, let the test import surface the error later.
            continue


def _restore_service_modules(service_root: Path) -> None:
    service_key = str(service_root)
    modules = SERVICE_MODULES.get(service_key, {})
    for name, module in modules.items():
        sys.modules[name] = module
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


def pytest_collect_file(file_path, parent):
    path = Path(str(file_path))
    if path.suffix != ".py" or not path.name.startswith("test_"):
        return None
    service_root = _get_service_root(path)
    if not service_root:
        return None
    _ensure_service_path(service_root)
    _clear_conflicting_modules(service_root)
    _prime_service_modules(service_root)
    return None


def pytest_runtest_setup(item):
    service_root = _get_service_root(Path(str(item.fspath)))
    if not service_root:
        return
    _ensure_service_path(service_root)
    _clear_conflicting_modules(service_root)
    _restore_service_modules(service_root)

# Ensure Package collectors always have an 'obj' attribute to avoid plugin crashes.
if not hasattr(Package, "obj"):
    Package.obj = None
