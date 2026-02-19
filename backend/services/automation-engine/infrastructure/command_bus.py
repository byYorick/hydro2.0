"""
Command Bus - централизованная публикация команд через history-logger REST API.
Интегрирован с валидацией команд и отслеживанием выполнения.
Все общение с нодами происходит через history-logger.
"""
import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Optional, Dict, Any, Tuple
import httpx
from common.mqtt import MqttClient
from common.commands import new_command_id
from common.db import create_zone_event, fetch
from common.infra_alerts import send_infra_alert, send_infra_exception_alert
from common.simulation_events import record_simulation_event
from prometheus_client import Counter, Histogram
from .command_validator import CommandValidator
from .command_tracker import CommandTracker
from .command_audit import CommandAudit
from utils.logging_context import get_trace_id
from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from decision_context import ContextLike, normalize_context
from services.resilience_contract import (
    INFRA_COMMAND_BUSY,
    INFRA_COMMAND_CHANNEL_TYPE_VALIDATION_FAILED,
    INFRA_COMMAND_EFFECT_NOT_CONFIRMED,
    INFRA_COMMAND_FAILED,
    INFRA_COMMAND_INVALID,
    INFRA_COMMAND_INVALID_CHANNEL_TYPE,
    INFRA_COMMAND_NO_EFFECT,
    INFRA_COMMAND_NODE_ZONE_MISMATCH,
    INFRA_COMMAND_NODE_ZONE_VALIDATION_FAILED,
    INFRA_COMMAND_PUBLISH_RESPONSE_DECODE_ERROR,
    INFRA_COMMAND_SEND_FAILED,
    INFRA_COMMAND_TIMEOUT,
    INFRA_COMMAND_TRACKER_UNAVAILABLE,
    INFRA_UNKNOWN_ERROR,
)

logger = logging.getLogger(__name__)
_TRUE_VALUES = {"1", "true", "yes", "on"}
_DEFAULT_CLOSED_LOOP_TIMEOUT_SEC = max(1.0, float(os.getenv("AE_COMMAND_CLOSED_LOOP_TIMEOUT_SEC", "60")))
_TERMINAL_COMMAND_STATUSES = {"DONE", "ERROR", "INVALID", "BUSY", "NO_EFFECT", "TIMEOUT", "SEND_FAILED"}
_ACTUATOR_COMMANDS = {"set_relay", "set_pwm", "run_pump", "dose", "light_on", "light_off"}
_SYSTEM_MODE_COMMANDS = {"activate_sensor_mode", "deactivate_sensor_mode"}
_DEFAULT_COMMAND_DEDUPE_TTL_SEC = max(10, int(os.getenv("AE_COMMAND_DEDUPE_TTL_SEC", "3600")))
_MAX_COMMAND_DEDUPE_ENTRIES = max(1000, int(os.getenv("AE_COMMAND_DEDUPE_MAX_ENTRIES", "50000")))

# Метрики для отслеживания ошибок публикации
REST_PUBLISH_ERRORS = Counter("rest_command_errors_total", "REST command publish errors", ["error_type"])
COMMANDS_SENT = Counter("automation_commands_sent_total", "Commands sent by automation", ["zone_id", "metric"])
COMMAND_VALIDATION_FAILED = Counter("command_validation_failed_total", "Failed command validations", ["zone_id", "reason"])
COMMAND_REST_LATENCY = Histogram("command_rest_latency_seconds", "REST command publish latency", buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0])
COMMAND_DEDUPE_DECISIONS = Counter(
    "command_dedupe_decisions_total",
    "Command dedupe decisions before publish",
    ["outcome"],
)
COMMAND_DEDUPE_HITS = Counter(
    "command_dedupe_hits_total",
    "Command dedupe hits (duplicate decisions)",
    ["outcome"],
)
COMMAND_DEDUPE_RESERVE_CONFLICTS = Counter(
    "command_dedupe_reserve_conflicts_total",
    "Command dedupe reserve conflicts",
)


