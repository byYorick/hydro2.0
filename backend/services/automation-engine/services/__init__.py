"""Services layer - business logic."""

def __getattr__(name):
    if name == "ZoneAutomationService":
        from .zone_automation_service import ZoneAutomationService
        return ZoneAutomationService
    raise AttributeError(f"module 'services' has no attribute {name}")

__all__ = ['ZoneAutomationService']
