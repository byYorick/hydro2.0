"""CommandRouter — диспетчер inputs_schedule в ActuatorSolver.

Принимает список запланированных событий (`inputs_schedule`) и применяет их
к ActuatorSolver в порядке возрастания `t_min`. Поддерживает шаг по времени,
который дозвонивает события за `[prev_t, current_t)`.

Формат события (из `SimulationRequest.inputs_schedule`):
    {
        "t_min": <float>,           # минут от начала симуляции (≥ 0)
        "cmd": <str>,               # 'dose' | 'run_pump' | 'set_relay' | ...
        "channel": <str>,           # имя канала (как в node_channels.channel)
        "params": <dict>,           # cmd-specific (ml | duration_ms | state | ...)
        "node_uid": <str>           # опционально, для DT не критично
    }
"""
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from solvers import ActuatorSolver


@dataclass
class _ScheduledEvent:
    t_min: float
    cmd: str
    channel: str
    params: Dict[str, Any]


class CommandRouter:
    """Принимает упорядоченный schedule и пробрасывает события в ActuatorSolver."""

    def __init__(
        self,
        actuator_solver: ActuatorSolver,
        schedule: Optional[Iterable[Dict[str, Any]]] = None,
    ) -> None:
        self.actuator_solver = actuator_solver
        self._events: List[_ScheduledEvent] = self._normalize_schedule(schedule or [])
        self._cursor: int = 0
        self._last_t_min: float = 0.0

    @staticmethod
    def _normalize_schedule(
        schedule: Iterable[Dict[str, Any]],
    ) -> List[_ScheduledEvent]:
        events: List[_ScheduledEvent] = []
        for raw in schedule:
            if not isinstance(raw, dict):
                continue
            try:
                t_min = float(raw.get("t_min", 0))
            except (TypeError, ValueError):
                continue
            cmd = str(raw.get("cmd") or "").strip()
            channel = str(raw.get("channel") or "").strip()
            if not cmd or not channel:
                continue
            params = raw.get("params") or {}
            if not isinstance(params, dict):
                params = {}
            events.append(_ScheduledEvent(
                t_min=max(0.0, t_min),
                cmd=cmd,
                channel=channel,
                params=params,
            ))
        events.sort(key=lambda e: e.t_min)
        return events

    def advance_to(self, current_t_min: float) -> List[_ScheduledEvent]:
        """Применить все события в `[_last_t_min, current_t_min)`.

        Возвращает список применённых (для логов/тестов).
        """
        applied: List[_ScheduledEvent] = []
        while (
            self._cursor < len(self._events)
            and self._events[self._cursor].t_min <= current_t_min
        ):
            event = self._events[self._cursor]
            self.actuator_solver.apply_command(
                cmd=event.cmd,
                channel=event.channel,
                params=event.params,
            )
            applied.append(event)
            self._cursor += 1
        self._last_t_min = current_t_min
        return applied

    @property
    def remaining_events(self) -> int:
        return max(0, len(self._events) - self._cursor)
