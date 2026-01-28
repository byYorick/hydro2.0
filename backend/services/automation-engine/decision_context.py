from dataclasses import dataclass
from typing import Any, Dict, Optional, Union


ContextDict = Dict[str, Any]
ContextLike = Optional[Union["DecisionContext", ContextDict]]


def _compact_payload(payload: ContextDict) -> ContextDict:
    return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class DecisionContext:
    current_value: Optional[float] = None
    target_value: Optional[float] = None
    diff: Optional[float] = None
    reason: Optional[str] = None
    telemetry: Optional[ContextDict] = None
    pid_zone: Optional[str] = None
    pid_output: Optional[float] = None
    pid_integral: Optional[float] = None
    pid_prev_error: Optional[float] = None
    trace_id: Optional[str] = None

    def to_dict(self) -> ContextDict:
        payload = _compact_payload(
            {
                "current_value": self.current_value,
                "target_value": self.target_value,
                "diff": self.diff,
                "reason": self.reason,
                "pid_zone": self.pid_zone,
                "pid_output": self.pid_output,
                "pid_integral": self.pid_integral,
                "pid_prev_error": self.pid_prev_error,
                "trace_id": self.trace_id,
            }
        )
        if self.telemetry:
            payload["telemetry"] = self.telemetry
        return payload

    def telemetry_snapshot(self) -> ContextDict:
        return self.telemetry or {}

    def decision_payload(self) -> ContextDict:
        return _compact_payload(
            {
                "current_value": self.current_value,
                "target_value": self.target_value,
                "diff": self.diff,
                "reason": self.reason,
                "pid_zone": self.pid_zone,
                "pid_output": self.pid_output,
                "pid_integral": self.pid_integral,
            }
        )

    def pid_payload(self) -> ContextDict:
        return _compact_payload(
            {
                "integral": self.pid_integral,
                "prev_error": self.pid_prev_error,
                "zone": self.pid_zone,
            }
        )


def normalize_context(context: ContextLike) -> ContextDict:
    if isinstance(context, DecisionContext):
        return context.to_dict()
    return context or {}