class CommandBus:
    """Централизованная публикация команд через history-logger REST API с валидацией и отслеживанием."""
    
    def __init__(
        self,
        mqtt: Optional[MqttClient] = None,  # Оставлено для обратной совместимости, но не используется
        gh_uid: str = "",
        history_logger_url: Optional[str] = None,
        history_logger_token: Optional[str] = None,
        command_source: Optional[str] = None,
        command_validator: Optional[CommandValidator] = None,
        command_tracker: Optional[CommandTracker] = None,
        command_audit: Optional[CommandAudit] = None,
        http_timeout: float = 5.0,
        api_circuit_breaker: Optional[CircuitBreaker] = None,
        enforce_node_zone_assignment: Optional[bool] = None,
        enforce_command_channel_compatibility: Optional[bool] = None,
    ):
        """
        Инициализация Command Bus.
        
        Args:
            mqtt: MQTT клиент (deprecated, не используется)
            gh_uid: UID теплицы
            history_logger_url: URL history-logger сервиса (по умолчанию из env)
            history_logger_token: Токен для аутентификации (по умолчанию из env)
            command_validator: Валидатор команд (опционально)
            command_tracker: Трекер команд (опционально)
            command_audit: Аудит команд (опционально)
            http_timeout: Таймаут для HTTP запросов в секундах
            api_circuit_breaker: Circuit breaker для API (опционально)
        """
        self.mqtt = mqtt  # Deprecated
        self.gh_uid = gh_uid
        self.history_logger_url = history_logger_url or os.getenv("HISTORY_LOGGER_URL", "http://history-logger:9300")
        self.history_logger_token = history_logger_token or os.getenv("HISTORY_LOGGER_API_TOKEN") or os.getenv("PY_INGEST_TOKEN")
        self.command_source = command_source or os.getenv("COMMAND_SOURCE", "automation")
        self.validator = command_validator or CommandValidator()
        self.tracker = command_tracker
        self.audit = command_audit or CommandAudit()
        self.http_timeout = http_timeout
        self.api_circuit_breaker = api_circuit_breaker
        self._zone_gh_uid_cache: Dict[int, str] = {}
        self.command_dedupe_ttl_sec = _DEFAULT_COMMAND_DEDUPE_TTL_SEC
        self.command_dedupe_enabled = str(os.getenv("AE_COMMAND_DEDUPE_ENABLED", "1")).strip().lower() in _TRUE_VALUES
        self._dedupe_store: Dict[str, Dict[str, Any]] = {}
        self._dedupe_lock = asyncio.Lock()
        if enforce_node_zone_assignment is None:
            raw_guard = str(os.getenv("AE_ENFORCE_NODE_ZONE_ASSIGNMENT", "1")).strip().lower()
            self.enforce_node_zone_assignment = raw_guard in _TRUE_VALUES
        else:
            self.enforce_node_zone_assignment = bool(enforce_node_zone_assignment)
        if enforce_command_channel_compatibility is None:
            raw_guard = str(os.getenv("AE_ENFORCE_COMMAND_CHANNEL_COMPATIBILITY", "1")).strip().lower()
            self.enforce_command_channel_compatibility = raw_guard in _TRUE_VALUES
        else:
            self.enforce_command_channel_compatibility = bool(enforce_command_channel_compatibility)
        
        # Долгоживущий HTTP клиент для переиспользования соединений
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _safe_create_zone_event(
        self,
        zone_id: int,
        event_type: str,
        payload: Dict[str, Any],
    ) -> None:
        try:
            await create_zone_event(zone_id, event_type, payload)
        except Exception:
            logger.warning(
                "Zone %s: failed to create %s event",
                zone_id,
                event_type,
                exc_info=True,
            )

    async def _verify_node_zone_assignment(
        self,
        *,
        zone_id: int,
        node_uid: str,
        channel: str,
        cmd: str,
    ) -> bool:
        if not self.enforce_node_zone_assignment:
            return True

        try:
            rows = await fetch(
                """
                SELECT zone_id, status
                FROM nodes
                WHERE uid = $1
                LIMIT 1
                """,
                node_uid,
            )
        except Exception as exc:
            logger.error(
                "Zone %s: failed to verify node-zone assignment for node_uid=%s: %s",
                zone_id,
                node_uid,
                exc,
                exc_info=True,
            )
            await send_infra_exception_alert(
                error=exc,
                code=INFRA_COMMAND_NODE_ZONE_VALIDATION_FAILED,
                alert_type="Command Node-Zone Validation Failed",
                severity="critical",
                zone_id=zone_id,
                service="automation-engine",
                component="command_bus",
                node_uid=node_uid,
                channel=channel,
                cmd=cmd,
            )
            return False

        if not rows:
            try:
                await create_zone_event(
                    zone_id,
                    "COMMAND_ZONE_NODE_MISMATCH",
                    {
                        "reason": "node_not_found",
                        "expected_zone_id": zone_id,
                        "node_uid": node_uid,
                        "channel": channel,
                        "cmd": cmd,
                    },
                )
            except Exception:
                logger.warning("Zone %s: failed to create COMMAND_ZONE_NODE_MISMATCH event", zone_id, exc_info=True)
            await send_infra_alert(
                code=INFRA_COMMAND_NODE_ZONE_MISMATCH,
                alert_type="Command Node-Zone Mismatch",
                message=f"Команда {cmd} отклонена: node_uid={node_uid} не найден",
                severity="critical",
                zone_id=zone_id,
                service="automation-engine",
                component="command_bus",
                node_uid=node_uid,
                channel=channel,
                cmd=cmd,
                error_type="NodeNotFound",
                details={
                    "reason": "node_not_found",
                    "expected_zone_id": zone_id,
                    "actual_zone_id": None,
                },
            )
            return False

        actual_zone_id = rows[0].get("zone_id")
        if actual_zone_id is None or int(actual_zone_id) != int(zone_id):
            try:
                await create_zone_event(
                    zone_id,
                    "COMMAND_ZONE_NODE_MISMATCH",
                    {
                        "reason": "zone_mismatch",
                        "expected_zone_id": zone_id,
                        "actual_zone_id": actual_zone_id,
                        "node_uid": node_uid,
                        "channel": channel,
                        "cmd": cmd,
                    },
                )
            except Exception:
                logger.warning("Zone %s: failed to create COMMAND_ZONE_NODE_MISMATCH event", zone_id, exc_info=True)
            await send_infra_alert(
                code=INFRA_COMMAND_NODE_ZONE_MISMATCH,
                alert_type="Command Node-Zone Mismatch",
                message=(
                    f"Команда {cmd} отклонена: node_uid={node_uid} закреплен за zone_id={actual_zone_id}, "
                    f"ожидался zone_id={zone_id}"
                ),
                severity="critical",
                zone_id=zone_id,
                service="automation-engine",
                component="command_bus",
                node_uid=node_uid,
                channel=channel,
                cmd=cmd,
                error_type="NodeZoneMismatch",
                details={
                    "reason": "zone_mismatch",
                    "expected_zone_id": zone_id,
                    "actual_zone_id": actual_zone_id,
                },
            )
            return False

        return True

    async def _resolve_greenhouse_uid_for_zone(self, zone_id: int) -> str:
        """
        Определяет canonical greenhouse_uid для зоны.
        Использует fallback на self.gh_uid, если БД временно недоступна.
        """
        cached = self._zone_gh_uid_cache.get(zone_id)
        if cached:
            return cached

        fallback_gh_uid = self.gh_uid
        try:
            rows = await fetch(
                """
                SELECT g.uid AS gh_uid
                FROM zones z
                JOIN greenhouses g ON g.id = z.greenhouse_id
                WHERE z.id = $1
                LIMIT 1
                """,
                zone_id,
            )
            if rows:
                resolved = str(rows[0].get("gh_uid") or "").strip()
                if resolved:
                    self._zone_gh_uid_cache[zone_id] = resolved
                    if fallback_gh_uid and fallback_gh_uid != resolved:
                        logger.warning(
                            "Zone %s: overridden greenhouse_uid from %s to %s for command publish",
                            zone_id,
                            fallback_gh_uid,
                            resolved,
                        )
                    return resolved
        except Exception as exc:
            logger.warning(
                "Zone %s: failed to resolve greenhouse_uid from DB, fallback to configured value: %s",
                zone_id,
                exc,
            )

        if fallback_gh_uid:
            return fallback_gh_uid

        raise RuntimeError(f"Unable to resolve greenhouse_uid for zone_id={zone_id}")

    async def _verify_command_channel_compatibility(
        self,
        *,
        zone_id: int,
        node_uid: str,
        channel: str,
        cmd: str,
    ) -> Tuple[bool, Optional[str]]:
        if not self.enforce_command_channel_compatibility:
            return True, None

        normalized_cmd = str(cmd or "").strip().lower()
        normalized_channel = str(channel or "").strip().lower()

        if normalized_cmd in _SYSTEM_MODE_COMMANDS:
            if normalized_channel != "system":
                return False, "sensor_mode_requires_system_channel"
            return True, None

        if normalized_cmd not in _ACTUATOR_COMMANDS:
            return True, None

        if normalized_channel == "system":
            return False, "actuator_command_on_system_channel"

        try:
            rows = await fetch(
                """
                SELECT UPPER(TRIM(COALESCE(nc.type, ''))) AS channel_type
                FROM nodes n
                LEFT JOIN node_channels nc
                  ON nc.node_id = n.id
                 AND LOWER(TRIM(COALESCE(nc.channel, ''))) = $2
                WHERE n.uid = $1
                LIMIT 1
                """,
                node_uid,
                normalized_channel,
            )
        except Exception as exc:
            logger.error(
                "Zone %s: failed to verify command/channel compatibility node_uid=%s channel=%s cmd=%s: %s",
                zone_id,
                node_uid,
                channel,
                cmd,
                exc,
                exc_info=True,
            )
            await send_infra_exception_alert(
                error=exc,
                code=INFRA_COMMAND_CHANNEL_TYPE_VALIDATION_FAILED,
                alert_type="Command Channel Type Validation Failed",
                severity="critical",
                zone_id=zone_id,
                service="automation-engine",
                component="command_bus",
                node_uid=node_uid,
                channel=channel,
                cmd=cmd,
            )
            return False, "channel_type_validation_failed"

        if not rows:
            return False, "channel_not_found"

        channel_type = str(rows[0].get("channel_type") or "").strip().upper()
        if not channel_type:
            return False, "channel_not_found"

        if channel_type != "ACTUATOR":
            return False, f"channel_type_{channel_type.lower()}"

        return True, None

    async def _handle_command_channel_compatibility_failure(
        self,
        *,
        zone_id: int,
        node_uid: str,
        channel: str,
        cmd: str,
        error_code: str,
    ) -> None:
        COMMAND_VALIDATION_FAILED.labels(zone_id=str(zone_id), reason=error_code).inc()
        logger.error(
            "Zone %s: command validation failed - incompatible channel/cmd node_uid=%s channel=%s cmd=%s reason=%s",
            zone_id,
            node_uid,
            channel,
            cmd,
            error_code,
        )
        try:
            await create_zone_event(
                zone_id,
                "COMMAND_VALIDATION_FAILED",
                {
                    "node_uid": node_uid,
                    "channel": channel,
                    "cmd": cmd,
                    "error": error_code,
                    "reason": "channel_command_mismatch",
                },
            )
        except Exception:
            logger.warning("Zone %s: failed to create COMMAND_VALIDATION_FAILED event", zone_id, exc_info=True)

        await record_simulation_event(
            zone_id,
            service="automation-engine",
            stage="command_validate",
            status="validation_failed",
            level="error",
            message="Команда отклонена: несовместимы cmd и тип канала",
            payload={
                "node_uid": node_uid,
                "channel": channel,
                "cmd": cmd,
                "error_code": error_code,
            },
        )
        await send_infra_alert(
            code=INFRA_COMMAND_INVALID_CHANNEL_TYPE,
            alert_type="Command Channel Type Mismatch",
            message=f"Команда {cmd} отклонена: несовместимый тип канала {channel}",
            severity="warning",
            zone_id=zone_id,
            service="automation-engine",
            component="command_bus",
            node_uid=node_uid,
            channel=channel,
            cmd=cmd,
            error_type=error_code,
            details={
                "reason": "channel_command_mismatch",
                "error_code": error_code,
            },
        )
    
    async def start(self):
        """Инициализировать долгоживущий HTTP клиент."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=self.http_timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
            )
            logger.debug("CommandBus HTTP client initialized")
    
    async def stop(self):
        """Закрыть HTTP клиент и освободить ресурсы."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
            logger.debug("CommandBus HTTP client closed")
    
    def _get_client(self):
        """
        Получить HTTP клиент.
        
        Returns:
            httpx.AsyncClient если долгоживущий клиент инициализирован
            None если нужно использовать временный клиент в контекстном менеджере
        """
        if self._http_client is None:
            logger.warning("CommandBus HTTP client not initialized, using temporary client")
            return None
        return self._http_client

    def _resolve_dedupe_ttl_sec(self, params: Optional[Dict[str, Any]] = None) -> int:
        ttl_raw: Any = None
        if isinstance(params, dict):
            ttl_raw = params.get("dedupe_ttl_sec")
        try:
            ttl_value = int(ttl_raw) if ttl_raw is not None else int(self.command_dedupe_ttl_sec)
        except Exception:
            ttl_value = int(self.command_dedupe_ttl_sec)
        return max(10, ttl_value)

    @staticmethod
    def _normalized_json_payload(payload: Any) -> str:
        try:
            return json.dumps(payload if payload is not None else {}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        except Exception:
            return json.dumps({"__repr__": repr(payload)}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def _build_dedupe_reference_key(
        self,
        *,
        zone_id: int,
        node_uid: str,
        channel: str,
        cmd: str,
        params: Optional[Dict[str, Any]],
    ) -> str:
        material = "|".join(
            [
                str(int(zone_id)),
                str(node_uid or "").strip().lower(),
                str(channel or "").strip().lower(),
                str(cmd or "").strip().lower(),
                self._normalized_json_payload(params),
            ]
        )
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
        return f"zone:{int(zone_id)}:cmd:{digest}"

    def _prune_dedupe_store_locked(self, now_monotonic: float) -> None:
        stale_keys = [
            key
            for key, entry in self._dedupe_store.items()
            if float(entry.get("expires_at_monotonic", 0.0)) <= now_monotonic
        ]
        for key in stale_keys:
            self._dedupe_store.pop(key, None)
        if len(self._dedupe_store) <= _MAX_COMMAND_DEDUPE_ENTRIES:
            return
        sorted_items = sorted(
            self._dedupe_store.items(),
            key=lambda item: float(item[1].get("expires_at_monotonic", now_monotonic)),
        )
        overflow = len(self._dedupe_store) - _MAX_COMMAND_DEDUPE_ENTRIES
        for key, _ in sorted_items[:overflow]:
            self._dedupe_store.pop(key, None)

    async def _reserve_command_dedupe(
        self,
        *,
        zone_id: int,
        node_uid: str,
        channel: str,
        cmd: str,
        params: Optional[Dict[str, Any]],
        cmd_id: Optional[str],
        dedupe_ttl_sec: int,
    ) -> Dict[str, Any]:
        reference_key = self._build_dedupe_reference_key(
            zone_id=zone_id,
            node_uid=node_uid,
            channel=channel,
            cmd=cmd,
            params=params,
        )
        if not self.command_dedupe_enabled:
            return {
                "decision": "new",
                "reference_key": reference_key,
                "dedupe_ttl_sec": dedupe_ttl_sec,
                "reservation_token": None,
                "effective_cmd_id": cmd_id,
            }

        now_monotonic = time.monotonic()
        now_iso = time.time()
        async with self._dedupe_lock:
            self._prune_dedupe_store_locked(now_monotonic)
            existing = self._dedupe_store.get(reference_key)
            if existing is not None and float(existing.get("expires_at_monotonic", 0.0)) > now_monotonic:
                status = str(existing.get("status") or "").strip().lower()
                effective_cmd_id = str(existing.get("cmd_id") or "").strip() or None
                if status == "reserved":
                    COMMAND_DEDUPE_DECISIONS.labels(outcome="duplicate_blocked").inc()
                    COMMAND_DEDUPE_HITS.labels(outcome="duplicate_blocked").inc()
                    COMMAND_DEDUPE_RESERVE_CONFLICTS.inc()
                    return {
                        "decision": "duplicate_blocked",
                        "reference_key": reference_key,
                        "dedupe_ttl_sec": dedupe_ttl_sec,
                        "reservation_token": None,
                        "effective_cmd_id": effective_cmd_id,
                    }
                COMMAND_DEDUPE_DECISIONS.labels(outcome="duplicate_no_effect").inc()
                COMMAND_DEDUPE_HITS.labels(outcome="duplicate_no_effect").inc()
                return {
                    "decision": "duplicate_no_effect",
                    "reference_key": reference_key,
                    "dedupe_ttl_sec": dedupe_ttl_sec,
                    "reservation_token": None,
                    "effective_cmd_id": effective_cmd_id,
                }

            reservation_token = hashlib.sha256(f"{reference_key}:{now_iso}:{new_command_id()}".encode("utf-8")).hexdigest()
            self._dedupe_store[reference_key] = {
                "status": "reserved",
                "reservation_token": reservation_token,
                "created_at_monotonic": now_monotonic,
                "expires_at_monotonic": now_monotonic + float(dedupe_ttl_sec),
                "cmd_id": str(cmd_id or "").strip() or None,
            }
            COMMAND_DEDUPE_DECISIONS.labels(outcome="new").inc()
            return {
                "decision": "new",
                "reference_key": reference_key,
                "dedupe_ttl_sec": dedupe_ttl_sec,
                "reservation_token": reservation_token,
                "effective_cmd_id": str(cmd_id or "").strip() or None,
            }

    async def _bind_dedupe_cmd_id(self, dedupe_state: Optional[Dict[str, Any]], cmd_id: Optional[str]) -> None:
        if not dedupe_state or not self.command_dedupe_enabled:
            return
        reservation_token = str(dedupe_state.get("reservation_token") or "").strip()
        reference_key = str(dedupe_state.get("reference_key") or "").strip()
        resolved_cmd_id = str(cmd_id or "").strip()
        if not reservation_token or not reference_key or not resolved_cmd_id:
            return
        now_monotonic = time.monotonic()
        async with self._dedupe_lock:
            entry = self._dedupe_store.get(reference_key)
            if entry is None:
                return
            if str(entry.get("reservation_token") or "") != reservation_token:
                return
            entry["cmd_id"] = resolved_cmd_id
            entry["expires_at_monotonic"] = max(float(entry.get("expires_at_monotonic", now_monotonic)), now_monotonic)

    async def _complete_command_dedupe(
        self,
        dedupe_state: Optional[Dict[str, Any]],
        *,
        success: bool,
    ) -> None:
        if not dedupe_state or not self.command_dedupe_enabled:
            return
        reference_key = str(dedupe_state.get("reference_key") or "").strip()
        reservation_token = str(dedupe_state.get("reservation_token") or "").strip()
        dedupe_ttl_sec = int(dedupe_state.get("dedupe_ttl_sec") or self.command_dedupe_ttl_sec)
        if not reference_key or not reservation_token:
            return

        now_monotonic = time.monotonic()
        async with self._dedupe_lock:
            entry = self._dedupe_store.get(reference_key)
            if entry is None:
                return
            if str(entry.get("reservation_token") or "") != reservation_token:
                return
            if success:
                entry["status"] = "published"
                entry["expires_at_monotonic"] = now_monotonic + float(max(10, dedupe_ttl_sec))
            else:
                self._dedupe_store.pop(reference_key, None)

    async def _emit_publish_failure_alert(
        self,
        *,
        code: str,
        zone_id: int,
        node_uid: str,
        channel: str,
        cmd: str,
        error: Optional[str],
        error_type: Optional[str],
        http_status: Optional[int] = None,
    ) -> None:
        severity = "critical" if code in {INFRA_COMMAND_SEND_FAILED, INFRA_COMMAND_TIMEOUT} else "error"
        await send_infra_alert(
            code=code,
            alert_type="Command Publish Failed",
            message=f"Не удалось отправить команду {cmd}: {error or code}",
            severity=severity,
            zone_id=zone_id,
            service="automation-engine",
            component="command_bus",
            node_uid=node_uid,
            channel=channel,
            cmd=cmd,
            error_type=error_type,
            details={
                "http_status": http_status,
                "error_message": error,
            },
        )

    async def _emit_closed_loop_failure_alert(
        self,
        *,
        zone_id: int,
        node_uid: str,
        channel: str,
        cmd: str,
        cmd_id: Optional[str],
        terminal_status: str,
        error: Optional[str],
    ) -> None:
        status = str(terminal_status or "").strip().upper() or "UNKNOWN"
        code_map = {
            "SEND_FAILED": (INFRA_COMMAND_SEND_FAILED, "critical"),
            "TRACKER_UNAVAILABLE": (INFRA_COMMAND_TRACKER_UNAVAILABLE, "error"),
            "TIMEOUT": (INFRA_COMMAND_TIMEOUT, "critical"),
            "ERROR": (INFRA_COMMAND_FAILED, "error"),
            "INVALID": (INFRA_COMMAND_INVALID, "error"),
            "BUSY": (INFRA_COMMAND_BUSY, "warning"),
            "NO_EFFECT": (INFRA_COMMAND_NO_EFFECT, "warning"),
        }
        code, severity = code_map.get(status, (INFRA_COMMAND_EFFECT_NOT_CONFIRMED, "error"))
        await send_infra_alert(
            code=code,
            alert_type="Command Closed-Loop Not Confirmed",
            message=f"Команда {cmd} не подтверждена DONE (status={status})",
            severity=severity,
            zone_id=zone_id,
            service="automation-engine",
            component="command_bus",
            node_uid=node_uid,
            channel=channel,
            cmd=cmd,
            error_type=status,
            details={
                "cmd_id": cmd_id,
                "terminal_status": status,
                "error_message": error,
            },
        )
    
    async def publish_command(
        self,
        zone_id: int,
        node_uid: str,
        channel: str,
        cmd: str,
        params: Optional[Dict[str, Any]] = None,
        cmd_id: Optional[str] = None,
        *,
        dedupe_state: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Публикация команды через history-logger REST API.
        
        Args:
            zone_id: ID зоны
            node_uid: UID узла
            channel: Канал узла
            cmd: Команда
            params: Параметры команды
            cmd_id: Идентификатор команды (если уже сгенерирован)
        
        Returns:
            True если команда успешно отправлена, False в противном случае
        """
        start_time = time.time()
        publish_success = False
        dedupe_ttl_sec = self._resolve_dedupe_ttl_sec(params)
        active_dedupe_state = dedupe_state
        if active_dedupe_state is None:
            active_dedupe_state = await self._reserve_command_dedupe(
                zone_id=zone_id,
                node_uid=node_uid,
                channel=channel,
                cmd=cmd,
                params=params,
                cmd_id=cmd_id,
                dedupe_ttl_sec=dedupe_ttl_sec,
            )

        dedupe_decision = str(active_dedupe_state.get("decision") or "new").strip().lower()
        dedupe_reference_key = str(active_dedupe_state.get("reference_key") or "").strip()
        dedupe_ttl_value = int(active_dedupe_state.get("dedupe_ttl_sec") or dedupe_ttl_sec)
        effective_cmd_id = str(cmd_id or active_dedupe_state.get("effective_cmd_id") or "").strip() or None

        if dedupe_decision in {"duplicate_blocked", "duplicate_no_effect"}:
            logger.info(
                "Zone %s: command dedupe prevented side-effect publish cmd=%s node_uid=%s channel=%s decision=%s",
                zone_id,
                cmd,
                node_uid,
                channel,
                dedupe_decision,
                extra={
                    "zone_id": zone_id,
                    "cmd": cmd,
                    "node_uid": node_uid,
                    "channel": channel,
                    "dedupe_decision": dedupe_decision,
                    "dedupe_reference_key": dedupe_reference_key,
                    "dedupe_ttl_sec": dedupe_ttl_value,
                },
            )
            await record_simulation_event(
                zone_id,
                service="automation-engine",
                stage="command_dedupe",
                status=dedupe_decision,
                message="Команда пропущена dedupe арбитражем",
                payload={
                    "cmd": cmd,
                    "node_uid": node_uid,
                    "channel": channel,
                    "cmd_id": effective_cmd_id,
                    "dedupe_decision": dedupe_decision,
                    "dedupe_reference_key": dedupe_reference_key,
                    "dedupe_ttl_sec": dedupe_ttl_value,
                },
            )
            return True

        try:
            await self._bind_dedupe_cmd_id(active_dedupe_state, effective_cmd_id)
            is_assigned = await self._verify_node_zone_assignment(
                zone_id=zone_id,
                node_uid=node_uid,
                channel=channel,
                cmd=cmd,
            )
            if not is_assigned:
                COMMAND_VALIDATION_FAILED.labels(zone_id=str(zone_id), reason="node_zone_mismatch").inc()
                logger.error(
                    "Zone %s: command validation failed - node_uid=%s is not assigned to this zone",
                    zone_id,
                    node_uid,
                )
                await record_simulation_event(
                    zone_id,
                    service="automation-engine",
                    stage="command_validate",
                    status="validation_failed",
                    level="error",
                    message="Команда отклонена: node_uid не привязан к зоне",
                    payload={
                        "node_uid": node_uid,
                        "channel": channel,
                        "cmd": cmd,
                        "reason": "node_zone_mismatch",
                    },
                )
                return False

            is_channel_compatible, channel_error = await self._verify_command_channel_compatibility(
                zone_id=zone_id,
                node_uid=node_uid,
                channel=channel,
                cmd=cmd,
            )
            if not is_channel_compatible:
                await self._handle_command_channel_compatibility_failure(
                    zone_id=zone_id,
                    node_uid=node_uid,
                    channel=channel,
                    cmd=cmd,
                    error_code=str(channel_error or "channel_command_mismatch"),
                )
                return False

            # Получаем trace_id из контекста логирования
            trace_id = get_trace_id()
            if effective_cmd_id:
                trace_id = effective_cmd_id
            
            # Формируем запрос к history-logger
            effective_gh_uid = await self._resolve_greenhouse_uid_for_zone(zone_id)
            payload = {
                "cmd": cmd,
                "greenhouse_uid": effective_gh_uid,
                "zone_id": zone_id,
                "node_uid": node_uid,
                "channel": channel,
                "source": self.command_source,
                "params": params or {},
            }
            if effective_cmd_id:
                payload["cmd_id"] = effective_cmd_id
            if trace_id:
                payload["trace_id"] = trace_id
            
            # Заголовки для аутентификации
            headers = {"Content-Type": "application/json"}
            if self.history_logger_token:
                headers["Authorization"] = f"Bearer {self.history_logger_token}"
            if trace_id:
                headers["X-Trace-Id"] = trace_id
            
            # Обертка для HTTP запроса через circuit breaker
            async def _send_request():
                client = self._get_client()
                if client is None:
                    # Используем временный клиент в контекстном менеджере
                    async with httpx.AsyncClient(timeout=self.http_timeout) as temp_client:
                        return await temp_client.post(
                            f"{self.history_logger_url}/commands",
                            json=payload,
                            headers=headers
                        )
                else:
                    # Используем долгоживущий клиент
                    return await client.post(
                        f"{self.history_logger_url}/commands",
                        json=payload,
                        headers=headers
                    )
            
            # Отправляем запрос через circuit breaker если он настроен
            if self.api_circuit_breaker:
                response = await self.api_circuit_breaker.call(_send_request)
            else:
                response = await _send_request()
            
            latency = time.time() - start_time
            COMMAND_REST_LATENCY.observe(latency)
                
            if response.status_code == 200:
                try:
                    result = response.json()
                    cmd_id = result.get("data", {}).get("command_id")
                    logger.debug(
                        f"Zone {zone_id}: Command {cmd} sent successfully via REST, cmd_id: {cmd_id}",
                        extra={"zone_id": zone_id, "cmd_id": cmd_id, "trace_id": trace_id}
                    )
                    COMMANDS_SENT.labels(zone_id=str(zone_id), metric=cmd).inc()
                    await record_simulation_event(
                        zone_id,
                        service="automation-engine",
                        stage="command_publish",
                        status="sent",
                        message="Команда отправлена через history-logger",
                        payload={
                            "cmd": cmd,
                            "cmd_id": cmd_id,
                            "channel": channel,
                            "node_uid": node_uid,
                            "source": self.command_source,
                            "dedupe_decision": dedupe_decision,
                            "dedupe_reference_key": dedupe_reference_key,
                            "dedupe_ttl_sec": dedupe_ttl_value,
                        },
                    )
                    publish_success = True
                    return True
                except Exception as e:
                    error_type = "json_decode_error"
                    REST_PUBLISH_ERRORS.labels(error_type=error_type).inc()
                    logger.error(
                        f"Zone {zone_id}: Failed to parse response JSON: {e}",
                        extra={"zone_id": zone_id, "trace_id": trace_id}
                    )
                    await record_simulation_event(
                        zone_id,
                        service="automation-engine",
                        stage="command_publish",
                        status="failed",
                        level="error",
                        message="Ошибка разбора ответа history-logger",
                        payload={
                            "cmd": cmd,
                            "channel": channel,
                            "node_uid": node_uid,
                            "error": str(e),
                            "dedupe_decision": dedupe_decision,
                            "dedupe_reference_key": dedupe_reference_key,
                            "dedupe_ttl_sec": dedupe_ttl_value,
                        },
                    )
                    await self._emit_publish_failure_alert(
                        code=INFRA_COMMAND_PUBLISH_RESPONSE_DECODE_ERROR,
                        zone_id=zone_id,
                        node_uid=node_uid,
                        channel=channel,
                        cmd=cmd,
                        error=str(e),
                        error_type=error_type,
                    )
                    return False
            else:
                try:
                    error_msg = response.text
                except Exception:
                    error_msg = f"HTTP {response.status_code}"
                error_type = f"http_{response.status_code}"
                REST_PUBLISH_ERRORS.labels(error_type=error_type).inc()
                logger.error(
                    f"Zone {zone_id}: Failed to publish command {cmd} via REST: {response.status_code} - {error_msg}",
                    extra={"zone_id": zone_id, "trace_id": trace_id}
                )
                await record_simulation_event(
                    zone_id,
                    service="automation-engine",
                    stage="command_publish",
                    status="failed",
                    level="error",
                    message="Ошибка отправки команды через history-logger",
                    payload={
                        "cmd": cmd,
                        "channel": channel,
                        "node_uid": node_uid,
                        "http_status": response.status_code,
                        "error": error_msg,
                        "dedupe_decision": dedupe_decision,
                        "dedupe_reference_key": dedupe_reference_key,
                        "dedupe_ttl_sec": dedupe_ttl_value,
                    },
                )
                await self._emit_publish_failure_alert(
                    code=INFRA_COMMAND_SEND_FAILED,
                    zone_id=zone_id,
                    node_uid=node_uid,
                    channel=channel,
                    cmd=cmd,
                    error=error_msg,
                    error_type=error_type,
                    http_status=response.status_code,
                )
                return False
                    
        except httpx.TimeoutException as e:
            error_type = "timeout"
            REST_PUBLISH_ERRORS.labels(error_type=error_type).inc()
            logger.error(f"Zone {zone_id}: Timeout publishing command {cmd} via REST: {e}", exc_info=True)
            await record_simulation_event(
                zone_id,
                service="automation-engine",
                stage="command_publish",
                status="failed",
                level="error",
                message="Таймаут отправки команды через history-logger",
                payload={
                    "cmd": cmd,
                    "channel": channel,
                    "node_uid": node_uid,
                    "error": str(e),
                    "dedupe_decision": dedupe_decision,
                    "dedupe_reference_key": dedupe_reference_key,
                    "dedupe_ttl_sec": dedupe_ttl_value,
                },
            )
            await self._emit_publish_failure_alert(
                code=INFRA_COMMAND_TIMEOUT,
                zone_id=zone_id,
                node_uid=node_uid,
                channel=channel,
                cmd=cmd,
                error=str(e),
                error_type=error_type,
            )
            return False
        except httpx.RequestError as e:
            error_type = "request_error"
            REST_PUBLISH_ERRORS.labels(error_type=error_type).inc()
            logger.error(f"Zone {zone_id}: Request error publishing command {cmd} via REST: {e}", exc_info=True)
            await record_simulation_event(
                zone_id,
                service="automation-engine",
                stage="command_publish",
                status="failed",
                level="error",
                message="Ошибка запроса при отправке команды через history-logger",
                payload={
                    "cmd": cmd,
                    "channel": channel,
                    "node_uid": node_uid,
                    "error": str(e),
                    "dedupe_decision": dedupe_decision,
                    "dedupe_reference_key": dedupe_reference_key,
                    "dedupe_ttl_sec": dedupe_ttl_value,
                },
            )
            await self._emit_publish_failure_alert(
                code=INFRA_COMMAND_SEND_FAILED,
                zone_id=zone_id,
                node_uid=node_uid,
                channel=channel,
                cmd=cmd,
                error=str(e),
                error_type=error_type,
            )
            return False
        except Exception as e:
            error_type = type(e).__name__
            REST_PUBLISH_ERRORS.labels(error_type=error_type).inc()
            logger.error(f"Zone {zone_id}: Failed to publish command {cmd} via REST: {e}", exc_info=True)
            await record_simulation_event(
                zone_id,
                service="automation-engine",
                stage="command_publish",
                status="failed",
                level="error",
                message="Не удалось отправить команду через history-logger",
                payload={
                    "cmd": cmd,
                    "channel": channel,
                    "node_uid": node_uid,
                    "error": str(e),
                    "dedupe_decision": dedupe_decision,
                    "dedupe_reference_key": dedupe_reference_key,
                    "dedupe_ttl_sec": dedupe_ttl_value,
                },
            )
            await send_infra_exception_alert(
                error=e,
                code=INFRA_UNKNOWN_ERROR,
                alert_type="Command Publish Unexpected Error",
                severity="error",
                zone_id=zone_id,
                service="automation-engine",
                component="command_bus",
                node_uid=node_uid,
                channel=channel,
                cmd=cmd,
            )
            return False
        finally:
            await self._complete_command_dedupe(active_dedupe_state, success=publish_success)
    
    async def publish_controller_command(
        self,
        zone_id: int,
        command: Dict[str, Any],
        context: ContextLike = None
    ) -> bool:
        """
        Публикация команды от контроллера с валидацией и отслеживанием.
        
        Args:
            zone_id: ID зоны
            command: Команда от контроллера с полями:
                - node_uid: UID узла
                - channel: Канал узла
                - cmd: Команда
                - params: Параметры команды (опционально)
            context: Дополнительный контекст для трекинга
        
        Returns:
            True если команда успешно отправлена, False в противном случае
        """
        node_uid = command.get('node_uid')
        channel = command.get('channel', 'default')
        cmd = command.get('cmd')
        params = command.get('params')
        incoming_cmd_id_raw = command.get('cmd_id')
        incoming_cmd_id = str(incoming_cmd_id_raw).strip() if isinstance(incoming_cmd_id_raw, str) else None
        if incoming_cmd_id == "":
            incoming_cmd_id = None
        cmd_id = None
        normalized_context = normalize_context(context)
        
        if not node_uid or not cmd:
            logger.warning(f"Zone {zone_id}: Invalid command structure - missing node_uid or cmd")
            return False
        
        # Валидация команды
        is_valid, error = self.validator.validate_command(command)
        if not is_valid:
            COMMAND_VALIDATION_FAILED.labels(zone_id=str(zone_id), reason=error or 'unknown').inc()
            logger.error(
                f"Zone {zone_id}: Command validation failed: {error}",
                extra={
                    'zone_id': zone_id,
                    'command': command,
                    'validation_error': error
                }
            )
            await self._safe_create_zone_event(
                zone_id,
                "COMMAND_VALIDATION_FAILED",
                {
                    "command": command,
                    "error": error,
                },
            )
            await record_simulation_event(
                zone_id,
                service="automation-engine",
                stage="command_validate",
                status="validation_failed",
                level="warning",
                message="Команда не прошла валидацию",
                payload={
                    "command": command,
                    "error": error,
                },
            )
            return False
        
        dedupe_ttl_sec = self._resolve_dedupe_ttl_sec(params)
        generated_cmd_id = incoming_cmd_id
        if generated_cmd_id is None and self.tracker is not None:
            generated_cmd_id = new_command_id()

        dedupe_state = await self._reserve_command_dedupe(
            zone_id=zone_id,
            node_uid=str(node_uid),
            channel=str(channel),
            cmd=str(cmd),
            params=params if isinstance(params, dict) else {},
            cmd_id=generated_cmd_id,
            dedupe_ttl_sec=dedupe_ttl_sec,
        )
        dedupe_decision = str(dedupe_state.get("decision") or "new").strip().lower()
        dedupe_reference_key = str(dedupe_state.get("reference_key") or "").strip()
        dedupe_ttl_value = int(dedupe_state.get("dedupe_ttl_sec") or dedupe_ttl_sec)
        effective_cmd_id = str(dedupe_state.get("effective_cmd_id") or generated_cmd_id or "").strip() or None

        command["dedupe_decision"] = dedupe_decision
        command["dedupe_reference_key"] = dedupe_reference_key
        command["dedupe_ttl_sec"] = dedupe_ttl_value

        if dedupe_decision in {"duplicate_blocked", "duplicate_no_effect"}:
            if effective_cmd_id:
                command["cmd_id"] = effective_cmd_id
            cmd_id = effective_cmd_id
            await self._safe_create_zone_event(
                zone_id,
                "COMMAND_DEDUPE_SKIPPED",
                {
                    "node_uid": node_uid,
                    "channel": channel,
                    "cmd": cmd,
                    "cmd_id": effective_cmd_id,
                    "dedupe_decision": dedupe_decision,
                    "dedupe_reference_key": dedupe_reference_key,
                    "dedupe_ttl_sec": dedupe_ttl_value,
                },
            )
            success = True
        else:
            # Отслеживание команды
            cmd_id = None
            if self.tracker:
                try:
                    cmd_id = await self.tracker.track_command(
                        zone_id,
                        command,
                        normalized_context,
                        cmd_id=generated_cmd_id,
                    )
                    command["cmd_id"] = cmd_id
                    await self._bind_dedupe_cmd_id(dedupe_state, cmd_id)
                except Exception as e:
                    logger.warning(f"Zone {zone_id}: Failed to track command: {e}", exc_info=True)
                    await self._complete_command_dedupe(dedupe_state, success=False)
                    params = command.get('params')
                    cmd_id = None
                    command.pop('cmd_id', None)
                    return False
            else:
                cmd_id = incoming_cmd_id
                if cmd_id:
                    command["cmd_id"] = cmd_id
                    await self._bind_dedupe_cmd_id(dedupe_state, cmd_id)

            # Публикация команды (cmd_id передается top-level)
            success = await self.publish_command(
                zone_id,
                node_uid,
                channel,
                cmd,
                params,
                cmd_id=cmd_id,
                dedupe_state=dedupe_state,
            )

        cmd_id = str(command.get("cmd_id") or cmd_id or "").strip() or None
        
        # Аудит команды (даже если не удалось отправить)
        try:
            await self.audit.audit_command(zone_id, command, normalized_context)
        except Exception as e:
            logger.warning(f"Zone {zone_id}: Failed to audit command: {e}", exc_info=True)
        
        if not success and cmd_id and self.tracker:
            # Если публикация не удалась, фиксируем терминальный статус SEND_FAILED.
            await self.tracker.confirm_command_status(cmd_id, "SEND_FAILED", error="publish_failed")

        return success

    async def publish_controller_command_closed_loop(
        self,
        zone_id: int,
        command: Dict[str, Any],
        context: ContextLike = None,
        timeout_sec: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Публикация команды с closed-loop подтверждением эффекта.

        Успех фиксируется только при терминальном статусе DONE.
        """
        effective_timeout = float(timeout_sec) if timeout_sec is not None else _DEFAULT_CLOSED_LOOP_TIMEOUT_SEC
        effective_timeout = max(1.0, effective_timeout)
        tracker = self.tracker
        result: Dict[str, Any] = {
            "command_submitted": False,
            "command_effect_confirmed": False,
            "terminal_status": None,
            "cmd_id": None,
            "error_code": None,
            "error": None,
        }
        node_uid = str(command.get("node_uid") or "").strip() or "unknown"
        channel = str(command.get("channel") or "").strip() or "default"
        cmd = str(command.get("cmd") or "").strip() or "unknown"

        submitted = await self.publish_controller_command(zone_id, command, context)
        cmd_id = str(command.get("cmd_id") or "").strip() or None
        result["command_submitted"] = bool(submitted)
        result["cmd_id"] = cmd_id

        if not submitted:
            result["terminal_status"] = "SEND_FAILED"
            result["error_code"] = "SEND_FAILED"
            result["error"] = "publish_failed"
            await self._safe_create_zone_event(
                zone_id,
                "COMMAND_EFFECT_NOT_CONFIRMED",
                {
                    "cmd_id": cmd_id,
                    "cmd": cmd,
                    "node_uid": node_uid,
                    "channel": channel,
                    "terminal_status": "SEND_FAILED",
                    "reason": "publish_failed",
                },
            )
            await self._emit_closed_loop_failure_alert(
                zone_id=zone_id,
                node_uid=node_uid,
                channel=channel,
                cmd=cmd,
                cmd_id=cmd_id,
                terminal_status="SEND_FAILED",
                error="publish_failed",
            )
            return result

        if tracker is None or cmd_id is None:
            result["terminal_status"] = "TRACKER_UNAVAILABLE"
            result["error_code"] = "TRACKER_UNAVAILABLE"
            result["error"] = "command_tracker_required_for_closed_loop"
            await self._safe_create_zone_event(
                zone_id,
                "COMMAND_EFFECT_NOT_CONFIRMED",
                {
                    "cmd_id": cmd_id,
                    "cmd": cmd,
                    "node_uid": node_uid,
                    "channel": channel,
                    "terminal_status": "TRACKER_UNAVAILABLE",
                    "reason": "tracker_or_cmd_id_missing",
                },
            )
            await self._emit_closed_loop_failure_alert(
                zone_id=zone_id,
                node_uid=node_uid,
                channel=channel,
                cmd=cmd,
                cmd_id=cmd_id,
                terminal_status="TRACKER_UNAVAILABLE",
                error="command_tracker_required_for_closed_loop",
            )
            return result

        wait_result = await tracker.wait_for_command_done(
            cmd_id=cmd_id,
            timeout_sec=effective_timeout,
            poll_interval_sec=min(1.0, max(0.25, effective_timeout / 20.0)),
        )
        if wait_result is True:
            result["command_effect_confirmed"] = True
            result["terminal_status"] = "DONE"
            return result

        terminal_status = await tracker._get_command_status_from_db(cmd_id)  # noqa: SLF001
        normalized_status = str(terminal_status or "").strip().upper()

        if wait_result is None:
            # Нода могла ответить между последним poll и таймаутом —
            # если БД уже содержит терминальный статус, используем его.
            if normalized_status == "DONE":
                result["command_effect_confirmed"] = True
                result["terminal_status"] = "DONE"
                return result
            if normalized_status not in _TERMINAL_COMMAND_STATUSES:
                normalized_status = "TIMEOUT"
            try:
                if normalized_status == "TIMEOUT":
                    await tracker.confirm_command_status(cmd_id, "TIMEOUT", error="closed_loop_timeout")
            except Exception:
                logger.warning("Zone %s: failed to mark TIMEOUT for cmd_id=%s", zone_id, cmd_id, exc_info=True)

        if normalized_status not in _TERMINAL_COMMAND_STATUSES:
            normalized_status = "ERROR"

        result["terminal_status"] = normalized_status
        result["error_code"] = normalized_status
        result["error"] = f"command_terminal_status_{normalized_status.lower()}"

        await self._safe_create_zone_event(
            zone_id,
            "COMMAND_EFFECT_NOT_CONFIRMED",
            {
                "cmd_id": cmd_id,
                "cmd": cmd,
                "node_uid": node_uid,
                "channel": channel,
                "terminal_status": normalized_status,
                "reason": "terminal_status_not_done",
            },
        )
        await self._emit_closed_loop_failure_alert(
            zone_id=zone_id,
            node_uid=node_uid,
            channel=channel,
            cmd=cmd,
            cmd_id=cmd_id,
            terminal_status=normalized_status,
            error=result["error"],
        )
        return result
