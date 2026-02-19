from __future__ import annotations

from typing import Any, Dict


async def write_log(m: Any, task_name: str, status: str, details: Dict[str, Any]) -> None:
    await m.create_scheduler_log(task_name, status, details)
