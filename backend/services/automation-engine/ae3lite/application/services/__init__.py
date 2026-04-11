"""Application-level services for AE3-Lite handlers.

These sit between handlers and domain/infrastructure: they compose async
dependencies (runtime_monitor, repositories) without owning FSM logic.
"""
