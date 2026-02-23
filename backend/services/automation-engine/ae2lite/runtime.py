"""AE2-Lite runtime assembly helpers."""

from __future__ import annotations

from dataclasses import dataclass

from ae2lite.plan_executor import SchedulerTaskExecutor
from ae2lite.settings import load_limits


@dataclass
class Ae2Runtime:
    limits: dict
    executor: SchedulerTaskExecutor


def build_runtime(*, executor: SchedulerTaskExecutor) -> Ae2Runtime:
    return Ae2Runtime(limits=load_limits(), executor=executor)


__all__ = ["Ae2Runtime", "build_runtime"]
