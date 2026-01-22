"""
Обработчик команд с идемпотентностью и поддержкой всех команд.
"""

import asyncio
import json
from typing import Dict, Any, Optional, Callable
from functools import lru_cache
from collections import OrderedDict
from dataclasses import dataclass

from .state_machine import (
    CommandStateMachine,
    CommandState,
    CommandStatus,
    FailureMode
)
from .utils_time import current_timestamp_ms
from .logging import get_logger

logger = get_logger(__name__)


@dataclass
class CommandResponse:
    """Ответ на команду."""
    cmd_id: str
    status: str  # "ACK", "DONE", "ERROR", "INVALID", "BUSY", "NO_EFFECT"
    details: Optional[Dict[str, Any]] = None
    response_payload: Optional[Dict[str, Any]] = None
    ts: Optional[int] = None


class LRUCommandCache:
    """
    LRU кеш для идемпотентности команд.
    
    Хранит cmd_id -> (final_status, response_payload)
    """
    
    def __init__(self, maxsize: int = 1000):
        self.cache: OrderedDict[str, tuple[CommandStatus, Optional[Dict[str, Any]]]] = OrderedDict()
        self.maxsize = maxsize
    
    def get(self, cmd_id: str) -> Optional[tuple[CommandStatus, Optional[Dict[str, Any]]]]:
        """Получить закешированный результат команды."""
        if cmd_id in self.cache:
            # Перемещаем в конец (самый недавний)
            result = self.cache.pop(cmd_id)
            self.cache[cmd_id] = result
            return result
        return None
    
    def put(self, cmd_id: str, status: CommandStatus, payload: Optional[Dict[str, Any]]):
        """Сохранить результат команды в кеш."""
        if cmd_id in self.cache:
            # Обновляем существующий
            self.cache.pop(cmd_id)
        
        self.cache[cmd_id] = (status, payload)
        
        # Удаляем самый старый, если превышен размер
        if len(self.cache) > self.maxsize:
            self.cache.popitem(last=False)
    
    def clear(self):
        """Очистить кеш."""
        self.cache.clear()


