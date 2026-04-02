"""Shared ordering for «active» grow_cycle row per zone.

Single source of truth for AE3 read paths that must agree with
`PgZoneSnapshotReadModel` (bundle scope = grow_cycle id chosen here).
"""

SQL_ACTIVE_GROW_CYCLE_ORDER_BY = """
            ORDER BY
                CASE
                    WHEN gc.status = 'RUNNING' THEN 0
                    WHEN gc.status = 'PAUSED' THEN 1
                    WHEN gc.status = 'PLANNED' THEN 2
                    ELSE 3
                END,
                gc.id DESC NULLS LAST
"""

__all__ = ["SQL_ACTIVE_GROW_CYCLE_ORDER_BY"]
