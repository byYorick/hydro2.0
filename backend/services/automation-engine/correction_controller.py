"""
Correction Controller - универсальный контроллер для корректировки pH и EC.
Устраняет дублирование кода между pH и EC корректировкой.
"""
import asyncio
from typing import Optional, Dict, Any, List
from enum import Enum
import time
import logging
from uuid import uuid4
from common.db import create_zone_event, create_ai_log, fetch
from correction_cooldown import should_apply_correction, record_correction
from config.settings import get_settings
from utils.adaptive_pid import AdaptivePid, AdaptivePidConfig, PidZone, PidZoneCoeffs
from services.pid_config_service import get_config, invalidate_cache
from services.pid_state_manager import PidStateManager
from common.infra_alerts import send_infra_alert
from decision_context import DecisionContext
from services.targets_accessor import get_ph_target, get_ec_target
from scheduler_internal_enqueue import enqueue_internal_scheduler_task
from correction_freshness import validate_freshness_or_skip
from services.correction_bounds_policy import (
    apply_target_rate_limit,
    resolve_bounds,
    validate_target_with_bounds,
)
from correction_ec_batch import (
    build_ec_component_batch,
    build_actuator_identity,
    resolve_ec_component_ratios,
    resolve_nutrition_mode,
    resolve_solution_volume_l,
    extract_nutrition_control,
    resolve_batch_dose_control,
    get_latest_ec_value,
)
from correction_command_retry import (
    publish_controller_command_with_retry,
    trigger_ec_partial_batch_compensation,
    wait_command_done,
)

logger = logging.getLogger(__name__)


class CorrectionType(Enum):
    """Тип корректировки."""
    PH = "ph"
    EC = "ec"