class CommandHandler:
    """
    Обработчик команд с идемпотентностью.
    
    Поддерживает:
    - Все команды: set_relay, run_pump, dose, set_pwm, hil_set_sensor,
      hil_raise_error, hil_clear_error, hil_set_flow, hil_set_current
    - Идемпотентность через LRU cache
    - State machine для управления статусами
    - Негативные режимы
    - Мониторинг доставленных команд (cmd_id, тайминги, статистика)
    """
    
    def __init__(self, node, mqtt_client, event_loop=None, telemetry_publisher=None):
        """
        Инициализация обработчика команд.
        
        Args:
            node: Модель ноды (должна иметь gh_uid, zone_uid, node_uid, channels, actuators)
            mqtt_client: MQTT клиент для публикации ответов
            event_loop: Event loop для async операций (опционально)
            telemetry_publisher: Публикатор телеметрии для on-demand публикации (опционально)
        """
        self.node = node
        self.mqtt = mqtt_client
        self.telemetry_publisher = telemetry_publisher
        self.state_machine = CommandStateMachine()
        self.cache = LRUCommandCache(maxsize=1000)
        # Храним event loop, чтобы планировать async задачи из MQTT-потока без создания временных loop
        self._event_loop = event_loop
        
        # Мониторинг команд: статистика доставленных команд
        self._command_stats = {
            "total_received": 0,
            "total_delivered": 0,
            "total_dropped": 0,
            "total_duplicated": 0,
            "total_failed": 0,
            "commands_by_status": {},
            "avg_response_time_ms": 0.0,
        }
        
        # Внутреннее состояние для команд
        self.relay_states: Dict[str, bool] = {}  # channel -> state
        self.pump_states: Dict[str, bool] = {}  # channel -> running
        self.pwm_values: Dict[str, int] = {}  # channel -> value (0-255)
        self.sensor_values: Dict[str, float] = {}  # channel -> value
        self.errors: Dict[str, str] = {}  # channel -> error message
        self.flow_values: Dict[str, float] = {}  # channel -> flow rate
        self.current_values: Dict[str, float] = {}  # channel -> current

        # Эмпирические коэффициенты для симуляции корректировок
        self._ph_delta_per_ml = 0.01
        self._ec_delta_per_ml = 0.02
        
        # Маппинг команд (strict format, без legacy-алиасов)
        self.command_map = {
            "set_relay": self._handle_set_relay,
            "run_pump": self._handle_run,
            "dose": self._handle_dose,
            "set_pwm": self._handle_set_pwm,
            "hil_set_sensor": self._handle_hil_set_sensor,
            "hil_raise_error": self._handle_hil_raise_error,
            "hil_clear_error": self._handle_hil_clear_error,
            "hil_set_flow": self._handle_hil_set_flow,
            "hil_set_current": self._handle_hil_set_current,
            "hil_request_telemetry": self._handle_hil_request_telemetry,
        }
    
    async def start(self):
        """Запустить обработчик команд."""
        # Сохраняем текущий loop, чтобы использовать его из MQTT callback-потока
        if self._event_loop is None:
            try:
                self._event_loop = asyncio.get_running_loop()
            except RuntimeError:
                self._event_loop = None
        # Получаем список каналов (комбинация sensors и actuators)
        channels = set()
        if hasattr(self.node, 'channels') and self.node.channels:
            channels.update(self.node.channels)
        if hasattr(self.node, 'sensors') and self.node.sensors:
            channels.update(self.node.sensors)
        if hasattr(self.node, 'actuators') and self.node.actuators:
            channels.update(self.node.actuators)
        
        # Если каналов нет, используем дефолтные
        if not channels:
            channels = {"ph_sensor", "ec_sensor", "pump_1", "fan_1"}
        
        # Устанавливаем информацию об узле в MQTT клиенте
        self.mqtt.set_node_info(
            gh_uid=self.node.gh_uid,
            zone_uid=self.node.zone_uid,
            node_uid=self.node.node_uid,
            node_hw_id=self.node.hardware_id,
            preconfig_mode=(self.node.mode == "preconfig")
        )
        
        # Устанавливаем callback для команд
        self.mqtt.set_command_callback(self._on_command_dict)
        
        # Подписываемся на команды через специальный метод
        self.mqtt.subscribe_commands()
        
        # Также подписываемся на команды для каждого канала (для совместимости)
        for channel in channels:
            if self.node.mode == "preconfig":
                from .topics import temp_command
                topic = temp_command(self.node.hardware_id, channel)
            else:
                from .topics import command
                topic = command(self.node.gh_uid, self.node.zone_uid, self.node.node_uid, channel)
            self.mqtt.subscribe(topic, self._on_command, qos=1)
            logger.info(f"Subscribed to command topic: {topic}")
    
    def _on_command_dict(self, topic: str, command_dict: dict):
        """
        Обработчик входящей команды через callback (для использования с mqtt_client).
        
        Args:
            topic: MQTT топик
            command_dict: Распарсенный JSON команды
        """
        try:
            # Парсим топик для получения канала
            parts = topic.split("/")
            if len(parts) < 6:
                logger.error(f"Invalid command topic format: {topic}")
                return
            
            channel = parts[4]
            
            validation_error = self._validate_command_payload(command_dict)
            if validation_error:
                logger.error(f"Command validation failed: {validation_error}")
                self._schedule_async(
                    self._send_error_response(
                        channel,
                        command_dict.get("cmd_id"),
                        "INVALID",
                        validation_error,
                    )
                )
                return
            
            cmd_id = command_dict["cmd_id"]
            cmd = command_dict["cmd"]
            params = command_dict.get("params", {})
            exec_time_ms = 100
            
            # Обрабатываем команду
            self._schedule_async(self._handle_command(channel, cmd_id, cmd, params, exec_time_ms))
        
        except Exception as e:
            logger.error(f"Error processing command from callback: {e}", exc_info=True)
    
    def _on_command(self, topic: str, payload: bytes):
        """
        Обработчик входящей команды.
        
        Args:
            topic: MQTT топик (hydro/{gh}/{zone}/{node}/{channel}/command)
            payload: JSON payload команды
        """
        try:
            # Парсим топик для получения канала
            parts = topic.split("/")
            if len(parts) < 6:
                logger.error(f"Invalid command topic format: {topic}")
                return
            
            channel = parts[4]
            
            # Парсим команду
            try:
                data = json.loads(payload.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.error(f"Failed to parse command JSON: {e}")
                self._schedule_async(self._send_error_response(channel, None, "INVALID", "Invalid JSON"))
                return
            
            validation_error = self._validate_command_payload(data)
            if validation_error:
                logger.error(f"Command validation failed: {validation_error}")
                self._schedule_async(
                    self._send_error_response(
                        channel,
                        data.get("cmd_id"),
                        "INVALID",
                        validation_error,
                    )
                )
                return
            
            cmd_id = data["cmd_id"]
            cmd = data["cmd"]
            params = data.get("params", {})
            exec_time_ms = 100  # Strict format: exec_time_ms не используется
            
            # Мониторинг: увеличиваем счетчик полученных команд
            self._command_stats["total_received"] += 1
            
            logger.info(
                f"Received command: {cmd} (cmd_id={cmd_id}, channel={channel}, "
                f"exec_time_ms={exec_time_ms}, total_received={self._command_stats['total_received']})"
            )
            
            # Проверяем кеш для идемпотентности
            cached = self.cache.get(cmd_id)
            if cached is not None:
                cached_status, cached_payload = cached
                logger.info(f"Command {cmd_id} is cached, returning cached result")
                self._schedule_async(self._send_cached_response(channel, cmd_id, cached_status, cached_payload))
                return
            
            # Обрабатываем команду
            self._schedule_async(self._handle_command(channel, cmd_id, cmd, params, exec_time_ms))
        
        except Exception as e:
            logger.error(f"Error processing command: {e}", exc_info=True)
            # Пытаемся отправить ошибку, если есть cmd_id
            try:
                data = json.loads(payload.decode('utf-8'))
                cmd_id = data.get("cmd_id")
                channel = topic.split("/")[4] if len(topic.split("/")) >= 5 else "unknown"
                self._schedule_async(self._send_error_response(channel, cmd_id, "ERROR", str(e)))
            except:
                pass
    
    def _validate_command_payload(self, payload: Dict[str, Any]) -> Optional[str]:
        required_keys = {"cmd_id", "cmd", "params", "ts", "sig"}
        allowed_keys = set(required_keys)
        if not isinstance(payload, dict):
            return "Command payload must be an object"
        missing = required_keys - set(payload.keys())
        if missing:
            return f"Missing fields: {', '.join(sorted(missing))}"
        extra = set(payload.keys()) - allowed_keys
        if extra:
            return f"Unknown fields: {', '.join(sorted(extra))}"
        if not isinstance(payload.get("cmd_id"), str) or not payload.get("cmd_id"):
            return "Invalid cmd_id"
        if not isinstance(payload.get("cmd"), str) or not payload.get("cmd"):
            return "Invalid cmd"
        if not isinstance(payload.get("params"), dict):
            return "Invalid params (must be object)"
        if not isinstance(payload.get("ts"), int) or payload.get("ts", -1) < 0:
            return "Invalid ts"
        if not isinstance(payload.get("sig"), str) or not payload.get("sig"):
            return "Invalid sig"
        return None

    async def _handle_command(
        self,
        channel: str,
        cmd_id: str,
        cmd: str,
        params: Dict[str, Any],
        exec_time_ms: int
    ):
        """
        Обработать команду.
        
        Args:
            channel: Канал команды
            cmd_id: ID команды
            cmd: Имя команды
            params: Параметры команды
            exec_time_ms: Время выполнения в миллисекундах
        """
        params = dict(params or {})
        params.setdefault("channel", channel)

        if self.node.is_offline():
            logger.warning(f"Node offline, dropping command {cmd_id} ({cmd})")
            self._command_stats["total_dropped"] += 1
            return

        # Проверяем, поддерживается ли команда
        if cmd not in self.command_map:
            logger.warning(f"Unknown command: {cmd}")
            await self._send_error_response(channel, cmd_id, "INVALID", f"Unknown command: {cmd}")
            return
        
        # Принимаем команду в state machine
        state = self.state_machine.accept_command(
            cmd_id=cmd_id,
            cmd=cmd,
            params=params,
            exec_time_ms=exec_time_ms,
            channel=channel
        )
        
        # Отправляем ACK сразу (по протоколу: ACK = команда принята к выполнению)
        await self._send_response(channel, cmd_id, "ACK", {"details": "Command accepted"})
        
        # Выполняем команду асинхронно
        executor = self.command_map[cmd]
        asyncio.create_task(self._execute_command_async(state, executor))
    
    async def _execute_command_async(
        self,
        state: CommandState,
        executor: Callable[[str, Dict[str, Any]], tuple[CommandStatus, Optional[Dict[str, Any]]]]
    ):
        """Выполнить команду асинхронно."""
        execution_start_ms = current_timestamp_ms()
        try:
            logger.info(
                f"Executing command {state.cmd_id} (cmd={state.cmd}, channel={state.channel}, "
                f"accepted_at={state.accepted_at_ms}ms)"
            )
            # Для команды hil_request_telemetry выполняем публикацию напрямую
            if state.cmd == "hil_request_telemetry" and self.telemetry_publisher:
                try:
                    await self.telemetry_publisher.publish_on_demand()
                    logger.info("Triggered on-demand telemetry publication")
                    final_status = CommandStatus.DONE
                    response_payload = {"details": "Telemetry publication triggered"}
                except Exception as e:
                    logger.error(f"Error in on-demand telemetry: {e}", exc_info=True)
                    final_status = CommandStatus.ERROR
                    response_payload = {"error": f"Failed to publish telemetry: {str(e)}"}
            else:
                # Выполняем команду через state machine
                logger.info(f"Executing command via state machine: {state.cmd_id}")
                final_status, response_payload = await self.state_machine.execute_command(state, executor)
                logger.info(f"Command {state.cmd_id} executed, final_status={final_status}, response_payload={response_payload}")
            
            # Сохраняем в кеш для идемпотентности
            self.cache.put(state.cmd_id, final_status, response_payload)
            
            # Вычисляем время выполнения команды
            execution_time_ms = current_timestamp_ms() - execution_start_ms
            response_time_ms = (state.done_at_ms or current_timestamp_ms()) - state.accepted_at_ms
            
            # Обновляем статистику
            status_str = self._status_to_string(final_status)
            self._command_stats["commands_by_status"][status_str] = \
                self._command_stats["commands_by_status"].get(status_str, 0) + 1
            
            # Отправляем финальный ответ
            details = response_payload or {"details": "OK"}
            
            logger.info(
                f"Sending final response for command {state.cmd_id}: status={status_str}, "
                f"details={details}, execution_time={execution_time_ms}ms, "
                f"response_time={response_time_ms}ms"
            )
            
            # Проверяем негативные режимы
            if self.state_machine.should_drop_response(state.cmd_id):
                logger.warning(
                    f"Dropping response for command {state.cmd_id} "
                    f"(execution_time={execution_time_ms}ms, response_time={response_time_ms}ms)"
                )
                self._command_stats["total_dropped"] += 1
                return
            response_delay_ms = self.state_machine.get_response_delay_ms()
            if response_delay_ms > 0:
                await asyncio.sleep(response_delay_ms / 1000.0)

            if self.node.is_offline():
                logger.warning(f"Node offline, dropping response for {state.cmd_id}")
                self._command_stats["total_dropped"] += 1
                return
            await self._send_response(state.channel, state.cmd_id, status_str, details)
            self._command_stats["total_delivered"] += 1
            
            # Обновляем среднее время ответа
            total_delivered = self._command_stats["total_delivered"]
            current_avg = self._command_stats["avg_response_time_ms"]
            self._command_stats["avg_response_time_ms"] = \
                (current_avg * (total_delivered - 1) + response_time_ms) / total_delivered
            
            logger.info(
                f"Final response sent for command {state.cmd_id}: {status_str} "
                f"(response_time={response_time_ms}ms, avg_response_time={self._command_stats['avg_response_time_ms']:.1f}ms)"
            )
            
            # Дублируем ответ, если нужно
            if self.state_machine.should_duplicate_response(state.cmd_id):
                logger.info(f"Duplicating response for command {state.cmd_id}")
                self._command_stats["total_duplicated"] += 1
                await asyncio.sleep(0.1)  # Небольшая задержка перед дубликатом
                if self.node.is_offline():
                    logger.warning(f"Node offline, dropping duplicate response for {state.cmd_id}")
                    self._command_stats["total_dropped"] += 1
                    return
                await self._send_response(state.channel, state.cmd_id, status_str, details)
        
        except Exception as e:
            execution_time_ms = current_timestamp_ms() - execution_start_ms
            logger.error(
                f"Error executing command {state.cmd_id}: {e} "
                f"(execution_time={execution_time_ms}ms)", exc_info=True
            )
            # Сохраняем ошибку в кеш
            self.cache.put(state.cmd_id, CommandStatus.ERROR, {"error": str(e)})
            self._command_stats["total_failed"] += 1
            self._command_stats["commands_by_status"]["ERROR"] = \
                self._command_stats["commands_by_status"].get("ERROR", 0) + 1
            await self._send_error_response(state.channel, state.cmd_id, "ERROR", str(e))
    
    def get_command_stats(self) -> Dict[str, Any]:
        """
        Получить статистику доставленных команд.
        
        Returns:
            Словарь со статистикой команд
        """
        return dict(self._command_stats)
    
    async def _send_response(
        self,
        channel: str,
        cmd_id: str,
        status: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Отправить ответ на команду."""
        topic = f"hydro/{self.node.gh_uid}/{self.node.zone_uid}/{self.node.node_uid}/{channel}/command_response"
        
        response = {
            "cmd_id": cmd_id,
            "status": status,
            "ts": current_timestamp_ms()
        }
        
        if details:
            response["details"] = details
        
        self.mqtt.publish_json(topic, response, qos=1)
        logger.debug(f"Sent command response: {status} for {cmd_id}")
    
    def _schedule_async(self, coro):
        """Запланировать выполнение async функции."""
        try:
            loop = self._event_loop or asyncio.get_running_loop()
            if loop.is_running():
                # run_coroutine_threadsafe безопасно вызывается из MQTT-потока
                asyncio.run_coroutine_threadsafe(coro, loop)
            else:
                loop.run_until_complete(coro)
        except RuntimeError:
            # Если нет event loop, создаем новый
            asyncio.run(coro)
    
    async def _send_error_response(
        self,
        channel: str,
        cmd_id: Optional[str],
        status: str,
        error: str
    ):
        """Отправить ответ об ошибке."""
        if cmd_id is None:
            logger.warning("Cannot send error response: cmd_id is None")
            return
        
        await self._send_response(channel, cmd_id, status, {"error_message": error})
    
    async def _send_cached_response(
        self,
        channel: str,
        cmd_id: str,
        status: CommandStatus,
        payload: Optional[Dict[str, Any]]
    ):
        """Отправить закешированный ответ (идемпотентность)."""
        status_str = self._status_to_string(status)
        details = payload or {"details": "OK (cached)"}
        await self._send_response(channel, cmd_id, status_str, details)
    
    def _status_to_string(self, status: CommandStatus) -> str:
        """Преобразовать CommandStatus в строку для ответа."""
        if status == CommandStatus.DONE:
            return "DONE"  # Команда выполнена успешно
        elif status == CommandStatus.ACK:
            return "ACK"  # Команда принята (по протоколу используется ACK)
        elif status == CommandStatus.ERROR:
            return "ERROR"  # По протоколу ошибка - это ERROR
        elif status == CommandStatus.INVALID:
            return "INVALID"
        elif status == CommandStatus.BUSY:
            return "BUSY"
        elif status == CommandStatus.NO_EFFECT:
            return "NO_EFFECT"
        else:
            return status.value

    def _apply_dose_effect(self, correction_type: str, ml: float) -> tuple[bool, Dict[str, Any]]:
        """Применить эффект дозировки к сенсорам."""
        details: Dict[str, Any] = {
            "correction_type": correction_type,
            "ml": ml,
        }
        if correction_type in ("add_acid", "add_base"):
            sensor = "ph_sensor" if "ph_sensor" in self.node.sensor_states else "ph"
            current = self.node.get_sensor_value(sensor)
            if current is None:
                return False, {**details, "details": "No PH sensor available"}
            delta = self._ph_delta_per_ml * ml
            if correction_type == "add_acid":
                delta = -delta
            new_value = max(0.0, min(14.0, current + delta))
            self.node.set_sensor_value(sensor, new_value)
            details.update({"ph_before": current, "ph_after": new_value})
            return True, details

        if correction_type in ("add_nutrients", "dilute"):
            sensor = "ec_sensor" if "ec_sensor" in self.node.sensor_states else "ec"
            current = self.node.get_sensor_value(sensor)
            if current is None:
                return False, {**details, "details": "No EC sensor available"}
            delta = self._ec_delta_per_ml * ml
            if correction_type == "dilute":
                delta = -delta
            new_value = max(0.0, current + delta)
            self.node.set_sensor_value(sensor, new_value)
            details.update({"ec_before": current, "ec_after": new_value})
            return True, details

        return False, {**details, "details": "Unsupported correction type"}
    
    # Обработчики команд
    
    def _handle_set_relay(self, cmd: str, params: Dict[str, Any]) -> tuple[CommandStatus, Optional[Dict[str, Any]]]:
        """Обработать команду set_relay."""
        state = params.get("state")
        channel = params.get("channel", "main_pump")  # По умолчанию main_pump
        
        if state is None:
            return CommandStatus.INVALID, {"error": "Missing 'state' parameter"}
        
        if not isinstance(state, bool):
            return CommandStatus.INVALID, {"error": "Parameter 'state' must be boolean"}
        
        # Используем модель для установки состояния актуатора
        if channel in self.node.actuators:
            self.node.set_actuator(channel, state)
            logger.info(f"Set actuator {channel} to {state}")
            return CommandStatus.DONE, {"details": f"Actuator {channel} set to {state}"}
        else:
            # Fallback для старых команд
            self.relay_states[channel] = state
            logger.info(f"Set relay {channel} to {state}")
            return CommandStatus.DONE, {"details": f"Relay {channel} set to {state}"}
    
    def _handle_run(self, cmd: str, params: Dict[str, Any]) -> tuple[CommandStatus, Optional[Dict[str, Any]]]:
        """Обработать команду run_pump (запуск насоса)."""
        channel = params.get("channel", "main_pump")
        duration_ms = params.get("duration_ms", 0)
        correction_type = params.get("type")
        ml = params.get("ml")
        
        # Проверяем, не запущен ли уже насос
        act_state = self.node.get_actuator_state(channel)
        if act_state and act_state.state:
            return CommandStatus.BUSY, {"error": f"Pump {channel} is already running"}
        
        # Запускаем насос через модель
        if channel in self.node.actuators:
            self.node.set_actuator(channel, True, pwm_value=255)
            logger.info(f"Started pump {channel} for {duration_ms}ms")
            
            # Если указана длительность, останавливаем через время
            if duration_ms > 0:
                asyncio.create_task(self._stop_pump_after(channel, duration_ms))
            
            response = {"details": f"Pump {channel} started", "duration_ms": duration_ms}
            if correction_type and ml is not None:
                try:
                    ml_value = float(ml)
                except (TypeError, ValueError):
                    ml_value = None
                if ml_value is not None and ml_value > 0:
                    applied, dose_details = self._apply_dose_effect(correction_type, ml_value)
                    response["dose"] = dose_details
                    if not applied:
                        return CommandStatus.NO_EFFECT, response
            return CommandStatus.DONE, response
        else:
            # Fallback для старых команд
            if self.pump_states.get(channel, False):
                return CommandStatus.BUSY, {"error": f"Pump {channel} is already running"}
            self.pump_states[channel] = True
            logger.info(f"Started pump {channel} for {duration_ms}ms")
            if duration_ms > 0:
                asyncio.create_task(self._stop_pump_after(channel, duration_ms))
            response = {"details": f"Pump {channel} started", "duration_ms": duration_ms}
            if correction_type and ml is not None:
                try:
                    ml_value = float(ml)
                except (TypeError, ValueError):
                    ml_value = None
                if ml_value is not None and ml_value > 0:
                    applied, dose_details = self._apply_dose_effect(correction_type, ml_value)
                    response["dose"] = dose_details
                    if not applied:
                        return CommandStatus.NO_EFFECT, response
            return CommandStatus.DONE, response

    def _handle_dose(self, cmd: str, params: Dict[str, Any]) -> tuple[CommandStatus, Optional[Dict[str, Any]]]:
        """Обработать команду dose."""
        ml = params.get("ml")
        correction_type = params.get("type")

        if ml is None:
            return CommandStatus.INVALID, {"error": "Missing 'ml' parameter"}
        try:
            ml_value = float(ml)
        except (TypeError, ValueError):
            return CommandStatus.INVALID, {"error": "Parameter 'ml' must be numeric"}
        if ml_value <= 0:
            return CommandStatus.INVALID, {"error": "Parameter 'ml' must be positive"}
        if not correction_type:
            return CommandStatus.INVALID, {"error": "Missing 'type' parameter"}

        applied, dose_details = self._apply_dose_effect(correction_type, ml_value)
        if applied:
            return CommandStatus.DONE, {"details": "Dose applied", **dose_details}
        return CommandStatus.NO_EFFECT, {"details": "Dose had no effect", **dose_details}
    
    async def _stop_pump_after(self, channel: str, duration_ms: int):
        """Остановить насос через указанное время."""
        await asyncio.sleep(duration_ms / 1000.0)
        # Используем модель для остановки
        if channel in self.node.actuators:
            self.node.set_actuator(channel, False)
        else:
            self.pump_states[channel] = False
        logger.info(f"Stopped pump {channel} after {duration_ms}ms")
    
    def _handle_stop(self, cmd: str, params: Dict[str, Any]) -> tuple[CommandStatus, Optional[Dict[str, Any]]]:
        """Обработать команду stop (legacy, не используется в strict режиме)."""
        channel = params.get("channel", "main_pump")
        
        # Используем модель для остановки
        if channel in self.node.actuators:
            act_state = self.node.get_actuator_state(channel)
            if not act_state or not act_state.state:
                return CommandStatus.NO_EFFECT, {"details": f"Pump {channel} is not running"}
            self.node.set_actuator(channel, False)
            logger.info(f"Stopped pump {channel}")
            return CommandStatus.DONE, {"details": f"Pump {channel} stopped"}
        else:
            # Fallback для старых команд
            if not self.pump_states.get(channel, False):
                return CommandStatus.NO_EFFECT, {"details": f"Pump {channel} is not running"}
            self.pump_states[channel] = False
            logger.info(f"Stopped pump {channel}")
            return CommandStatus.DONE, {"details": f"Pump {channel} stopped"}
    
    def _handle_set_pwm(self, cmd: str, params: Dict[str, Any]) -> tuple[CommandStatus, Optional[Dict[str, Any]]]:
        """Обработать команду set_pwm."""
        value = params.get("value")
        channel = params.get("channel", "main_pump")
        
        if value is None:
            return CommandStatus.INVALID, {"error": "Missing 'value' parameter"}
        
        if not isinstance(value, int) or not (0 <= value <= 255):
            return CommandStatus.INVALID, {"error": "Parameter 'value' must be integer 0-255"}
        
        # Используем модель для установки PWM
        if channel in self.node.actuators:
            self.node.set_actuator(channel, value > 0, pwm_value=value)
            logger.info(f"Set PWM {channel} to {value}")
            return CommandStatus.DONE, {"details": f"PWM {channel} set to {value}", "value": value}
        else:
            # Fallback для старых команд
            self.pwm_values[channel] = value
            logger.info(f"Set PWM {channel} to {value}")
            return CommandStatus.DONE, {"details": f"PWM {channel} set to {value}", "value": value}
    
    def _handle_hil_set_sensor(self, cmd: str, params: Dict[str, Any]) -> tuple[CommandStatus, Optional[Dict[str, Any]]]:
        """Обработать команду hil_set_sensor (HIL инжект телеметрии)."""
        channel = params.get("channel")
        value = params.get("value")
        
        if channel is None:
            return CommandStatus.INVALID, {"error": "Missing 'channel' parameter"}
        
        if value is None:
            return CommandStatus.INVALID, {"error": "Missing 'value' parameter"}
        
        if not isinstance(value, (int, float)):
            return CommandStatus.INVALID, {"error": "Parameter 'value' must be number"}
        
        # Используем модель для установки значения сенсора
        if channel in self.node.sensors:
            self.node.set_sensor_value(channel, float(value))
            logger.info(f"Set sensor {channel} to {value}")
            return CommandStatus.DONE, {"details": f"Sensor {channel} set to {value}", "value": value}
        else:
            # Fallback для старых команд
            self.sensor_values[channel] = float(value)
            logger.info(f"Set sensor {channel} to {value}")
            return CommandStatus.DONE, {"details": f"Sensor {channel} set to {value}", "value": value}
    
    def _handle_hil_raise_error(self, cmd: str, params: Dict[str, Any]) -> tuple[CommandStatus, Optional[Dict[str, Any]]]:
        """Обработать команду hil_raise_error (HIL инжект ошибки)."""
        channel = params.get("channel", "default")
        error_msg = params.get("error", "HIL injected error")
        
        self.errors[channel] = error_msg
        logger.warning(f"Raised error on {channel}: {error_msg}")
        
        return CommandStatus.DONE, {"details": f"Error raised on {channel}", "error": error_msg}
    
    def _handle_hil_clear_error(self, cmd: str, params: Dict[str, Any]) -> tuple[CommandStatus, Optional[Dict[str, Any]]]:
        """Обработать команду hil_clear_error (HIL очистка ошибки)."""
        channel = params.get("channel", "default")
        
        if channel in self.errors:
            del self.errors[channel]
            logger.info(f"Cleared error on {channel}")
            return CommandStatus.DONE, {"details": f"Error cleared on {channel}"}
        else:
            return CommandStatus.NO_EFFECT, {"details": f"No error to clear on {channel}"}
    
    def _handle_hil_set_flow(self, cmd: str, params: Dict[str, Any]) -> tuple[CommandStatus, Optional[Dict[str, Any]]]:
        """Обработать команду hil_set_flow (HIL установка потока)."""
        channel = params.get("channel", "main_pump")
        flow = params.get("flow")
        
        if flow is None:
            return CommandStatus.INVALID, {"error": "Missing 'flow' parameter"}
        
        if not isinstance(flow, (int, float)):
            return CommandStatus.INVALID, {"error": "Parameter 'flow' must be number"}
        
        # Используем модель для установки flow_present
        if channel in self.node.actuators:
            act_state = self.node.get_actuator_state(channel)
            if act_state:
                act_state.flow_present = bool(flow > 0)
                # Обновляем телеметрию
                self.node.update()
                logger.info(f"Set flow {channel} to {flow}")
                return CommandStatus.DONE, {"details": f"Flow {channel} set to {flow}", "flow": flow}
        
        # Fallback для старых команд
        self.flow_values[channel] = float(flow)
        logger.info(f"Set flow {channel} to {flow}")
        return CommandStatus.DONE, {"details": f"Flow {channel} set to {flow}", "flow": flow}
    
    def _handle_hil_set_current(self, cmd: str, params: Dict[str, Any]) -> tuple[CommandStatus, Optional[Dict[str, Any]]]:
        """Обработать команду hil_set_current (HIL установка тока)."""
        channel = params.get("channel", "current_1")
        current = params.get("current")
        
        if current is None:
            return CommandStatus.INVALID, {"error": "Missing 'current' parameter"}
        
        if not isinstance(current, (int, float)):
            return CommandStatus.INVALID, {"error": "Parameter 'current' must be number"}
        
        # Используем модель для установки тока через overcurrent_mode
        # Если current > 500, включаем режим перегрузки
        current_ma = float(current)
        if current_ma > 500.0:
            self.node.set_overcurrent_mode(True, current=current_ma)
            logger.info(f"Set overcurrent mode with current {current_ma}mA")
        else:
            # Устанавливаем ток напрямую в сенсор
            self.node.set_sensor_value("ina209_ma", current_ma)
            logger.info(f"Set current {channel} to {current_ma}mA")
        
        # Fallback для старых команд
        self.current_values[channel] = current_ma
        return CommandStatus.DONE, {"details": f"Current {channel} set to {current_ma}", "current": current_ma}
    
    def _handle_hil_request_telemetry(self, cmd: str, params: Dict[str, Any]) -> tuple[CommandStatus, Optional[Dict[str, Any]]]:
        """
        Обработать команду hil_request_telemetry (HIL запрос телеметрии on-demand).
        
        Эта команда триггерит немедленную публикацию телеметрии для всех каналов.
        """
        if self.telemetry_publisher is None:
            return CommandStatus.ERROR, {"error": "Telemetry publisher not available"}
        
        # Триггерим публикацию телеметрии on-demand асинхронно
        # Создаем задачу для публикации (не ждем завершения)
        try:
            loop = self._event_loop
            if loop is None:
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    # Если нет event loop, создаем задачу в текущем контексте
                    # Это будет обработано в _execute_command_async
                    pass
            
            if loop and loop.is_running():
                # Если loop запущен, создаем задачу
                asyncio.create_task(self.telemetry_publisher.publish_on_demand())
                logger.info("Triggered on-demand telemetry publication (async)")
                return CommandStatus.DONE, {"details": "Telemetry publication triggered"}
            else:
                # Если loop не запущен, это будет обработано в _execute_command_async
                # Но для совместимости со state machine возвращаем статус
                logger.info("Telemetry publication will be triggered in async context")
                return CommandStatus.DONE, {"details": "Telemetry publication will be triggered"}
        except Exception as e:
            logger.error(f"Error triggering on-demand telemetry: {e}", exc_info=True)
            return CommandStatus.ERROR, {"error": f"Failed to publish telemetry: {str(e)}"}
    
    def _handle_hil_request_telemetry(self, cmd: str, params: Dict[str, Any]) -> tuple[CommandStatus, Optional[Dict[str, Any]]]:
        """
        Обработать команду hil_request_telemetry (HIL запрос телеметрии on-demand).
        
        Эта команда триггерит немедленную публикацию телеметрии для всех каналов.
        """
        if self.telemetry_publisher is None:
            return CommandStatus.ERROR, {"error": "Telemetry publisher not available"}
        
        # Триггерим публикацию телеметрии on-demand
        try:
            # Используем asyncio для вызова async метода
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Если loop уже запущен, создаем задачу
                asyncio.create_task(self.telemetry_publisher.publish_on_demand())
            else:
                # Если loop не запущен, запускаем синхронно
                loop.run_until_complete(self.telemetry_publisher.publish_on_demand())
        except Exception as e:
            logger.error(f"Error triggering on-demand telemetry: {e}", exc_info=True)
            return CommandStatus.ERROR, {"error": f"Failed to publish telemetry: {str(e)}"}
        
        logger.info("Triggered on-demand telemetry publication")
        return CommandStatus.DONE, {"details": "Telemetry publication triggered"}
