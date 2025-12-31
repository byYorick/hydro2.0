"""
Correction Controller - универсальный контроллер для корректировки pH и EC.
Устраняет дублирование кода между pH и EC корректировкой.
"""
from typing import Optional, Dict, Any
from utils.adaptive_pid import AdaptivePid
from enum import Enum
from datetime import datetime, timedelta, timezone
import time
import logging
from common.db import create_zone_event, create_ai_log
from common.utils.time import utcnow
from correction_cooldown import should_apply_correction, record_correction
from config.settings import get_settings
from utils.adaptive_pid import AdaptivePid, AdaptivePidConfig, PidZone, PidZoneCoeffs
from services.pid_config_service import get_config, invalidate_cache
from services.pid_state_manager import PidStateManager
from common.alerts import create_alert, AlertSource, AlertCode
from decision_context import DecisionContext
from services.targets_accessor import get_ph_target, get_ec_target

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
        
        # Находим actuator для корректировки
        actuator = self._select_actuator(
            correction_type=self._determine_correction_type(diff),
            actuators=actuators,
            nodes=nodes
        )
        if not actuator:
            return None
        
        # Определяем тип корректировки и количество
        correction_type = self._determine_correction_type(diff)
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
                'dose_ml': amount,
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
            pid_output=command['event_details'].get('dose_ml', 0) if pid else None,
            pid_integral=pid.integral if pid else None,
            pid_prev_error=pid.prev_error if pid else None,
        )
        
        # Отправляем команду через Command Bus с контекстом
        await command_bus.publish_controller_command(zone_id, command, context)
        
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
        """Выбрать actuator по роли (acid/base/nutrient) с fallback на legacy irrig node."""
        role_order: list[str] = []
        if self.correction_type == CorrectionType.PH:
            role_order = ["ph_base_pump"] if correction_type == "add_base" else ["ph_acid_pump"]
        else:
            # EC: добавляем удобрения, dilute пока не поддерживаем отдельным actuator
            if correction_type == "add_nutrients":
                role_order = ["ec_nutrient_pump"]
            else:
                # Для dilute нет корректного actuator — пропускаем, чтобы не совершать неверное действие
                return None

        if actuators:
            for role in role_order:
                if role in actuators:
                    return actuators[role]

        if nodes:
            return self._find_irrigation_node(nodes)

        return None

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
        params: Dict[str, Any] = {"type": correction_type, "dose_ml": amount_ml}

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

    def _find_irrigation_node(self, nodes: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Legacy fallback: найти узел для полива/дозирования по типу irrig."""
        for node_info in nodes.values():
            if node_info.get("type") == "irrig":
                return node_info
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