class CorrectionController:
    """Универсальный контроллер для корректировки pH/EC."""
    
    def __init__(self, correction_type: CorrectionType, pid_state_manager: Optional[PidStateManager] = None):
        """
        Инициализация контроллера.
        
        Args:
            correction_type: Тип корректировки (PH или EC)
            pid_state_manager: Менеджер состояния PID (опционально)
        """
        self.correction_type = correction_type
        self.metric_name = correction_type.value.upper()
        self.event_prefix = correction_type.value.upper()
        self._pid_by_zone: Dict[int, AdaptivePid] = {}
        self._last_pid_tick: Dict[int, float] = {}
        self._last_target_by_zone: Dict[int, float] = {}
        self._last_target_ts_by_zone: Dict[int, float] = {}
        self.pid_state_manager = pid_state_manager or PidStateManager()
        # Счетчик подряд пропусков проверки свежести по зонам
        self._freshness_check_failure_count: Dict[int, int] = {}

    def _log_skip(
        self,
        *,
        zone_id: int,
        reason_code: str,
        level: str = "warning",
        **extra_data: Any,
    ) -> None:
        payload = {
            "component": "correction_controller",
            "zone_id": zone_id,
            "metric": self.metric_name,
            "decision": "skip",
            "reason_code": reason_code,
        }
        payload.update(extra_data)
        log_fn = logger.info if level == "info" else logger.warning
        log_fn(
            "Zone %s: %s correction skipped (%s)",
            zone_id,
            self.metric_name,
            reason_code,
            extra=payload,
        )
    
    async def check_and_correct(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        telemetry: Dict[str, Optional[float]],
        telemetry_timestamps: Optional[Dict[str, Any]] = None,
        nodes: Dict[str, Dict[str, Any]] = None,
        water_level_ok: bool = True,
        actuators: Optional[Dict[str, Dict[str, Any]]] = None,
        bounds_overrides: Optional[Dict[str, Any]] = None,
        allowed_ec_components: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Проверка и корректировка параметра (pH или EC).
        
        Args:
            zone_id: ID зоны
            targets: Целевые значения из рецепта
            telemetry: Текущие значения телеметрии
            telemetry_timestamps: Временные метки обновления телеметрии (для проверки свежести)
            nodes: Узлы зоны
            water_level_ok: Флаг, что уровень воды в норме
        
        Returns:
            Команда для корректировки или None
        """
        target_key = self.correction_type.value
        current = telemetry.get(self.metric_name) or telemetry.get(target_key)
        if self.correction_type == CorrectionType.PH:
            target, target_min, target_max = get_ph_target(targets, zone_id=zone_id)
        else:
            target, target_min, target_max = get_ec_target(targets, zone_id=zone_id)

        if target is None or current is None:
            logger.debug(
                "Zone %s: %s correction skipped due to missing target/current",
                zone_id,
                self.metric_name,
                extra={
                    "zone_id": zone_id,
                    "metric": self.metric_name,
                    "current": current,
                    "target": target,
                },
            )
            return None

        logger.debug(
            "Zone %s: evaluating %s correction",
            zone_id,
            self.metric_name,
            extra={
                "zone_id": zone_id,
                "metric": self.metric_name,
                "current": current,
                "target": target,
                "target_min": target_min,
                "target_max": target_max,
                "water_level_ok": water_level_ok,
                "allowed_ec_components": allowed_ec_components,
                "bounds_overrides": bounds_overrides,
            },
        )
        
        freshness_ok = await validate_freshness_or_skip(
            zone_id=zone_id,
            metric_name=self.metric_name,
            target_key=target_key,
            correction_type=self.correction_type.value,
            current=current,
            target=target,
            telemetry_timestamps=telemetry_timestamps,
            freshness_check_failure_count=self._freshness_check_failure_count,
            event_prefix=self.event_prefix,
        )
        if not freshness_ok:
            return None
        
        try:
            target_val = float(target)
            current_val = float(current)
        except (ValueError, TypeError) as e:
            self._log_skip(
                zone_id=zone_id,
                reason_code="invalid_target_or_current",
                target=target,
                current=current,
                error=str(e),
            )
            return None

        target_original_val = target_val
        settings = get_settings()
        safety_enabled = bool(getattr(settings, "AE_SAFETY_BOUNDS_ENABLED", True))
        safety_kill_switch = bool(getattr(settings, "AE_SAFETY_BOUNDS_KILL_SWITCH", False))
        safety_active = safety_enabled and not safety_kill_switch
        bounds_context: Dict[str, Any] = {}
        rate_limit_result: Dict[str, Any] = {"clamped": False, "target": target_val}

        if safety_active:
            bounds_context = resolve_bounds(
                metric=target_key,
                targets=targets,
                bounds_overrides=bounds_overrides,
                settings=settings,
            )
            previous_target = self._last_target_by_zone.get(zone_id)
            previous_target_ts = self._last_target_ts_by_zone.get(zone_id)
            now_target_ts = time.monotonic()
            elapsed_seconds = (
                None
                if previous_target_ts is None
                else max(0.0, now_target_ts - previous_target_ts)
            )

            bounds_validation = validate_target_with_bounds(
                metric=target_key,
                target=target_val,
                bounds=bounds_context,
                previous_target=previous_target,
            )
            if not bool(bounds_validation.get("valid")):
                reason_code = str(bounds_validation.get("reason_code") or "bounds_validation_failed")
                self._log_skip(
                    zone_id=zone_id,
                    reason_code=reason_code,
                    target=target_val,
                    current=current_val,
                    bounds=bounds_context,
                    validation=bounds_validation.get("details"),
                )
                await create_zone_event(
                    zone_id,
                    f"{self.event_prefix}_CORRECTION_SKIPPED_BOUNDS",
                    {
                        "metric": target_key,
                        "reason_code": reason_code,
                        "target": target_val,
                        "current": current_val,
                        "bounds": bounds_context,
                        "validation": bounds_validation.get("details") or {},
                    },
                )
                return None

            rate_limit_result = apply_target_rate_limit(
                target=target_val,
                bounds=bounds_context,
                previous_target=previous_target,
                elapsed_seconds=elapsed_seconds,
            )
            target_val = float(rate_limit_result.get("target", target_val))
            if bool(rate_limit_result.get("clamped")):
                await create_zone_event(
                    zone_id,
                    f"{self.event_prefix}_TARGET_CLAMPED_RATE_LIMIT",
                    {
                        "metric": target_key,
                        "requested_target": target_original_val,
                        "effective_target": target_val,
                        "previous_target": previous_target,
                        "allowed_delta": rate_limit_result.get("allowed_delta"),
                        "elapsed_seconds": rate_limit_result.get("elapsed_seconds"),
                        "reason_code": str(rate_limit_result.get("reason_code") or "max_delta_per_min_clamped"),
                    },
                )

            self._last_target_by_zone[zone_id] = target_val
            self._last_target_ts_by_zone[zone_id] = now_target_ts
        else:
            self._last_target_by_zone[zone_id] = target_val
            self._last_target_ts_by_zone[zone_id] = time.monotonic()

        if target_min is not None and target_max is not None:
            if target_min <= current_val <= target_max:
                logger.debug(
                    "Zone %s: %s correction skipped - value inside target range",
                    zone_id,
                    self.metric_name,
                    extra={
                        "zone_id": zone_id,
                        "metric": self.metric_name,
                        "current": current_val,
                        "target_min": target_min,
                        "target_max": target_max,
                    },
                )
                return None
        
        diff = current_val - target_val

        pid = await self._get_pid(zone_id, target_val)
        
        # Проверяем, превышает ли отклонение порог
        if abs(diff) <= pid.config.dead_zone:
            logger.debug(
                "Zone %s: %s correction skipped - diff within dead zone",
                zone_id,
                self.metric_name,
                extra={
                    "zone_id": zone_id,
                    "metric": self.metric_name,
                    "diff": diff,
                    "dead_zone": pid.config.dead_zone,
                },
            )
            return None
        
        # Проверяем cooldown и анализ тренда
        should_correct, reason = await should_apply_correction(
            zone_id, target_key, current_val, target_val, diff
        )
        
        if not should_correct:
            self._log_skip(
                zone_id=zone_id,
                reason_code="cooldown_or_trend_policy_blocked",
                level="info",
                reason=reason,
                diff=diff,
            )
            # Создаем событие о пропуске корректировки
            await create_zone_event(
                zone_id,
                f'{self.event_prefix}_CORRECTION_SKIPPED',
                {
                    f'current_{target_key}': current_val,
                    f'target_{target_key}': target_val,
                    'diff': diff,
                    'reason': reason
                }
            )
            return None
        
        # Проверяем уровень воды перед дозированием
        if not water_level_ok:
            self._log_skip(zone_id=zone_id, reason_code="water_level_not_ok")
            return None
        
        correction_type = self._determine_correction_type(diff)

        # Находим actuator для корректировки
        actuator = self._select_actuator(
            correction_type=correction_type,
            actuators=actuators,
            nodes=nodes
        )
        if not actuator:
            self._log_skip(
                zone_id=zone_id,
                reason_code="actuator_unavailable",
                correction_type=correction_type,
                available_roles=sorted(list((actuators or {}).keys())),
            )
            return None
        
        # Определяем количество дозирования
        dt_seconds = self._get_dt_seconds(zone_id)
        amount = pid.compute(current_val, dt_seconds)

        # Детальное логирование PID вычислений
        logger.debug(
            f"Zone {zone_id}: {self.metric_name} PID calculation",
            extra={
                'zone_id': zone_id,
                'metric': self.metric_name,
                'current': current_val,
                'target': target_val,
                'error': diff,
                'pid_zone': pid.get_zone().value,
                'pid_output': amount,
                'pid_integral': pid.integral,
                'pid_prev_error': pid.prev_error,
                'pid_dt': dt_seconds,
                'pid_config': {
                    'dead_zone': pid.config.dead_zone,
                    'close_zone': pid.config.close_zone,
                    'far_zone': pid.config.far_zone,
                    'kp': pid.config.zone_coeffs[pid.get_zone()].kp,
                    'ki': pid.config.zone_coeffs[pid.get_zone()].ki,
                    'kd': pid.config.zone_coeffs[pid.get_zone()].kd,
                }
            }
        )
        
        # Логируем PID_OUTPUT событие только если output > 0
        if amount > 0:
            await create_zone_event(
                zone_id,
                'PID_OUTPUT',
                {
                    'type': self.correction_type.value,
                    'zone_state': pid.get_zone().value,
                    'output': amount,
                    'error': diff,
                    'dt_seconds': dt_seconds,
                    'current': current_val,
                    'target': target_val,
                    'safety_skip_reason': None,
                }
            )
        else:
            self._log_skip(
                zone_id=zone_id,
                reason_code="pid_output_zero",
                level="info",
                pid_zone=pid.get_zone().value,
                pid_dt_seconds=dt_seconds,
            )
            return None
        
        payload = self._build_correction_command(actuator, correction_type, amount)
        batch_commands: List[Dict[str, Any]] = []
        if self.correction_type == CorrectionType.EC and correction_type == "add_nutrients":
            batch_commands = self._build_ec_component_batch(
                targets=targets,
                actuators=actuators,
                total_ml=amount,
                current_ec=current_val,
                target_ec=target_val,
                allowed_ec_components=allowed_ec_components,
            )
            if not batch_commands:
                logger.warning(
                    "Zone %s: Unable to build EC component batch; skipping dosing",
                    zone_id,
                    extra={
                        "zone_id": zone_id,
                        "allowed_ec_components": allowed_ec_components,
                        "target_ec": target_val,
                        "current_ec": current_val,
                        "total_ml": amount,
                        "available_actuator_roles": sorted(list((actuators or {}).keys())),
                    },
                )
                await create_zone_event(
                    zone_id,
                    "EC_CORRECTION_SKIPPED",
                    {
                        "reason": "ec_component_batch_unavailable",
                        "available_roles": sorted(list((actuators or {}).keys())),
                    },
                )
                return None

        # Формируем команду
        command = {
            'node_uid': actuator['node_uid'],
            'channel': actuator['channel'],
            'cmd': payload['cmd'],
            'params': payload['params'],
            'event_type': self._get_correction_event_type(),
            'event_details': {
                'correction_type': correction_type,
                f'current_{target_key}': current_val,
                f'target_{target_key}': target_val,
                f'target_{target_key}_original': target_original_val,
                'diff': diff,
                'ml': amount,
                'binding_role': actuator.get('role'),
                'pid_zone': pid.get_zone().value,
                'pid_dt_seconds': dt_seconds,
                'safety_bounds_active': safety_active,
                'target_rate_limited': bool(rate_limit_result.get("clamped")),
            },
            'zone_id': zone_id,
            'correction_type_str': target_key,
            'current_value': current_val,
            'target_value': target_val,
            'reason': reason
        }
        nutrition_control = self._extract_nutrition_control(targets)
        if nutrition_control:
            command['nutrition_control'] = nutrition_control

        if batch_commands:
            command['batch_commands'] = batch_commands
            command['event_details']['component_dosing'] = [
                {
                    'component': item.get('component'),
                    'binding_role': item.get('role'),
                    'ml': item.get('ml'),
                    'ratio_pct': item.get('ratio_pct'),
                    'mode': item.get('mode'),
                    'k_ms_per_ml_l': item.get('k_ms_per_ml_l'),
                    'channel': item.get('channel'),
                }
                for item in batch_commands
            ]
        if bounds_context:
            command["event_details"]["bounds"] = {
                "hard_pct": bounds_context.get("hard_pct"),
                "abs_min": bounds_context.get("abs_min"),
                "abs_max": bounds_context.get("abs_max"),
                "max_delta_per_min": bounds_context.get("max_delta_per_min"),
            }

        return command
    
    async def apply_correction(
        self,
        command: Dict[str, Any],
        command_bus,
        pid: Optional[AdaptivePid] = None
    ) -> None:
        """
        Применить корректировку: отправить команду, создать события и логи.
        
        Args:
            command: Команда корректировки (результат check_and_correct)
            command_bus: CommandBus для публикации команд
            pid: Экземпляр PID для контекста (опционально)
        """
        zone_id = command['zone_id']
        correction_type_str = command['correction_type_str']
        current_val = command['current_value']
        target_val = command['target_value']
        diff = command['event_details']['diff']
        correction_type = command['event_details']['correction_type']
        reason = command.get('reason', '')
        correlation_id = str(
            command.get("correlation_id")
            or f"corr:correction:{zone_id}:{correction_type_str}:{uuid4().hex[:12]}"
        )
        command["correlation_id"] = correlation_id
        published_cmd_ids: List[str] = []
        
        # Подготавливаем контекст для аудита
        context = DecisionContext(
            current_value=current_val,
            target_value=target_val,
            diff=diff,
            reason=reason,
            telemetry=command.get('telemetry', {}),
            pid_zone=pid.get_zone().value if pid else None,
            pid_output=command['event_details'].get('ml', 0) if pid else None,
            pid_integral=pid.integral if pid else None,
            pid_prev_error=pid.prev_error if pid else None,
        )
        
        # Отправляем одну или несколько команд через Command Bus с контекстом
        batch_commands = command.get('batch_commands')
        if isinstance(batch_commands, list) and batch_commands:
            dose_delay_sec, ec_stop_tolerance = self._resolve_batch_dose_control(command)
            batch_aborted = False
            successful_components: List[str] = []
            for idx, batch_cmd in enumerate(batch_commands):
                published = await self._publish_controller_command_with_retry(
                    zone_id=zone_id,
                    command_bus=command_bus,
                    controller_command=batch_cmd,
                    context=context,
                    correction_type=correction_type_str,
                )
                if not published:
                    batch_aborted = True
                    failed_component = str(batch_cmd.get('component') or "")
                    remaining_components = len(batch_commands) - idx - 1
                    compensation_result = await self._trigger_ec_partial_batch_compensation(
                        zone_id=zone_id,
                        command=command,
                        successful_components=successful_components,
                        failed_component=failed_component,
                    )
                    await create_zone_event(
                        zone_id,
                        'EC_COMPONENT_BATCH_ABORTED',
                        {
                            'failed_component': failed_component,
                            'failed_channel': batch_cmd.get('channel'),
                            'failed_node_uid': batch_cmd.get('node_uid'),
                            'remaining_components': remaining_components,
                            'reason': 'command_unconfirmed',
                        }
                    )
                    await create_zone_event(
                        zone_id,
                        'EC_BATCH_PARTIAL_FAILURE',
                        {
                            'successful_components': successful_components,
                            'failed_component': failed_component,
                            'failed_channel': batch_cmd.get('channel'),
                            'failed_node_uid': batch_cmd.get('node_uid'),
                            'remaining_components': remaining_components,
                            'status': 'degraded',
                            'target_ec': target_val,
                            'current_ec': current_val,
                            'compensation': compensation_result,
                        }
                    )
                    break
                cmd_id = str(batch_cmd.get("cmd_id") or "").strip()
                if cmd_id:
                    published_cmd_ids.append(cmd_id)
                successful_components.append(str(batch_cmd.get("component") or ""))
                is_last = idx >= len(batch_commands) - 1
                if is_last or self.correction_type != CorrectionType.EC:
                    continue

                if dose_delay_sec > 0:
                    await asyncio.sleep(dose_delay_sec)

                ec_after = await self._get_latest_ec_value(zone_id)
                if ec_after is None:
                    continue

                await create_zone_event(
                    zone_id,
                    'EC_COMPONENT_RECHECK',
                    {
                        'component': batch_cmd.get('component'),
                        'ec_current': ec_after,
                        'ec_target': target_val,
                        'ec_stop_tolerance': ec_stop_tolerance,
                    }
                )

                if ec_after >= (target_val - ec_stop_tolerance):
                    await create_zone_event(
                        zone_id,
                        'EC_COMPONENT_BATCH_STOPPED',
                        {
                            'stopped_after_component': batch_cmd.get('component'),
                            'ec_current': ec_after,
                            'ec_target': target_val,
                            'ec_stop_tolerance': ec_stop_tolerance,
                            'remaining_components': len(batch_commands) - idx - 1,
                        }
                    )
                    break
            if batch_aborted:
                return
        else:
            published = await self._publish_controller_command_with_retry(
                zone_id=zone_id,
                command_bus=command_bus,
                controller_command=command,
                context=context,
                correction_type=correction_type_str,
            )
            if not published:
                await create_zone_event(
                    zone_id,
                    'CORRECTION_ABORTED_COMMAND_FAILURE',
                    {
                        'correction_type': correction_type_str,
                        'cmd': command.get('cmd'),
                        'node_uid': command.get('node_uid'),
                        'channel': command.get('channel'),
                        'reason': 'command_unconfirmed',
                    }
                )
                return
            cmd_id = str(command.get("cmd_id") or "").strip()
            if cmd_id:
                published_cmd_ids.append(cmd_id)
        
        # Записываем информацию о корректировке
        await record_correction(zone_id, correction_type_str, {
            "correction_type": correction_type,
            f"current_{correction_type_str}": current_val,
            f"target_{correction_type_str}": target_val,
            "diff": diff,
            "reason": reason
        })

        correction_event_details = dict(command.get("event_details") or {})
        correction_event_details["correlation_id"] = correlation_id
        correction_event_details["cmd_ids"] = published_cmd_ids
        if published_cmd_ids:
            correction_event_details["cmd_id"] = published_cmd_ids[-1]
        logger.info(
            "Zone %s: correction action event payload enriched with correlation/cmd ids",
            zone_id,
            extra={
                "zone_id": zone_id,
                "correction_type": correction_type_str,
                "correlation_id": correlation_id,
                "cmd_ids": published_cmd_ids,
                "event_type": command.get("event_type"),
            },
        )
        
        # Создаем основное событие корректировки
        await create_zone_event(
            zone_id,
            command['event_type'],
            correction_event_details
        )
        
        # Создаем событие DOSING для совместимости
        await create_zone_event(
            zone_id,
            'DOSING',
            {
                'type': f'{correction_type_str}_correction',
                'correction_type': correction_type,
                f'current_{correction_type_str}': current_val,
                f'target_{correction_type_str}': target_val,
                'diff': diff,
                'correlation_id': correlation_id,
                'cmd_ids': published_cmd_ids,
                'cmd_id': published_cmd_ids[-1] if published_cmd_ids else None,
            }
        )
        
        # Для pH создаем дополнительные события при критических отклонениях
        from config.settings import get_settings
        settings = get_settings()
        
        if self.correction_type == CorrectionType.PH:
            if diff > settings.PH_TOO_HIGH_THRESHOLD:
                await create_zone_event(
                    zone_id,
                    'PH_TOO_HIGH_DETECTED',
                    {
                        'current_ph': current_val,
                        'target_ph': target_val,
                        'diff': diff
                    }
                )
            elif diff < settings.PH_TOO_LOW_THRESHOLD:
                await create_zone_event(
                    zone_id,
                    'PH_TOO_LOW_DETECTED',
                    {
                        'current_ph': current_val,
                        'target_ph': target_val,
                        'diff': diff
                    }
                )
        
        # Создаем AI log
        await create_ai_log(
            zone_id,
            'recommend',
            {
                'action': f'{correction_type_str}_correction',
                'metric': correction_type_str,
                'current': current_val,
                'target': target_val,
                'correction': correction_type
            }
        )

    async def _publish_controller_command_with_retry(
        self,
        *,
        zone_id: int,
        command_bus,
        controller_command: Dict[str, Any],
        context: DecisionContext,
        correction_type: str,
    ) -> bool:
        return await publish_controller_command_with_retry(
            zone_id=zone_id,
            command_bus=command_bus,
            controller_command=controller_command,
            context=context,
            correction_type=correction_type,
            get_settings_fn=get_settings,
            create_zone_event_fn=create_zone_event,
            send_infra_alert_fn=send_infra_alert,
        )

    async def _trigger_ec_partial_batch_compensation(
        self,
        *,
        zone_id: int,
        command: Dict[str, Any],
        successful_components: List[str],
        failed_component: str,
    ) -> Dict[str, Any]:
        return await trigger_ec_partial_batch_compensation(
            zone_id=zone_id,
            command=command,
            successful_components=successful_components,
            failed_component=failed_component,
            enqueue_internal_scheduler_task_fn=enqueue_internal_scheduler_task,
            send_infra_alert_fn=send_infra_alert,
        )

    async def _wait_command_done(self, *, tracker, cmd_id: str, timeout_sec: float) -> Optional[bool]:
        return await wait_command_done(tracker=tracker, cmd_id=cmd_id, timeout_sec=timeout_sec)

    async def _get_pid(self, zone_id: int, setpoint: float) -> AdaptivePid:
        """Получить/инициализировать PID для зоны с восстановлением состояния."""
        pid = self._pid_by_zone.get(zone_id)

        if pid is None:
            # Загружаем конфиг из БД или используем дефолты
            pid_config = await get_config(zone_id, self.correction_type.value, setpoint)
            if pid_config is None:
                # Fallback на дефолты (не должно произойти, но на всякий случай)
                settings = get_settings()
                pid_config = self._build_pid_config(settings, setpoint)
            pid = AdaptivePid(pid_config)
            
            # Пытаемся восстановить состояние из БД
            restored = await self.pid_state_manager.restore_pid_state(
                zone_id,
                self.correction_type.value,
                pid
            )
            if restored:
                logger.info(
                    f"Zone {zone_id}: PID {self.correction_type.value} state restored from DB",
                    extra={'zone_id': zone_id, 'pid_type': self.correction_type.value}
                )
            
            self._pid_by_zone[zone_id] = pid
            self._last_pid_tick[zone_id] = time.monotonic()
        else:
            pid.update_setpoint(setpoint)

        return pid
    
    async def save_all_states(self):
        """Сохранить состояние всех PID контроллеров этого типа."""
        for zone_id, pid in self._pid_by_zone.items():
            await self.pid_state_manager.save_pid_state(
                zone_id,
                self.correction_type.value,
                pid
            )

    def _get_dt_seconds(self, zone_id: int) -> float:
        """Рассчитать dt между вызовами PID для зоны."""
        now = time.monotonic()
        last_tick = self._last_pid_tick.get(zone_id)
        self._last_pid_tick[zone_id] = now

        if last_tick is None:
            return float(get_settings().MAIN_LOOP_SLEEP_SECONDS)

        # Минимальный dt чтобы не делить на 0 и не дёргать производную
        return max(1.0, now - last_tick)

    def _build_pid_config(self, settings, setpoint: float) -> AdaptivePidConfig:
        """Сконфигурировать PID под тип коррекции."""
        if self.correction_type == CorrectionType.PH:
            return AdaptivePidConfig(
                setpoint=setpoint,
                dead_zone=settings.PH_PID_DEAD_ZONE,
                close_zone=settings.PH_PID_CLOSE_ZONE,
                far_zone=settings.PH_PID_FAR_ZONE,
                zone_coeffs={
                    PidZone.DEAD: PidZoneCoeffs(0.0, 0.0, 0.0),
                    PidZone.CLOSE: PidZoneCoeffs(settings.PH_PID_KP_CLOSE, settings.PH_PID_KI_CLOSE, settings.PH_PID_KD_CLOSE),
                    PidZone.FAR: PidZoneCoeffs(settings.PH_PID_KP_FAR, settings.PH_PID_KI_FAR, settings.PH_PID_KD_FAR),
                },
                max_output=settings.PH_PID_MAX_OUTPUT,
                min_output=0.0,
                max_integral=100.0,
                min_interval_ms=settings.PH_PID_MIN_INTERVAL_MS,
                enable_autotune=settings.PH_PID_ENABLE_AUTOTUNE,
                adaptation_rate=settings.PH_PID_ADAPTATION_RATE,
            )

        return AdaptivePidConfig(
            setpoint=setpoint,
            dead_zone=settings.EC_PID_DEAD_ZONE,
            close_zone=settings.EC_PID_CLOSE_ZONE,
            far_zone=settings.EC_PID_FAR_ZONE,
            zone_coeffs={
                PidZone.DEAD: PidZoneCoeffs(0.0, 0.0, 0.0),
                PidZone.CLOSE: PidZoneCoeffs(settings.EC_PID_KP_CLOSE, settings.EC_PID_KI_CLOSE, settings.EC_PID_KD_CLOSE),
                PidZone.FAR: PidZoneCoeffs(settings.EC_PID_KP_FAR, settings.EC_PID_KI_FAR, settings.EC_PID_KD_FAR),
            },
            max_output=settings.EC_PID_MAX_OUTPUT,
            min_output=0.0,
            max_integral=100.0,
            min_interval_ms=settings.EC_PID_MIN_INTERVAL_MS,
            enable_autotune=settings.EC_PID_ENABLE_AUTOTUNE,
            adaptation_rate=settings.EC_PID_ADAPTATION_RATE,
        )
    
    def _select_actuator(
        self,
        correction_type: str,
        actuators: Optional[Dict[str, Dict[str, Any]]],
        nodes: Optional[Dict[str, Dict[str, Any]]]
    ) -> Optional[Dict[str, Any]]:
        """Выбрать actuator по роли."""
        role_order: list[str] = []
        if self.correction_type == CorrectionType.PH:
            role_order = ["ph_base_pump"] if correction_type == "add_base" else ["ph_acid_pump"]
        else:
            # EC: добавляем удобрения, dilute пока не поддерживаем отдельным actuator
            if correction_type == "add_nutrients":
                role_order = ["ec_npk_pump", "ec_calcium_pump", "ec_magnesium_pump", "ec_micro_pump"]
            else:
                # Для dilute нет корректного actuator — пропускаем, чтобы не совершать неверное действие
                return None

        if actuators:
            for role in role_order:
                if role in actuators:
                    return actuators[role]

        return None

    def _build_ec_component_batch(
        self,
        targets: Dict[str, Any],
        actuators: Optional[Dict[str, Dict[str, Any]]],
        total_ml: float,
        current_ec: float,
        target_ec: float,
        allowed_ec_components: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        return build_ec_component_batch(
            targets=targets,
            actuators=actuators,
            total_ml=total_ml,
            current_ec=current_ec,
            target_ec=target_ec,
            allowed_ec_components=allowed_ec_components,
            build_correction_command=self._build_correction_command,
        )

    def _build_actuator_identity(self, actuator: Dict[str, Any]) -> str:
        return build_actuator_identity(actuator)

    def _resolve_ec_component_ratios(
        self,
        targets: Dict[str, Any],
        available_components: List[str],
    ) -> Dict[str, float]:
        return resolve_ec_component_ratios(targets, available_components)

    def _resolve_nutrition_mode(self, nutrition: Dict[str, Any]) -> str:
        return resolve_nutrition_mode(nutrition)

    def _resolve_solution_volume_l(self, nutrition: Dict[str, Any]) -> Optional[float]:
        return resolve_solution_volume_l(nutrition)

    def _build_correction_command(
        self,
        actuator: Dict[str, Any],
        correction_type: str,
        amount_ml: float
    ) -> Dict[str, Any]:
        """
        Собрать payload команды дозирования для actuator.

        Возвращает словарь с cmd и params (поддерживает dose или run_pump).
        """
        role = (actuator.get("role") or "").lower()
        # pH насосы умеют dose, остальным даем run_pump
        use_dose = role.startswith("ph_")
        params: Dict[str, Any] = {"type": correction_type, "ml": amount_ml}

        if use_dose:
            cmd = "dose"
        else:
            cmd = "run_pump"
            ml_per_sec = actuator.get("ml_per_sec") or 1.0
            try:
                ml_per_sec = float(ml_per_sec)
            except (TypeError, ValueError):
                ml_per_sec = 1.0
            duration_ms = max(1, int((amount_ml / ml_per_sec) * 1000))
            params["duration_ms"] = duration_ms

        return {"cmd": cmd, "params": params}

    def _extract_nutrition_control(self, targets: Dict[str, Any]) -> Dict[str, Any]:
        return extract_nutrition_control(targets)

    def _resolve_batch_dose_control(self, command: Dict[str, Any]) -> tuple[float, float]:
        return resolve_batch_dose_control(command)

    async def _get_latest_ec_value(self, zone_id: int) -> Optional[float]:
        return await get_latest_ec_value(zone_id, fetch_fn=fetch)
    
    def _determine_correction_type(self, diff: float) -> str:
        """Определить тип корректировки на основе разницы."""
        from config.settings import get_settings
        settings = get_settings()
        
        threshold = settings.PH_CORRECTION_THRESHOLD if self.correction_type == CorrectionType.PH else settings.EC_CORRECTION_THRESHOLD
        
        if self.correction_type == CorrectionType.PH:
            return "add_base" if diff < -threshold else "add_acid"
        else:  # EC
            return "add_nutrients" if diff < -threshold else "dilute"
    
    def _calculate_amount(self, diff: float) -> float:
        """Рассчитать количество для дозирования."""
        from config.settings import get_settings
        settings = get_settings()
        
        if self.correction_type == CorrectionType.PH:
            return abs(diff) * settings.PH_DOSING_MULTIPLIER
        else:  # EC
            return abs(diff) * settings.EC_DOSING_MULTIPLIER
    
    def _get_correction_event_type(self) -> str:
        """Получить тип события для корректировки."""
        if self.correction_type == CorrectionType.PH:
            return 'PH_CORRECTED'
        else:  # EC
            return 'EC_DOSING'
