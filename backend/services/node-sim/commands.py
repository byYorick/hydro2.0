"""
Обработка команд для node-sim.
Принимает команды из MQTT и обрабатывает их через state_machine.
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, Callable

from .state_machine import CommandStateMachine, CommandStatus
from .model import NodeModel
from .topics import command_response_topic, temp_command_topic, temp_error_topic, error_topic
from .mqtt_client import MqttClient

logger = logging.getLogger(__name__)


class CommandHandler:
    """
    Обработчик команд для node-sim.
    
    Обрабатывает:
    - Прием команд из MQTT
    - Дедупликацию по cmd_id
    - Отправку command_response (ACCEPTED быстро, DONE/FAILED после выполнения)
    - Режимы отказов: delay, drop, duplicate
    """
    
    def __init__(self, node: NodeModel, mqtt: MqttClient):
        """
        Инициализация обработчика команд.
        
        Args:
            node: Модель ноды
            mqtt: MQTT клиент
        """
        self.node = node
        self.mqtt = mqtt
        self.state_machine = CommandStateMachine(max_commands=128)
        self._response_tasks: Dict[str, asyncio.Task] = {}
    
    async def start(self):
        """Запустить обработчик команд."""
        # Подписываемся на команды
        if self.node.mode.value == "preconfig":
            # Temp топики для всех каналов
            for ch in self.node.channels + self.node.actuators:
                topic = temp_command_topic(self.node.hardware_id, ch)
                await self.mqtt.subscribe(topic, self._handle_command)
                logger.info(f"Subscribed to temp command topic: {topic}")
        else:
            # Обычные топики для всех каналов
            for ch in self.node.channels + self.node.actuators:
                topic = f"hydro/{self.node.gh_uid}/{self.node.zone_uid}/{self.node.node_uid}/{ch}/command"
                await self.mqtt.subscribe(topic, self._handle_command)
                logger.info(f"Subscribed to command topic: {topic}")
    
    async def _handle_command(self, topic: str, payload: bytes):
        """Обработать команду из MQTT."""
        try:
            data = json.loads(payload.decode("utf-8"))
            
            # Извлекаем параметры команды
            cmd_id = data.get("cmd_id") or data.get("correlation_id")
            cmd = data.get("cmd") or data.get("type")
            params = data.get("params", {})
            deadline_ms = data.get("deadline_ms")
            
            # Извлекаем channel из топика: hydro/{gh}/{zone}/{node}/{channel}/command
            # Или из params, если указан там
            channel = params.get("channel")
            if not channel:
                # Пытаемся извлечь из топика
                parts = topic.split("/")
                if len(parts) >= 5 and parts[-1] == "command":
                    channel = parts[-2]  # Предпоследний элемент
                else:
                    # Fallback на первый актуатор
                    channel = self.node.actuators[0] if self.node.actuators else "pump_1"
            
            if not cmd_id or not cmd:
                logger.warning(f"Invalid command format: {data}")
                return
            
            logger.info(f"Received command: {cmd_id}, cmd={cmd}, channel={channel}, params={params}")
            
            # Обрабатываем команду через state machine
            state = await self.state_machine.process_command(
                cmd_id=cmd_id,
                cmd=cmd,
                params=params,
                deadline_ms=deadline_ms,
                executor=self._execute_command
            )
            
            # Сохраняем channel в state для использования при отправке ответа
            state.channel = channel
            
            # Отправляем ACCEPTED быстро
            await self._send_response(state, "ACCEPTED")
            
            # Ждем завершения выполнения и отправляем DONE/FAILED
            if state.execution_task:
                asyncio.create_task(self._wait_and_send_final_response(state))
        
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in command: {e}")
        except Exception as e:
            logger.error(f"Error handling command: {e}", exc_info=True)
    
    async def _execute_command(self, cmd: str, params: Dict[str, Any]) -> bool:
        """
        Выполнить команду.
        
        Args:
            cmd: Тип команды
            params: Параметры команды
        
        Returns:
            True если успешно, False если ошибка
        """
        try:
            if cmd == "run_pump":
                return await self._execute_run_pump(params)
            elif cmd == "set_relay" or cmd == "set_relay_state":
                # Поддержка как set_relay, так и set_relay_state для совместимости
                return await self._execute_set_relay(params)
            elif cmd == "set_pwm":
                return await self._execute_set_pwm(params)
            elif cmd == "calibrate":
                return await self._execute_calibrate(params)
            else:
                logger.warning(f"Unknown command: {cmd}")
                return False
        except Exception as e:
            logger.error(f"Error executing command {cmd}: {e}", exc_info=True)
            return False
    
    async def _execute_run_pump(self, params: Dict[str, Any]) -> bool:
        """Выполнить команду run_pump."""
        channel = params.get("channel", "pump_1")
        duration_ms = params.get("duration_ms", 1000)
        
        # Включаем насос
        self.node.set_actuator_state(channel, True, pwm_value=255)
        
        # Ждем duration_ms
        await asyncio.sleep(duration_ms / 1000.0)
        
        # Выключаем насос
        self.node.set_actuator_state(channel, False)
        
        return True
    
    async def _execute_set_relay(self, params: Dict[str, Any]) -> bool:
        """Выполнить команду set_relay."""
        channel = params.get("channel", "pump_1")
        state = params.get("state", False)
        
        self.node.set_actuator_state(channel, state)
        return True
    
    async def _execute_set_pwm(self, params: Dict[str, Any]) -> bool:
        """Выполнить команду set_pwm."""
        channel = params.get("channel", "pump_1")
        value = params.get("value", 0)
        value = max(0, min(255, int(value)))  # Ограничиваем 0-255
        
        self.node.set_actuator_state(channel, value > 0, pwm_value=value)
        return True
    
    async def _execute_calibrate(self, params: Dict[str, Any]) -> bool:
        """Выполнить команду calibrate."""
        cal_type = params.get("type", "PH_7")
        logger.info(f"Calibrating: {cal_type}")
        # Симуляция калибровки
        await asyncio.sleep(0.1)
        return True
    
    async def _send_response(self, state, status: str):
        """
        Отправить ответ на команду.
        
        Args:
            state: Состояние команды (с атрибутом channel)
            status: Статус ответа (ACCEPTED, DONE, FAILED)
        """
        # Используем channel из state (сохранен при обработке команды)
        channel = getattr(state, 'channel', None) or self.node.actuators[0] if self.node.actuators else "pump_1"
        
        # Определяем топик для ответа
        if self.node.mode.value == "preconfig":
            # Используем temp топик
            topic = temp_command_topic(self.node.hardware_id, channel).replace("/command", "/command_response")
        else:
            # Используем обычный топик с правильным channel
            topic = command_response_topic(self.node.gh_uid, self.node.zone_uid, self.node.node_uid, channel)
        
        # Формируем payload
        payload = {
            "cmd_id": state.cmd_id,
            "status": status,
            "ts": int(time.time() * 1000)
        }
        
        if status == "FAILED":
            payload["error_code"] = state.error_code
            payload["error_message"] = state.error_message
        
        if status == "DONE":
            duration_ms = state.get_duration_ms()
            if duration_ms:
                payload["duration_ms"] = duration_ms
        
        # Отправляем ответ
        await self.mqtt.publish_json(topic, payload, qos=1)
        logger.info(f"Sent command_response: {state.cmd_id}, status={status}")
        
        # Режим duplicate_response
        if self.state_machine.should_duplicate_response(state.cmd_id):
            await asyncio.sleep(0.1)
            await self.mqtt.publish_json(topic, payload, qos=1)
            logger.info(f"Sent duplicate command_response: {state.cmd_id}")
    
    async def _wait_and_send_final_response(self, state):
        """Дождаться завершения команды и отправить финальный ответ."""
        try:
            if state.execution_task:
                await state.execution_task
            
            # Отправляем финальный ответ
            if state.status == CommandStatus.DONE:
                await self._send_response(state, "DONE")
            elif state.status == CommandStatus.FAILED:
                await self._send_response(state, "FAILED")
        except Exception as e:
            logger.error(f"Error waiting for command completion: {e}", exc_info=True)

