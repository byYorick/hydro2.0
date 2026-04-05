"""Общая сортировка для «активной» строки grow_cycle на зону.

Единый источник истины для read-path'ов AE3, которые должны совпадать
с `PgZoneSnapshotReadModel` по выбору grow_cycle id для bundle scope.
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
