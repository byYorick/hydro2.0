"""Command request-contract / node_secret / status normalisation."""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from common.trace_context import get_trace_id, set_trace_id
from models import CommandRequest


def validate_command_request_contract(req: CommandRequest) -> None:
    if "legacy_type" in req.model_fields_set:
        raise HTTPException(
            status_code=400,
            detail="Legacy field 'type' is not supported, use 'cmd'",
        )
    if not req.get_command_name():
        raise HTTPException(status_code=400, detail="'cmd' is required")


def apply_trace_id(trace_id: str | None) -> None:
    if trace_id and not get_trace_id():
        set_trace_id(trace_id, allow_generate=False)


def ensure_node_secret(config: dict) -> dict:
    """Backward-compatible name: never put plaintext node_secret on MQTT.

    Command HMAC still uses ``_resolve_node_secret`` (DB). Config publish goes
    through ``prepare_node_config_for_mqtt``.
    """
    from commands.node_secret_wire import prepare_node_config_for_mqtt

    node_uid = ""
    raw_uid = config.get("node_id") or config.get("node_uid")
    if isinstance(raw_uid, str):
        node_uid = raw_uid
    return prepare_node_config_for_mqtt(config, node_uid=node_uid)


def normalize_command_status(status: Any) -> str:
    return str(status or "").strip().upper()


def normalize_params_for_idempotency(params: Any) -> str:
    """Канонизация params для проверки коллизий cmd_id.

    Это **не дубль** ``canonical_json_payload`` из ``common.hmac_utils``:

    * ``canonical_json_payload`` — формат для HMAC-подписи (cJSON-совместимые float,
      без ``sig``-ключа). Любое изменение формата ломает verification на нодах.
    * ``normalize_params_for_idempotency`` — ключ коллизии по ``(cmd_id, params_hash)``
      в БД. Использует ``sort_keys`` под исторический формат Laravel, где ключи
      в params приходили в разном порядке.

    Объединять нельзя — сломается либо HMAC, либо idempotency-дедупликация legacy строк.
    """
    candidate: Any = {} if params is None else params
    if isinstance(candidate, str):
        try:
            candidate = json.loads(candidate)
        except Exception:
            candidate = candidate.strip()
    # Laravel исторически писал пустые params и как ``[]``, и как ``{}`` — для
    # коллизии это эквивалент.
    if isinstance(candidate, list) and len(candidate) == 0:
        candidate = {}
    try:
        return json.dumps(candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except Exception:
        return str(candidate)
