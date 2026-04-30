"""Services layer - legacy business logic package."""

__all__ = ['ZoneAutomationService']


def __getattr__(name):
    if name == 'ZoneAutomationService':
        from .zone_automation_service import ZoneAutomationService
        return ZoneAutomationService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
