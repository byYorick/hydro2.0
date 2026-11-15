"""app runtime intent listener: explicit dependencies and invocation data."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AppRuntimeIntentListenerPorts:
    pass


class AppRuntimeIntentListener:
    def __init__(self, ports: AppRuntimeIntentListenerPorts) -> None:
        self._ports = ports

    def build_intent_listener_callback(self, *, worker: Any, logger: logging.Logger) -> Any:
        async def _on_terminal_intent(data: dict[str, Any]) -> None:
            intent_id = data.get("intent_id")
            zone_id = data.get("zone_id")
            status = data.get("status")
            logger.info(
                "IntentStatusListener: terminal intent received intent_id=%s zone_id=%s status=%s; kicking worker",
                intent_id,
                zone_id,
                status,
            )
            worker.kick()

        return _on_terminal_intent
