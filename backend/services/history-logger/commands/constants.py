"""Canonical command-status sets used by ingress pipeline."""

#: Terminal outcomes: командa дошла до исполнителя и получила окончательный статус.
FINAL_COMMAND_STATUSES: frozenset[str] = frozenset({
    "DONE",
    "NO_EFFECT",
    "ERROR",
    "INVALID",
    "BUSY",
    "TIMEOUT",
})

#: Статусы, при которых повторная публикация запрещена (final + ACK).
NON_REPUBLISHABLE_COMMAND_STATUSES: frozenset[str] = FINAL_COMMAND_STATUSES | {"ACK"}

#: Статусы, при которых разрешён republish (пересылка) в MQTT.
REPUBLISH_ALLOWED_STATUSES: frozenset[str] = frozenset({"QUEUED", "SEND_FAILED"})

#: Валидные значения ``commands.status`` сразу после успешного MQTT publish.
POST_PUBLISH_ALLOWED_STATUSES: frozenset[str] = (
    NON_REPUBLISHABLE_COMMAND_STATUSES | REPUBLISH_ALLOWED_STATUSES | {"SENT"}
)

#: Exponential backoff для retry MQTT publish. Worst-case ~3.5s до bubble 500.
MQTT_PUBLISH_RETRY_DELAYS_SEC: tuple[float, ...] = (0.5, 1.0, 2.0)

#: Легаси-статусы, которые history-logger ни при каких условиях не должен ни генерировать,
#: ни персистить в ``commands.status``.
FORBIDDEN_COMMAND_STATUSES: frozenset[str] = frozenset({"ACCEPTED", "FAILED"})

#: Количество попыток MQTT publish перед финальным fail.
MAX_PUBLISH_RETRIES: int = 3
