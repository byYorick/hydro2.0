"""
Correction Controller - универсальный контроллер для корректировки pH и EC.
Устраняет дублирование кода между pH и EC корректировкой.
"""
import asyncio
from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime, timedelta, timezone
import time
import logging
from common.db import create_zone_event, create_ai_log, fetch
from common.utils.time import utcnow
from correction_cooldown import should_apply_correction, record_correction
from config.settings import get_settings
from utils.adaptive_pid import AdaptivePid, AdaptivePidConfig, PidZone, PidZoneCoeffs
from services.pid_config_service import get_config, invalidate_cache
from services.pid_state_manager import PidStateManager
from common.alerts import create_alert, AlertSource, AlertCode
from common.infra_alerts import send_infra_alert
from decision_context import DecisionContext
from services.targets_accessor import get_ph_target, get_ec_target, get_nutrition_components

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
        self.pid_state_manager = pid_state_manager or PidStateManager()
        # Счетчик подряд пропусков проверки свежести по зонам
        self._freshness_check_failure_count: Dict[int, int] = {}
    
    async def check_and_correct(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        telemetry: Dict[str, Optional[float]],
        telemetry_timestamps: Optional[Dict[str, Any]] = None,
        nodes: Dict[str, Dict[str, Any]] = None,
        water_level_ok: bool = True,
        actuators: Optional[Dict[str, Dict[str, Any]]] = None
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
            return None
        
        # КРИТИЧЕСКАЯ ПРОВЕРКА: проверяем свежесть данных телеметрии
        # Предотвращает дозирование на основе устаревших или недоступных данных (fail-closed)
        freshness_check_passed = False
        freshness_check_error = None
        
        if telemetry_timestamps:
            metric_timestamp = telemetry_timestamps.get(self.metric_name) or telemetry_timestamps.get(target_key)
            if metric_timestamp:
                try:
                    # Парсим timestamp (может быть datetime или строка)
                    if isinstance(metric_timestamp, str):
                        updated_at = datetime.fromisoformat(metric_timestamp.replace('Z', '+00:00'))
                    elif isinstance(metric_timestamp, datetime):
                        updated_at = metric_timestamp
                    else:
                        updated_at = None
                    
                    if updated_at:
                        settings = get_settings()
                        max_age = timedelta(minutes=settings.TELEMETRY_MAX_AGE_MINUTES)
                        # Приводим updated_at к aware UTC для корректного сравнения
                        if updated_at.tzinfo is None:
                            updated_at = updated_at.replace(tzinfo=timezone.utc)
                        elif updated_at.tzinfo != timezone.utc:
                            updated_at = updated_at.astimezone(timezone.utc)
                        age = utcnow() - updated_at
                        
                        if age > max_age:
                            logger.warning(
                                f"Zone {zone_id}: {self.metric_name} data is too old ({age.total_seconds() / 60:.1f} minutes, "
                                f"max: {settings.TELEMETRY_MAX_AGE_MINUTES} minutes). Skipping correction to prevent blind dosing."
                            )
                            # Создаем событие о пропуске корректировки из-за устаревших данных
                            await create_zone_event(
                                zone_id,
                                f'{self.event_prefix}_CORRECTION_SKIPPED_STALE_DATA',
                                {
                                    f'current_{target_key}': current,
                                    f'target_{target_key}': target,
                                    'data_age_minutes': age.total_seconds() / 60,
                                    'max_age_minutes': settings.TELEMETRY_MAX_AGE_MINUTES,
                                    'updated_at': metric_timestamp.isoformat() if isinstance(metric_timestamp, datetime) else str(metric_timestamp),
                                    'reason': 'telemetry_data_too_old'
                                }
                            )
                            # Сбрасываем счетчик пропусков проверки свежести (это другая причина пропуска)
                            self._freshness_check_failure_count.pop(zone_id, None)
                            return None
                        else:
                            # Проверка свежести прошла успешно
                            freshness_check_passed = True
                    else:
                        # Не удалось определить updated_at
                        freshness_check_error = "unable_to_parse_timestamp"
                except Exception as e:
                    # Ошибка при проверке свежести - fail-closed
                    freshness_check_error = str(e)
            else:
                # Нет timestamp для метрики
                freshness_check_error = "timestamp_missing"
        else:
            # Нет telemetry_timestamps - fail-closed
            freshness_check_error = "telemetry_timestamps_missing"
        
        # Fail-closed: если проверка свежести не прошла, не дозируем
        if not freshness_check_passed:
            # Увеличиваем счетчик подряд пропусков
            failure_count = self._freshness_check_failure_count.get(zone_id, 0) + 1
            self._freshness_check_failure_count[zone_id] = failure_count
            
            logger.warning(
                f"Zone {zone_id}: Failed to check {target_key} data freshness (error: {freshness_check_error}). "
                f"Skipping correction to prevent blind dosing (fail-closed). "
                f"Consecutive failures: {failure_count}"
            )
            
            # Создаем событие о пропуске корректировки из-за ошибки проверки свежести
            await create_zone_event(
                zone_id,
                'CORRECTION_SKIPPED_FRESHNESS_CHECK_FAILED',
                {
                    'correction_type': self.correction_type.value,
                    'metric': self.metric_name,
                    f'current_{target_key}': current,
                    f'target_{target_key}': target,
                    'error': freshness_check_error,
                    'consecutive_failures': failure_count,
                    'reason': 'freshness_check_failed'
                }
            )
            
            # Создаем alert при N подряд пропусках
            settings = get_settings()
            if failure_count >= settings.FRESHNESS_CHECK_FAILED_ALERT_THRESHOLD:
                await create_alert(
                    zone_id=zone_id,
                    source=AlertSource.INFRA.value,
                    code=AlertCode.INFRA_FRESHNESS_CHECK_FAILED.value,
                    type='FRESHNESS_CHECK_FAILED',
                    details={
                        'correction_type': self.correction_type.value,
                        'metric': self.metric_name,
                        'consecutive_failures': failure_count,
                        'error': freshness_check_error,
                        'threshold': settings.FRESHNESS_CHECK_FAILED_ALERT_THRESHOLD
                    }
                )
            
            return None
        
        # Проверка свежести прошла успешно - сбрасываем счетчик
        self._freshness_check_failure_count.pop(zone_id, None)
        
        try:
            target_val = float(target)
            current_val = float(current)
        except (ValueError, TypeError) as e:
            logger.warning(f"Zone {zone_id}: Invalid {target_key} values - target={target}, current={current}: {e}")
            return None

        if target_min is not None and target_max is not None:
            if target_min <= current_val <= target_max:
                return None
        
        diff = current_val - target_val

        # Подготавливаем PID для зоны и типа коррекции
        pid = await self._get_pid(zone_id, target_val)
        
        # Проверяем, превышает ли отклонение порог
        if abs(diff) <= pid.config.dead_zone:
            return None
        
        # Проверяем cooldown и анализ тренда
        should_correct, reason = await should_apply_correction(
            zone_id, target_key, current_val, target_val, diff
        )
        
        if not should_correct:
            logger.info(f"Zone {zone_id}: {self.metric_name} correction skipped - {reason}")
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
            return None
        
        correction_type = self._determine_correction_type(diff)

        # Находим actuator для корректировки
        actuator = self._select_actuator(
            correction_type=correction_type,
            actuators=actuators,
            nodes=nodes
        )
        if not actuator:
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
            logger.info(
                f"Zone {zone_id}: {self.metric_name} PID output is zero "
                f"(zone={pid.get_zone().value}, dt={dt_seconds:.2f}s); skipping correction."
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
            )
            if not batch_commands:
                logger.warning(
                    "Zone %s: Unable to build EC component batch; skipping dosing",
                    zone_id,
                    extra={"zone_id": zone_id},
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
                'diff': diff,
                'ml': amount,
                'binding_role': actuator.get('role'),
                'pid_zone': pid.get_zone().value,
                'pid_dt_seconds': dt_seconds
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
                    await create_zone_event(
                        zone_id,
                        'EC_COMPONENT_BATCH_ABORTED',
                        {
                            'failed_component': batch_cmd.get('component'),
                            'failed_channel': batch_cmd.get('channel'),
                            'failed_node_uid': batch_cmd.get('node_uid'),
                            'remaining_components': len(batch_commands) - idx - 1,
                            'reason': 'command_unconfirmed',
                        }
                    )
                    break
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
        
        # Записываем информацию о корректировке
        await record_correction(zone_id, correction_type_str, {
            "correction_type": correction_type,
            f"current_{correction_type_str}": current_val,
            f"target_{correction_type_str}": target_val,
            "diff": diff,
            "reason": reason
        })
        
        # Создаем основное событие корректировки
        await create_zone_event(
            zone_id,
            command['event_type'],
            command['event_details']
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
                'diff': diff
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
        settings = get_settings()
        max_attempts = max(1, int(settings.CORRECTION_COMMAND_MAX_ATTEMPTS))
        timeout_sec = max(0.1, float(settings.CORRECTION_COMMAND_TIMEOUT_SEC))
        retry_delay_sec = max(0.0, float(settings.CORRECTION_COMMAND_RETRY_DELAY_SEC))
        tracker = getattr(command_bus, "tracker", None)

        last_failure_reason = "unknown"
        last_cmd_id: Optional[str] = None

        for attempt in range(1, max_attempts + 1):
            sent = await command_bus.publish_controller_command(zone_id, controller_command, context)
            cmd_id = controller_command.get("cmd_id")
            last_cmd_id = str(cmd_id) if cmd_id else None

            if not sent:
                last_failure_reason = "publish_failed"
            elif tracker and cmd_id:
                wait_result = await self._wait_command_done(
                    tracker=tracker,
                    cmd_id=str(cmd_id),
                    timeout_sec=timeout_sec,
                )
                if wait_result is True:
                    return True
                if wait_result is None:
                    last_failure_reason = f"ack_done_timeout_{timeout_sec}s"
                    try:
                        await tracker.confirm_command_status(
                            str(cmd_id),
                            "TIMEOUT",
                            error=last_failure_reason,
                        )
                    except Exception as confirm_exc:
                        logger.warning(
                            "Zone %s: failed to mark correction timeout cmd_id=%s: %s",
                            zone_id,
                            cmd_id,
                            confirm_exc,
                            extra={"zone_id": zone_id},
                        )
                else:
                    last_failure_reason = "command_failed_status"
            else:
                # Tracker отключен: подтверждение недоступно, считаем отправку успешной.
                return True

            await create_zone_event(
                zone_id,
                'CORRECTION_COMMAND_ATTEMPT_FAILED',
                {
                    'correction_type': correction_type,
                    'attempt': attempt,
                    'max_attempts': max_attempts,
                    'cmd_id': last_cmd_id,
                    'cmd': controller_command.get('cmd'),
                    'node_uid': controller_command.get('node_uid'),
                    'channel': controller_command.get('channel'),
                    'component': controller_command.get('component'),
                    'reason': last_failure_reason,
                },
            )

            if attempt < max_attempts and retry_delay_sec > 0:
                await asyncio.sleep(retry_delay_sec)

        await send_infra_alert(
            code='infra_correction_command_unconfirmed',
            alert_type='Correction Command Unconfirmed',
            message=f'Команда коррекции не подтверждена после {max_attempts} попыток',
            severity='critical',
            zone_id=zone_id,
            service='automation-engine',
            component='correction_controller',
            node_uid=controller_command.get('node_uid'),
            channel=controller_command.get('channel'),
            cmd=controller_command.get('cmd'),
            error_type='CommandUnconfirmed',
            details={
                'correction_type': correction_type,
                'cmd_id': last_cmd_id,
                'max_attempts': max_attempts,
                'timeout_sec': timeout_sec,
                'reason': last_failure_reason,
                'component': controller_command.get('component'),
            },
        )

        return False

    async def _wait_command_done(self, *, tracker, cmd_id: str, timeout_sec: float) -> Optional[bool]:
        try:
            return await tracker.wait_for_command_done(
                cmd_id=cmd_id,
                timeout_sec=timeout_sec,
                poll_interval_sec=min(1.0, max(0.25, timeout_sec / 10.0)),
            )
        except Exception as exc:
            logger.warning(
                "Failed waiting correction command completion for cmd_id=%s: %s",
                cmd_id,
                exc,
            )
            return False

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
    ) -> List[Dict[str, Any]]:
        if not actuators or total_ml <= 0:
            return []

        required_components = ["npk", "calcium", "magnesium", "micro"]
        role_map = {
            "npk": "ec_npk_pump",
            "calcium": "ec_calcium_pump",
            "magnesium": "ec_magnesium_pump",
            "micro": "ec_micro_pump",
        }
        missing_roles = [
            role_map[component]
            for component in required_components
            if role_map[component] not in actuators
        ]
        if missing_roles:
            return []

        component_actuators: Dict[str, Dict[str, Any]] = {
            component: actuators[role_map[component]]
            for component in required_components
        }
        actuator_identity_to_component: Dict[str, str] = {}
        duplicate_actuator_bindings: List[Dict[str, str]] = []
        for component in required_components:
            actuator = component_actuators[component]
            identity = self._build_actuator_identity(actuator)
            previous_component = actuator_identity_to_component.get(identity)
            if previous_component is None:
                actuator_identity_to_component[identity] = component
                continue
            duplicate_actuator_bindings.append(
                {
                    "identity": identity,
                    "component_a": previous_component,
                    "component_b": component,
                }
            )
        if duplicate_actuator_bindings:
            logger.warning(
                "EC component pumps must be unique per component; duplicate actuator bindings detected",
                extra={"duplicates": duplicate_actuator_bindings},
            )
            return []

        # Fail-closed: для EC дозирования требуется валидная калибровка производительности насоса.
        ml_per_sec_by_component: Dict[str, float] = {}
        for component in required_components:
            actuator = component_actuators[component]
            ml_per_sec_raw = actuator.get("ml_per_sec")
            try:
                ml_per_sec = float(ml_per_sec_raw)
            except (TypeError, ValueError):
                ml_per_sec = 0.0
            if ml_per_sec <= 0:
                logger.warning(
                    "EC component batch skipped due to invalid pump calibration",
                    extra={
                        "component": component,
                        "role": actuator.get("role"),
                        "node_uid": actuator.get("node_uid"),
                        "channel": actuator.get("channel"),
                        "ml_per_sec": ml_per_sec_raw,
                    },
                )
                return []
            ml_per_sec_by_component[component] = ml_per_sec

        nutrition = targets.get("nutrition") if isinstance(targets.get("nutrition"), dict) else {}
        components_cfg = get_nutrition_components(targets)
        if any(component not in components_cfg for component in required_components):
            return []
        components_order = required_components

        ratios = self._resolve_ec_component_ratios(targets, components_order)
        if not ratios:
            return []

        mode = self._resolve_nutrition_mode(nutrition)
        solution_volume_l = self._resolve_solution_volume_l(nutrition)

        k_values: Dict[str, Optional[float]] = {}
        for component in components_order:
            cfg_k = components_cfg.get(component, {}).get("k_ms_per_ml_l")
            act_k = component_actuators[component].get("k_ms_per_ml_l")
            try:
                k_candidate = float(cfg_k if cfg_k is not None else act_k)
            except (TypeError, ValueError):
                k_candidate = None
            if k_candidate is not None and k_candidate > 0:
                k_values[component] = k_candidate
            else:
                k_values[component] = None

        commands: List[Dict[str, Any]] = []
        component_ml_map: Dict[str, float] = {}

        if mode == "dose_ml_l_only":
            if solution_volume_l is None or solution_volume_l <= 0:
                return []
            for component in components_order:
                dose_ml_l = components_cfg.get(component, {}).get("dose_ml_per_l")
                try:
                    dose_value = float(dose_ml_l)
                except (TypeError, ValueError):
                    dose_value = 0.0
                if dose_value <= 0:
                    return []
                component_ml_map[component] = round(dose_value * solution_volume_l, 3)

        if mode == "delta_ec_by_k":
            delta_ec = max(0.0, target_ec - current_ec)
            has_all_k = all((k_values.get(component) or 0) > 0 for component in components_order)
            if delta_ec <= 0 or solution_volume_l is None or solution_volume_l <= 0 or not has_all_k:
                return []
            for component in components_order:
                ratio_pct = float(ratios.get(component, 0.0))
                k_value = float(k_values[component] or 0.0)
                delta_ec_component = delta_ec * (ratio_pct / 100.0)
                ml_per_l = delta_ec_component / k_value if k_value > 0 else 0.0
                component_ml_map[component] = round(max(0.0, ml_per_l * solution_volume_l), 3)

        if mode == "ratio_ec_pid":
            has_all_k = all((k_values.get(component) or 0) > 0 for component in components_order)
            if has_all_k:
                weighted = {
                    component: float(ratios.get(component, 0.0)) / float(k_values[component] or 1.0)
                    for component in components_order
                }
                weighted_sum = sum(weighted.values())
                if weighted_sum <= 0:
                    return []
                for component in components_order:
                    component_ml_map[component] = round(max(0.0, total_ml * (weighted[component] / weighted_sum)), 3)
            else:
                remaining_ml = float(total_ml)
                for idx, component in enumerate(components_order):
                    ratio_pct = float(ratios.get(component, 0.0))
                    if idx == len(components_order) - 1:
                        component_ml = max(0.0, round(remaining_ml, 3))
                    else:
                        component_ml = max(0.0, round((total_ml * ratio_pct) / 100.0, 3))
                        remaining_ml -= component_ml
                    component_ml_map[component] = component_ml

        if not component_ml_map:
            return []

        for component in components_order:
            ratio_pct = float(ratios.get(component, 0.0))
            component_ml = max(0.0, float(component_ml_map.get(component, 0.0)))

            if component_ml <= 0:
                continue

            actuator = component_actuators[component]
            actuator_with_calibration = dict(actuator)
            actuator_with_calibration["ml_per_sec"] = ml_per_sec_by_component[component]
            payload = self._build_correction_command(actuator_with_calibration, "add_nutrients", component_ml)
            payload["params"]["component"] = component
            payload["params"]["ratio_pct"] = round(ratio_pct, 2)

            commands.append(
                {
                    "node_uid": actuator["node_uid"],
                    "channel": actuator["channel"],
                    "cmd": payload["cmd"],
                    "params": payload["params"],
                    "component": component,
                    "role": actuator.get("role"),
                    "ml": component_ml,
                    "ratio_pct": round(ratio_pct, 2),
                    "mode": mode,
                    "k_ms_per_ml_l": k_values.get(component),
                }
            )

        return commands

    def _build_actuator_identity(self, actuator: Dict[str, Any]) -> str:
        node_channel_id = actuator.get("node_channel_id")
        if node_channel_id is not None:
            return f"node_channel:{node_channel_id}"

        node_uid = actuator.get("node_uid")
        channel = actuator.get("channel")
        if node_uid is not None and channel is not None:
            return f"node_uid:{node_uid}|channel:{channel}"

        node_id = actuator.get("node_id")
        if node_id is not None and channel is not None:
            return f"node_id:{node_id}|channel:{channel}"

        role = actuator.get("role")
        if role is not None:
            return f"role:{role}"

        return "unknown"

    def _resolve_ec_component_ratios(
        self,
        targets: Dict[str, Any],
        available_components: List[str],
    ) -> Dict[str, float]:
        components = get_nutrition_components(targets)
        if not components:
            return {}

        raw_ratios: Dict[str, float] = {}
        for component in available_components:
            ratio = components.get(component, {}).get("ratio_pct")
            if ratio is None:
                return {}
            try:
                ratio_value = float(ratio)
            except (TypeError, ValueError):
                return {}
            if ratio_value < 0:
                return {}
            raw_ratios[component] = ratio_value

        total = sum(raw_ratios.values())
        if total <= 0:
            return {}

        normalized: Dict[str, float] = {}
        for component in available_components:
            normalized[component] = round((raw_ratios[component] / total) * 100.0, 2)
        return normalized

    def _resolve_nutrition_mode(self, nutrition: Dict[str, Any]) -> str:
        mode = str(nutrition.get("mode", "")).strip().lower()
        if mode in {"ratio_ec_pid", "delta_ec_by_k", "dose_ml_l_only"}:
            return mode
        return ""

    def _resolve_solution_volume_l(self, nutrition: Dict[str, Any]) -> Optional[float]:
        raw = nutrition.get("solution_volume_l")
        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        if value <= 0:
            return None
        return value

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
        nutrition = targets.get("nutrition")
        if not isinstance(nutrition, dict):
            return {}

        result: Dict[str, Any] = {}
        mode_raw = nutrition.get("mode")
        if isinstance(mode_raw, str):
            mode = mode_raw.strip().lower()
            if mode in {"ratio_ec_pid", "delta_ec_by_k", "dose_ml_l_only"}:
                result["mode"] = mode

        solution_volume_raw = nutrition.get("solution_volume_l")
        if solution_volume_raw is not None:
            try:
                solution_volume = float(solution_volume_raw)
                if solution_volume > 0:
                    result["solution_volume_l"] = solution_volume
            except (TypeError, ValueError):
                pass

        delay_raw = nutrition.get("dose_delay_sec")
        if delay_raw is not None:
            try:
                delay = float(delay_raw)
                if delay >= 0:
                    result["dose_delay_sec"] = delay
            except (TypeError, ValueError):
                pass

        tolerance_raw = nutrition.get("ec_stop_tolerance")
        if tolerance_raw is not None:
            try:
                tolerance = float(tolerance_raw)
                if tolerance >= 0:
                    result["ec_stop_tolerance"] = tolerance
            except (TypeError, ValueError):
                pass

        return result

    def _resolve_batch_dose_control(self, command: Dict[str, Any]) -> tuple[float, float]:
        settings = get_settings()
        control = command.get("nutrition_control")
        if not isinstance(control, dict):
            control = {}

        delay_raw = control.get("dose_delay_sec", settings.EC_COMPONENT_DOSE_DELAY_SEC)
        tolerance_raw = control.get("ec_stop_tolerance", settings.EC_COMPONENT_RECHECK_TOLERANCE)

        try:
            dose_delay_sec = max(0.0, float(delay_raw))
        except (TypeError, ValueError):
            dose_delay_sec = float(settings.EC_COMPONENT_DOSE_DELAY_SEC)

        try:
            ec_stop_tolerance = max(0.0, float(tolerance_raw))
        except (TypeError, ValueError):
            ec_stop_tolerance = float(settings.EC_COMPONENT_RECHECK_TOLERANCE)

        return dose_delay_sec, ec_stop_tolerance

    async def _get_latest_ec_value(self, zone_id: int) -> Optional[float]:
        try:
            rows = await fetch(
                """
                SELECT tl.last_value
                FROM telemetry_last tl
                JOIN sensors s ON s.id = tl.sensor_id
                WHERE s.zone_id = $1
                  AND s.type = 'EC'
                ORDER BY tl.updated_at DESC
                LIMIT 1
                """,
                zone_id,
            )
        except Exception as exc:
            logger.warning(
                "Zone %s: failed to fetch EC after component dose: %s",
                zone_id,
                exc,
                extra={"zone_id": zone_id},
            )
            return None

        if not rows:
            return None

        value = rows[0].get("last_value")
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    
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
