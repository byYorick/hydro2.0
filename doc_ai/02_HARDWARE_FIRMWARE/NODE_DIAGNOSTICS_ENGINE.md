# NODE_DIAGNOSTICS_ENGINE.md
# Полный движок диагностики узлов ESP32 в системе 2.0
# Self‑Tests • Health Metrics • Failure Detection • Recovery • Reporting

Документ описывает диагностику и самоконтроль узлов ESP32 в архитектуре 2.0.

---

# 1. Цели диагностики узлов

Node Diagnostics Engine выполняет:

- мониторинг здоровья ESP32,
- диагностику сенсоров,
- диагностику актуаторов,
- проверку стабильности Wi‑Fi/MQTT,
- обнаружение ошибок оборудования,
- авто‑восстановление (recovery),
- отправку статусов в backend,
- интеграцию с Alert Engine.

---

# 2. Архитектура Node Diagnostics

Файлы:

```
diagnostics/
 ├── diag_core.c
 ├── diag_wifi.c
 ├── diag_sensors.c
 ├── diag_actuators.c
 ├── diag_memory.c
 ├── diag_mqtt.c
 ├── diag_recovery.c
 └── diag_report.c
```

---

# 3. Категории диагностики

1. **Wi‑Fi Diagnostics**
2. **MQTT Diagnostics**
3. **Memory Health**
4. **Sensor Health**
5. **Actuator Health**
6. **Timing & RTOS Health**
7. **Power Stability**
8. **Thermal Status**
9. **Command Processing Stability**

---

# 4. Wi‑Fi Diagnostics

Проверяет:

- RSSI
- disconnect count
- reconnect attempts
- DHCP errors
- роуминг
- отсутствие связи c MQTT

Статусы:

```
GOOD, MEDIUM, BAD, CRITICAL
```

---

# 5. MQTT Diagnostics

Отслеживает:

- количество reconnects,
- ping-loop hangs,
- publish failures,
- пропущенные ACK команд.

Если MQTT нестабилен → флаг:

```
MQTT_UNSTABLE
```

---

# 6. Memory Diagnostics

Проверяет:

- heap free
- fragmentation level
- min heap watermark
- stack usage per task
- memory leaks (detected by diff)

Порог:

```
heap_free < 20 KB → WARNING
heap_free < 10 KB → CRITICAL
```

---

# 7. Sensor Diagnostics

Диагностика сенсоров:

### PH Sensor
- отсутствие изменения данных
- шум выше нормы
- дрейф > допустимого
- нелогичные скачки

### EC Sensor
- невозможность компенсации
- скачки > 0.8 мС/см
- зависание чтения

### Temperature/Humidity
- невозможные значения
- частые ошибки CRC
- отсутствие обновлений

### Water Level / Flow
- нулевой расход
- скачки уровня
- слишком частые NO_FLOW

---

# 8. Actuator Diagnostics

Отслеживается:

- подтверждение включения/выключения
- перегрев драйвера (опционально)
- подозрительный ток (если датчик)
- заедание клапана
- насос не запустился
- слишком длинное время работы

Типы ошибок:

```
PUMP_FAIL
VALVE_STUCK
ACTUATOR_TIMEOUT
```

---

# 9. Timing & RTOS Diagnostics

Проверяет:

- задержки задач > 200 мс
- блокировки FreeRTOS
- неисполняемые таймеры
- watchdog reset count

Если задача зависает → перезапуск задачи.

---

# 10. Power Diagnostics

Опционально:

- низкое питание 4.5–4.7 В
- нестабильный источник
- отключение по питанию

---

# 11. Thermal Diagnostics

ESP32 перегревается, если:

```
cpu_temp ≥ 80°C → WARNING
cpu_temp ≥ 90°C → CRITICAL
```

---

# 12. Command Stability Diagnostics

Отслеживает:

- количество ошибок команд
- повторные попытки retry
- ошибки HMAC
- недоставленные команды

Если слишком много ошибок:

```
COMMAND_PROCESSING_UNSTABLE
```

---

# 13. Отправка диагностики в статусе

Статусный пакет содержит:

```json
{
 "health": {
 "wifi": "medium",
 "mqtt": "good",
 "memory": "good",
 "sensors": {
 "ph": "good",
 "ec": "drift_warning",
 "temp": "good"
 },
 "actuators": "good",
 "rtos": "good",
 "power": "good",
 "cpu_temp": 57
 }
}
```

---

# 14. Recovery Engine (автовосстановление)

Алгоритмы восстановления:

### Wi‑Fi recovery
- reconnect → backoff → restart wifi → switch AP → full reboot

### MQTT recovery
- reconnect MQTT → restart wifi → restart esp

### Memory recovery
- очистка кэшей
- рестарт задач
- reboot при критическом уровне

### Sensor recovery
- reinit I2C
- reset устройства
- fallback значения

### Actuator recovery
- остановка насосов
- повторная попытка
- переход в safe mode

---

# 15. Node Safe Mode

Если в узле обнаружено:

- критические ошибки сенсоров,
- утечка памяти,
- нестабильный Wi‑Fi,
- постоянные MQTT ошибки,

узел переходит в safe mode:

Отключается:

- дозирование
- полив
- нагреватель

Остаются активны:

- телеметрия
- watchdog reset
- статус

---

# 16. Alert Integration

Ошибки генерируют алерты:

- NODE_OFFLINE
- NODE_UNSTABLE
- SENSOR_FAIL
- ACTUATOR_FAIL
- MEMORY_LOW
- HIGH_CPU_TEMP

---

# 17. ИИ‑интеграция

AI анализирует:

- sensor drift patterns 
- memory leak trends 
- actuator failure probability 
- wifi instability patterns 

AI может предложить:

- перенастройку сенсора,
- замену оборудования,
- перемещение узла,
- изменение интервалов работы.

ИИ НЕ может:

- отключить safety,
- игнорировать критические ошибки.

---

# 18. Чек‑лист диагностики узлов

1. Узлы стабильно подключены? 
2. MQTT работает? 
3. Данные сенсоров логичны? 
4. Актуаторы отвечают корректно? 
5. RTOS задачи не блокируются? 
6. Памяти достаточно? 
7. Нет перегрева процессора? 
8. Safe Mode работает? 
9. Диагностика отправляется каждые 30 секунд? 

---

# Конец файла NODE_DIAGNOSTICS_ENGINE.md
