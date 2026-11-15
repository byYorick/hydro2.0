"""Typed records shared by the component boundaries."""

from dataclasses import dataclass, field
from typing import List

from common.redis_queue import QueueEntry


class PgTransportError(Exception):
    """Транспортная ошибка PostgreSQL — батч можно безопасно requeue."""


@dataclass
class TelemetryBatchResult:
    """Результат обработки батча телеметрии для selective ack/requeue/dead-list."""

    entries_to_requeue: List[QueueEntry] = field(default_factory=list)
    entries_to_dead: List[QueueEntry] = field(default_factory=list)
    processed_count: int = 0

    def entries_to_ack(self, all_entries: List[QueueEntry]) -> List[QueueEntry]:
        dead_ids = {id(entry) for entry in self.entries_to_dead}
        requeue_ids = {id(entry) for entry in self.entries_to_requeue}
        return [entry for entry in all_entries if id(entry) not in dead_ids and id(entry) not in requeue_ids]
